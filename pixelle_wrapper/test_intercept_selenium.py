"""
Selenium 版截流脚本（抖音 Web）

流程（与产品约定对齐）：
- 关键词搜索（persona.industry_keywords 多词按 / 轮换，状态见 data/intercept_keyword_rotation.json）→ 视频 Tab → 筛选「最新发布」「半年内」（每换一词重筛）→ 列表边滑边依次处理
- 无评论（抢首评）则点关闭控件回列表（同页不 driver.get，以免丢筛选）
- 有评论：扫评论区意向（persona.intent_keywords + 内置词；可加 --ai-intent 豆包二判）→ 点头像新开 Tab → 先关注再私信 → 文案豆包
- 主要步骤默认 3～7s 随机停顿（--human-delay-min/max）；可选 --start-delay-seconds；评论 jsonl 中 play_count 固定 0（曝光未对接）
- 私信：仅「发送成功且回显校验通过」计入当日上限（默认 10 条/自然日）；去重文件记录后该用户终身不再私信
- 评论：本视频第一次出现意向即触发「素材评论」一次（与私信是否成功无关）；每视频最多成功评论 1 次；
  仅「发布成功且回显」计入当日上限（默认 12 条/自然日）；已成功评论过的视频跨跑次跳过
- 文案：默认走豆包（prompts/ + config.yaml persona）；`--no-doubao` 时用 --fixed-dm / --fixed-comment

运行示例（PowerShell）：
  cd F:\\shuziren\\pixelle_wrapper
  python test_intercept_selenium.py --min-likes 20
  python test_intercept_selenium.py --no-doubao --fixed-dm "..." --fixed-comment "..."

注意：
- Chrome 用户数据目录默认与 ai_pipeline/browser_manager.py 内一致：
  pixelle_wrapper/browser_data/chrome_user_data（+ config.yaml 的 profile_directory）。
- 跑脚本时不要另开同一 Profile 的手动 Chrome，以免锁配置。
- 豆包密钥/模型见 ai_pipeline/doubao_client.py 与环境变量 AI_API_KEY、AI_MODEL；联调可将 USE_TEMP_INPUT_666=True。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import socket
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# ---- 豆包客户端：跑通联调后取消下行注释 ----
from ai_pipeline.doubao_client import doubao_chat_completion

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    SessionNotCreatedException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

logger = logging.getLogger(__name__)

THIS_DIR = Path(__file__).resolve().parent
ART_DIR = THIS_DIR / "debug_artifacts_intercept_selenium"
ART_DIR.mkdir(parents=True, exist_ok=True)

# 与 BrowserManager 一致：ai_pipeline 的 parent.parent 即 pixelle_wrapper
CHROME_USER_DATA_DIR_DEFAULT = THIS_DIR / "browser_data" / "chrome_user_data"

# ---------------------------------------------------------------------------
# 联调时可将下行改为 True，私信/评论将固定 TEMP_INPUT_TEXT，不请求豆包。
USE_TEMP_INPUT_666 = False
TEMP_INPUT_TEXT = "666"
# ---------------------------------------------------------------------------

# ---- 提示词路径（豆包恢复后使用，勿删）----
PROMPT_DM = THIS_DIR / "prompts" / "私信回复_豆包prompt.txt"
PROMPT_COMMENT = THIS_DIR / "prompts" / "素材评论一句话_豆包prompt.txt"
PROMPT_INTENT_DECISION = THIS_DIR / "prompts" / "意向客户判定_豆包prompt.txt"

DEDUP_DM_DEFAULT = THIS_DIR / "data" / "dm_sent.jsonl"
COMMENT_LOG_DEFAULT = THIS_DIR / "data" / "intercept_comments.jsonl"
KEYWORD_ROTATION_STATE = THIS_DIR / "data" / "intercept_keyword_rotation.json"

# 意向判定（默认，未开 --ai-intent）：整条评论转小写后，只要包含下列任一词的子串即视为意向（含「多少钱」「价格」等询价）。
# 传 --ai-intent 时仍走 ai_intent_decide（当前联调为注释，实际等同关键词）。
INTENT_KEYWORDS = [
    "联系方式", "怎么合作", "合作", "代理", "加盟", "在哪", "地址",
    "报价", "多少钱", "价格", "怎么联系", "电话", "微信", "vx", "V信", "加V",
]

# 截流脚本构建号（写入日志，便于客户现场核对是否已更新到含 search-result-card 根节点修复的版本）
INTERCEPT_SELENIUM_BUILD = "1.0.14"

# 评论入口 / 占位：保留旧 class，并包容 data-e2e 与新版占位 span
_COMMENT_ENTRY_ICON_CSS = (
    '[data-e2e="feed-comment-icon"], div.jp8u3iov, div[class*="jp8u3iov"]'
)
_COMMENT_PLACEHOLDER_SPAN_CSS = (
    "span.hVeIqFGi, span[class*='hVeIqFGi'], span.j_kd_P_l, span[class*='j_kd_P_l']"
)


def _setup_logging() -> Path:
    log_dir = THIS_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"intercept_selenium_{time.strftime('%Y%m%d_%H%M%S')}.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    logger.info(f"[SeleniumIntercept] 日志: {log_path}")
    logger.info(f"[SeleniumIntercept] 构建: {INTERCEPT_SELENIUM_BUILD}")
    try:
        _selfcheck_like_parsers()
    except Exception as e:
        logger.error(f"[SeleniumIntercept] 点赞解析自检失败: {e}")
        raise
    return log_path


def _today_calendar() -> str:
    return time.strftime("%Y-%m-%d")


def _rand_sleep(a: float = 0.6, b: float = 1.5) -> None:
    time.sleep(random.uniform(a, b))


def _normalize_user_id(text: str) -> str:
    if not text:
        return ""
    s = str(text)
    m = re.search(r"douyin\.com/user/([^/?#]+)", s)
    if m:
        return m.group(1)
    m = re.search(r"/user/([^/?#]+)", s)
    if m:
        return m.group(1)
    return ""


def _video_id_from_url(url: str) -> str:
    m = re.search(r"/video/(\d+)", url or "")
    return m.group(1) if m else ""


def _find_video_modal_candidates(driver: webdriver.Chrome) -> List[Any]:
    """搜索页视频多为悬浮层（dialog / Modal），收集足够大且可见的容器。"""
    roots: List[Any] = []
    seen: Set[str] = set()
    for sel in (
        "div[role='dialog']",
        "[class*='Drawer']",
        "[class*='drawer']",
    ):
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                try:
                    if not el.is_displayed():
                        continue
                    r = el.rect
                    if r.get("width", 0) < 260 or r.get("height", 0) < 160:
                        continue
                    eid = getattr(el, "id", "") or str(id(el))
                    if eid in seen:
                        continue
                    seen.add(eid)
                    roots.append(el)
                except Exception:
                    continue
        except Exception:
            continue
    try:
        for el in driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'Modal')]|//div[contains(@class,'modal')]",
        ):
            try:
                if not el.is_displayed():
                    continue
                r = el.rect
                if r.get("width", 0) < 260 or r.get("height", 0) < 160:
                    continue
                eid = getattr(el, "id", "") or str(id(el))
                if eid in seen:
                    continue
                seen.add(eid)
                roots.append(el)
            except Exception:
                continue
    except Exception:
        pass
    return roots


def _element_tree_contains_video_id(el, video_id: str) -> bool:
    if not video_id or el is None:
        return False
    try:
        if el.find_elements(By.CSS_SELECTOR, f'a[href*="/video/{video_id}"]'):
            return True
    except Exception:
        pass
    try:
        if el.find_elements(By.XPATH, f".//*[contains(@href,'{video_id}')]"):
            return True
    except Exception:
        pass
    return False


def _modal_shows_player_for_id(modal, video_id: str) -> bool:
    """悬浮窗内出现目标视频链接或足够大的 video（且 subtree 含该 id 线索）。"""
    if _element_tree_contains_video_id(modal, video_id):
        try:
            for v in modal.find_elements(By.TAG_NAME, "video"):
                if v.is_displayed():
                    return True
        except Exception:
            pass
        return True
    try:
        for v in modal.find_elements(By.TAG_NAME, "video"):
            if not v.is_displayed():
                continue
            r = v.rect
            if r.get("width", 0) < 200 or r.get("height", 0) < 100:
                continue
            html = modal.get_attribute("innerHTML") or ""
            if video_id in html:
                return True
    except Exception:
        pass
    return False


def _large_video_ancestor_has_video_link(driver: webdriver.Chrome, video_id: str) -> bool:
    """新标签整页播放等：大屏 video 祖先链上需出现 /video/{id}，避免列表小窗误判。"""
    try:
        return bool(
            driver.execute_script(
                """
                const vid = arguments[0];
                const videos = [...document.querySelectorAll('video')];
                for (const v of videos) {
                  const r = v.getBoundingClientRect();
                  if (r.width < 320 || r.height < 160) continue;
                  if (r.bottom < 0 || r.top > innerHeight + 80) continue;
                  let n = v;
                  for (let i = 0; i < 28 && n; i++) {
                    const links = n.querySelectorAll('a[href*="/video/"]');
                    for (const a of links) {
                      if (a.href && a.href.indexOf('/video/' + vid) !== -1) return true;
                    }
                    n = n.parentElement;
                  }
                }
                return false;
                """,
                video_id,
            )
        )
    except Exception:
        return False


def _page_has_floating_video_for_id(driver: webdriver.Chrome, video_id: str) -> bool:
    """是否已进入当前视频播放区：只看 DOM（悬浮窗优先），不用地址栏。"""
    ev = (video_id or "").strip()
    if not ev:
        return False
    for root in _find_video_modal_candidates(driver):
        if _modal_shows_player_for_id(root, ev):
            return True
    return _large_video_ancestor_has_video_link(driver, ev)


def _find_modal_root_for_video(driver: webdriver.Chrome, video_id: str):
    ev = (video_id or "").strip()
    if not ev:
        return None
    for root in _find_video_modal_candidates(driver):
        if _modal_shows_player_for_id(root, ev):
            return root
    return None


def _meets_min_likes(likes: int, min_likes: int) -> bool:
    """
    min_likes>0 时必须解析到点赞且 likes>=min_likes；likes<=0 一律不选（避免点到 0 赞/解析失败的首卡）。
    若需「解析不到也试」可传 --min-likes 0。
    """
    if min_likes <= 0:
        return True
    if likes <= 0:
        return False
    return likes >= min_likes


def _text_looks_like_video_duration(text: str) -> bool:
    """列表里「00:45」「1:23」是时长，常被误当成点赞。"""
    t = (text or "").strip()
    if re.match(r"^\d{1,2}:\d{2}$", t):
        return True
    if re.match(r"^\d{1,2}:\d{2}:\d{2}$", t):
        return True
    return False


def _text_looks_like_publish_date(text: str) -> bool:
    """列表里「5月9日」「· 2025年2月23日」等是发布日期，勿误当点赞。"""
    t = (text or "").strip()
    if not t:
        return False
    if re.search(r"\d+\s*月\d+\s*日", t):
        return True
    if re.search(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日", t):
        return True
    return "月" in t and "日" in t and len(t) <= 24


# 搜索卡片点赞容器（多代 class 并存，按客户抓包逐步补齐）
_LIKE_COUNT_BOX_SELECTORS = (
    "div.z5UgP5jK",
    "div.pl6nCmrM",
    "div[class*='pl6nCmrM']",
    "div.GiEcbsyC",
    "div[class*='GiEcbsyC']",
)

# 封面浮层内点赞 span 兜底（videoImage 下的心形+数字，不依赖易变的中间层 class）
_LIKE_COUNT_SPAN_SELECTORS = (
    "div.pl6nCmrM span",
    "div.gM8PpRYt div.pl6nCmrM span",
    "div[class*='videoImage'] div.pl6nCmrM span",
    "div.GiEcbsyC span",
    "div[class*='GiEcbsyC'] span",
    "div[class*='videoImage'] div[class*='GiEcbsyC'] span",
    "div[class*='videoImage'] div[class*='EcbsyC'] span",
    "span.ShfAqUnv",
    "[class*='like'] span",
    "span[class*='Like']",
    "div[class*='videoImage'] ~ * span",
)


def _span_text_to_like_count(text: str) -> int:
    if _text_looks_like_video_duration(text) or _text_looks_like_publish_date(text):
        return 0
    return _parse_like_to_int(text)


def _span_text_to_like_count_strict(text: str) -> int:
    """兜底扫 span 时仅接受整段为点赞数（避免日期/标题里的零散数字）。"""
    t = (text or "").strip()
    if not t or _text_looks_like_video_duration(t) or _text_looks_like_publish_date(t):
        return 0
    if not re.match(r"^\d+(\.\d+)?(万|w)?$", t, flags=re.IGNORECASE):
        return 0
    return _parse_like_to_int(t)


def _read_like_span_text(sp) -> str:
    """列表封面赞数常被 CSS 隐藏，textContent 比 is_displayed+text 更可靠。"""
    try:
        tx = (sp.get_attribute("textContent") or sp.text or "").strip()
        if tx:
            return tx
    except Exception:
        pass
    return ""


def _like_count_from_like_box(box) -> int:
    for sp in box.find_elements(By.CSS_SELECTOR, "span"):
        try:
            v = _span_text_to_like_count(_read_like_span_text(sp))
            if v > 0:
                return v
        except Exception:
            continue
    return 0


def _parse_likes_from_like_boxes(root, box_selectors: tuple[str, ...]) -> int:
    """在指定点赞容器内取 span（不依赖 is_displayed，封面浮层赞数常为隐藏但仍可读）。"""
    if root is None:
        return 0
    for box_sel in box_selectors:
        try:
            for box in root.find_elements(By.CSS_SELECTOR, box_sel):
                v = _like_count_from_like_box(box)
                if v > 0:
                    return v
        except Exception:
            continue
    return 0


def _parse_likes_from_card_js(driver: webdriver.Chrome, card) -> int:
    """JS 在 videoImage 浮层内读心形旁 span（兼容 GiEcbsyC / pl6nCmrM 等混淆 class）。"""
    if driver is None or card is None:
        return 0
    try:
        raw = driver.execute_script(
            """
            const card = arguments[0];
            const boxSels = [
              '[class*="GiEcbsyC"]', '[class*="pl6nCmrM"]',
              '[class*="EcbsyC"]', '[class*="pl6nCmrM"]', '[class*="z5UgP5jK"]'
            ];
            const re = /^\\d+(\\.\\d+)?(万|w)?$/i;
            const roots = card.querySelectorAll('[class*="videoImage"], [class*="VideoImage"]');
            const scanRoot = roots.length ? roots : [card];
            for (const root of scanRoot) {
              for (const sel of boxSels) {
                for (const box of root.querySelectorAll(sel)) {
                  const sp = box.querySelector('span');
                  if (!sp) continue;
                  const t = (sp.textContent || sp.innerText || '').trim();
                  if (t && re.test(t)) return t;
                }
              }
              for (const sp of root.querySelectorAll('span')) {
                const t = (sp.textContent || sp.innerText || '').trim();
                if (t && re.test(t)) return t;
              }
            }
            return '';
            """,
            card,
        )
        return _span_text_to_like_count(str(raw or "").strip())
    except Exception:
        return 0


def _parse_likes_from_link_js(driver: webdriver.Chrome, link_el) -> int:
    """从 /video/ 链接向上逐层扫封面赞数（避免误选空的嵌套 search-result-card）。"""
    if driver is None or link_el is None:
        return 0
    try:
        raw = driver.execute_script(
            """
            const a = arguments[0];
            const re = /^\\d+(\\.\\d+)?(万|w)?$/i;
            const boxSels = [
              '[class*="GiEcbsyC"]', '[class*="pl6nCmrM"]',
              '[class*="EcbsyC"]', '[class*="z5UgP5jK"]'
            ];
            let el = a;
            for (let depth = 0; depth < 16 && el; depth++, el = el.parentElement) {
              for (const sel of boxSels) {
                for (const box of el.querySelectorAll(sel)) {
                  const sp = box.querySelector('span');
                  const t = sp ? (sp.textContent || sp.innerText || '').trim() : '';
                  if (t && re.test(t)) return t;
                }
              }
              for (const img of el.querySelectorAll('[class*="videoImage"], [class*="VideoImage"]')) {
                for (const sp of img.querySelectorAll('span')) {
                  const t = (sp.textContent || sp.innerText || '').trim();
                  if (t && re.test(t)) return t;
                }
              }
            }
            return '';
            """,
            link_el,
        )
        return _span_text_to_like_count(str(raw or "").strip())
    except Exception:
        return 0


_GI_LIKE_BOX_SEL = (
    "div.GiEcbsyC, div[class*='GiEcbsyC'], "
    "div.pl6nCmrM, div[class*='pl6nCmrM'], div.z5UgP5jK"
)


def _card_roots_for_likes(card, link_el) -> List[Any]:
    """按优先级返回多个候选根：从最贴近链接的祖先到外层 li。"""
    roots: List[Any] = []
    seen: Set[int] = set()

    def _add(el) -> None:
        if el is None:
            return
        try:
            key = id(el)
        except Exception:
            return
        if key in seen:
            return
        seen.add(key)
        roots.append(el)

    if link_el is not None:
        try:
            ancestors = link_el.find_elements(
                By.XPATH,
                "./ancestor::div[contains(@class,'search-result-card')]",
            )
            for root in reversed(ancestors):
                try:
                    if root.find_elements(By.CSS_SELECTOR, _GI_LIKE_BOX_SEL):
                        _add(root)
                except Exception:
                    continue
            if ancestors:
                _add(ancestors[-1])
        except Exception:
            pass
        for xp in (
            "./ancestor::li[contains(@class,'QdtBFx1O')][1]",
            "./ancestor::li[1]",
        ):
            try:
                _add(link_el.find_element(By.XPATH, xp))
            except Exception:
                continue
    if card is not None:
        _add(card)
    return roots


def _parse_likes_from_root(driver, root) -> int:
    """在单个 DOM 根上尽量解析点赞数。"""
    if root is None:
        return 0
    v = _parse_likes_from_like_boxes(root, _LIKE_COUNT_BOX_SELECTORS)
    if v > 0:
        return v
    if driver is not None:
        v = _parse_likes_from_card_js(driver, root)
        if v > 0:
            return v
    for sel in _LIKE_COUNT_SPAN_SELECTORS:
        try:
            for sp in root.find_elements(By.CSS_SELECTOR, sel):
                v = _span_text_to_like_count_strict(_read_like_span_text(sp))
                if v > 0:
                    return v
                v = _span_text_to_like_count(_read_like_span_text(sp))
                if v > 0:
                    return v
        except Exception:
            continue
    try:
        for sp in root.find_elements(By.CSS_SELECTOR, "span.ShfAqUnv"):
            try:
                v = _span_text_to_like_count_strict(_read_like_span_text(sp))
                if v > 0:
                    return v
            except Exception:
                continue
    except Exception:
        pass
    return 0


def _resolve_search_result_card_root(card, link_el):
    """返回最可能含封面赞数的卡片根（供标题解析等复用）。"""
    for root in _card_roots_for_likes(card, link_el):
        if _parse_likes_from_like_boxes(root, _LIKE_COUNT_BOX_SELECTORS) > 0:
            return root
    roots = _card_roots_for_likes(card, link_el)
    if roots:
        return roots[0]
    return card


def _parse_likes_from_search_card(card, link_el) -> int:
    """
    搜索卡片内点赞：z5UgP5jK / pl6nCmrM / GiEcbsyC 等封面浮层心形旁 span（如 739、1239、1.1万、3.3万）。
    """
    driver = None
    try:
        if link_el is not None:
            driver = link_el.parent
    except Exception:
        pass

    for root in _card_roots_for_likes(card, link_el):
        v = _parse_likes_from_root(driver, root)
        if v > 0:
            return v
    if driver is not None and link_el is not None:
        v = _parse_likes_from_link_js(driver, link_el)
        if v > 0:
            return v
    return _parse_likes_near_element(link_el)


def _parse_search_card_caption(card, link_el=None) -> str:
    """
    搜索列表卡片内主文案（多为标题 + #话题 同一行）。
    与点赞解析共用 search-result-card 根（避免外层 li 无标题节点）。
    """
    if card is None:
        return ""
    root = _resolve_search_result_card_root(card, link_el)
    sels = (
        "div.RBpYLmIg",
        "div[class*='RBpYLmIg']",
        "div.IhSgLL6N",
        "div[class*='IhSgLL6N']",
        "div.LhfUwwlJ",
        "div.ripHDa6N div.LhfUwwlJ",
        "div[class*='ripHDa6N'] div[class*='LhfUwwlJ']",
        "div.search-result-card div.gDk7ywY3 > div:first-child",
        "div[class*='gDk7ywY3'] > div:first-child",
    )
    for sel in sels:
        try:
            for el in root.find_elements(By.CSS_SELECTOR, sel):
                try:
                    tx = (el.text or "").strip()
                    if len(tx) < 2:
                        continue
                    if _text_looks_like_video_duration(tx):
                        continue
                    low = tx.lower()
                    if low in ("@", "分享", "关注"):
                        continue
                    return tx
                except Exception:
                    continue
        except Exception:
            continue
    return ""


def _parse_search_card_caption_near_link(link_el) -> str:
    """从视频链接元素向上找到列表项卡片再取文案（兜底路径与 collect 一致）。"""
    if link_el is None:
        return ""
    for xp in (
        "./ancestor::li[contains(@class,'QdtBFx1O')][1]",
        "./ancestor::div[contains(@class,'search-result-card')][1]",
        "./ancestor::li[1]",
    ):
        try:
            card = link_el.find_element(By.XPATH, xp)
            cap = _parse_search_card_caption(card, link_el)
            if cap:
                return cap
        except Exception:
            continue
    return ""


def _parse_likes_near_element(el) -> int:
    """在锚点祖先容器内尽量找点赞数（多选择器兜底）。"""
    driver = None
    try:
        driver = el.parent
    except Exception:
        pass
    for root in _card_roots_for_likes(None, el):
        v = _parse_likes_from_root(driver, root)
        if v > 0:
            return v
    if driver is not None:
        v = _parse_likes_from_link_js(driver, el)
        if v > 0:
            return v
    root = el
    for xp in (
        "./ancestor::div[contains(@class,'search-result-card')][1]",
        "./ancestor::div[contains(@class,'search-result')][1]",
        "./ancestor::li[1]",
        "./ancestor::article[1]",
    ):
        try:
            root = el.find_element(By.XPATH, xp)
            break
        except Exception:
            continue
    v = _parse_likes_from_root(driver, root)
    if v > 0:
        return v
    for sel in _LIKE_COUNT_SPAN_SELECTORS:
        try:
            for sp in root.find_elements(By.CSS_SELECTOR, sel):
                v = _span_text_to_like_count_strict(_read_like_span_text(sp))
                if v > 0:
                    return v
        except Exception:
            continue
    return 0


def _parse_like_to_int(s: str) -> int:
    if _text_looks_like_video_duration(s) or _text_looks_like_publish_date(s):
        return 0
    s = (s or "").strip().lower().replace(",", "")
    if not s:
        return 0
    m = re.match(r"^(\d+(?:\.\d+)?)(w|万)?$", s)
    if m:
        n = float(m.group(1))
        if m.group(2):
            return int(n * 10000)
        return int(n)
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*(w|万)?", s)
    if m2:
        n = float(m2.group(1))
        if m2.group(2):
            return int(n * 10000)
        return int(n)
    return 0


def _selfcheck_like_parsers() -> None:
    """启动时校验点赞文本解析（不访问浏览器）。"""
    cases = (
        ("1239", 1239),
        ("779", 779),
        ("3.3万", 33000),
        ("1.1w", 11000),
        ("12:34", 0),
        ("2025年3月1日", 0),
    )
    for raw, want in cases:
        got = _parse_like_to_int(raw)
        if got != want:
            raise RuntimeError(f"点赞解析自检失败: {raw!r} -> {got}, 期望 {want}")
        got2 = _span_text_to_like_count_strict(raw)
        if want > 0 and got2 != want:
            raise RuntimeError(f"strict 自检失败: {raw!r} -> {got2}, 期望 {want}")
    logger.info("[SeleniumIntercept] 点赞解析自检通过（1239/3.3万/时长过滤）")


def _batch_parse_search_likes_js(driver: webdriver.Chrome) -> Dict[str, int]:
    """
    整页按列表卡片批量读点赞（与浏览器 DevTools 所见 DOM 一致，比单元素 find 更稳）。
    返回 {video_id: likes_int}。
    """
    try:
        raw = driver.execute_script(
            """
            const re = /^\\d+(\\.\\d+)?(万|w)?$/i;
            const boxSels = [
              '[class*="GiEcbsyC"]', '[class*="pl6nCmrM"]', '[class*="z5UgP5jK"]'
            ];
            const out = {};
            const pickText = (node) => {
              if (!node) return '';
              for (const sel of boxSels) {
                for (const box of node.querySelectorAll(sel)) {
                  const sp = box.querySelector('span');
                  const t = sp ? (sp.textContent || sp.innerText || '').trim() : '';
                  if (t && re.test(t)) return t;
                }
              }
              for (const img of node.querySelectorAll('[class*="videoImage"], [class*="VideoImage"]')) {
                for (const sp of img.querySelectorAll('span')) {
                  const t = (sp.textContent || sp.innerText || '').trim();
                  if (t && re.test(t)) return t;
                }
              }
              return '';
            };
            const roots = document.querySelectorAll('li.QdtBFx1O, div.search-result-card');
            for (const root of roots) {
              const a = root.querySelector('a[href*="/video/"]');
              if (!a) continue;
              const m = (a.href || '').match(/\\/video\\/(\\d+)/);
              if (!m) continue;
              const id = m[1];
              if (out[id]) continue;
              let t = pickText(root);
              if (!t) {
                let p = a.parentElement;
                for (let i = 0; i < 12 && p; i++, p = p.parentElement) {
                  t = pickText(p);
                  if (t) break;
                }
              }
              out[id] = t || '';
            }
            return out;
            """
        )
    except Exception:
        return {}
    result: Dict[str, int] = {}
    if not isinstance(raw, dict):
        return result
    for vid, text in raw.items():
        result[str(vid)] = _parse_like_to_int(str(text or ""))
    return result


def _merge_js_likes_into_cards(
    cards: List[Tuple[str, int, Any, str]], js_likes: Dict[str, int]
) -> List[Tuple[str, int, Any, str]]:
    if not cards or not js_likes:
        return cards
    merged: List[Tuple[str, int, Any, str]] = []
    for href, likes, link, cap in cards:
        vid = _video_id_from_url(href)
        jl = js_likes.get(vid or "", 0)
        if jl > likes:
            likes = jl
        merged.append((href, likes, link, cap))
    return merged


def _log_likes_parse_diagnostics(
    driver: webdriver.Chrome,
    cards: List[Tuple[str, int, Any, str]],
    js_likes: Dict[str, int],
) -> None:
    if not cards:
        return
    if any(lk > 0 for _, lk, _, _ in cards):
        return
    js_pos = sum(1 for v in js_likes.values() if v > 0)
    try:
        diag = driver.execute_script(
            """
            const samples = [];
            document.querySelectorAll(
              '[class*="GiEcbsyC"] span, [class*="pl6nCmrM"] span, [class*="videoImage"] span'
            ).forEach(sp => {
              const t = (sp.textContent || sp.innerText || '').trim();
              if (t && samples.length < 10) samples.push(t);
            });
            return {
              giBoxes: document.querySelectorAll('[class*="GiEcbsyC"]').length,
              plBoxes: document.querySelectorAll('[class*="pl6nCmrM"]').length,
              listRoots: document.querySelectorAll('li.QdtBFx1O, div.search-result-card').length,
              videoLinks: document.querySelectorAll('a[href*="/video/"]').length,
              samples,
            };
            """
        )
        logger.warning(
            f"[SeleniumIntercept] 列表点赞解析全为0（Selenium+JS批量均未读到正数；"
            f"JS映射{len(js_likes)}条其中>0有{js_pos}条）DOM诊断={diag}。"
            f"若页面上肉眼可见赞数，请发 list_no_pick 截图与完整日志。"
        )
    except Exception as e:
        logger.warning(
            f"[SeleniumIntercept] 列表点赞全0（JS映射{len(js_likes)}条，DOM诊断失败: {e}）"
        )


def _fill_template(template_text: str, vars_map: Dict[str, str]) -> str:
    out = template_text
    for k, v in vars_map.items():
        out = out.replace("${" + k + "}", v or "")
    return out


def _empty_persona_kb() -> Dict[str, str]:
    return {
        "priceRange": "",
        "wechatId": "",
        "companyName": "",
        "serviceRegion": "",
        "targetAudience": "",
        "companyAddress": "",
        "businessYear": "",
        "keyFeatures": "",
        "relatedNotes": "",
        "industryKeywords": "",
        "commentExample": "",
        "intentKeywordsCustom": "",
    }


def _load_persona_from_config() -> Dict[str, str]:
    """与 hf_auto_reply._load_persona_from_config 字段一致，供豆包模板填充。"""
    b = _empty_persona_kb()
    if yaml is None:
        return b
    p = THIS_DIR / "config.yaml"
    if not p.exists():
        return b
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        persona = data.get("persona", {}) if isinstance(data, dict) else {}
        if not isinstance(persona, dict):
            return b
        b["priceRange"] = str(persona.get("price_range", "") or "")
        b["wechatId"] = str(persona.get("wechat_id", "") or "")
        b["companyName"] = str(persona.get("company_name", "") or "")
        b["serviceRegion"] = str(persona.get("service_region", "") or "")
        b["targetAudience"] = str(persona.get("target_audience", "") or "")
        b["companyAddress"] = str(persona.get("company_address", "") or "")
        b["businessYear"] = str(persona.get("business_year", "") or "")
        b["keyFeatures"] = str(persona.get("key_features", "") or "")
        b["relatedNotes"] = str(persona.get("related_notes", "") or "")
        b["industryKeywords"] = str(persona.get("industry_keywords", "") or "")
        b["commentExample"] = str(persona.get("comment_example", "") or "")
        b["intentKeywordsCustom"] = str(persona.get("intent_keywords", "") or "")
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 读取 config.yaml persona 失败，使用空人设: {e}")
    return b


def _apply_persona_overlay_json(persona_kb: Dict[str, str], path: str) -> Dict[str, str]:
    """将 JSON 对象中非空字符串合并进人设（键与 _empty_persona_kb 一致）。"""
    raw = (path or "").strip()
    if not raw:
        return persona_kb
    fp = Path(raw)
    if not fp.is_file():
        logger.warning(f"[SeleniumIntercept] persona overlay 文件不存在，忽略: {fp}")
        return persona_kb
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 读取 persona overlay JSON 失败: {e}")
        return persona_kb
    if not isinstance(data, dict):
        return persona_kb
    out = dict(persona_kb)
    for k, v in data.items():
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out[str(k)] = s
    return out


def _finalize_dm_body(raw: Optional[str], fallback: str) -> str:
    if not raw:
        return fallback
    s = raw.strip()
    s = s.strip(" \t\r\n\"'「」")
    for line in s.splitlines():
        t = line.strip()
        if t:
            s = t
            break
    if len(s) > 320:
        s = s[:320].rstrip()
    return s or fallback


def _finalize_comment_body(raw: Optional[str], fallback: str) -> str:
    if not raw:
        return fallback
    s = raw.strip()
    s = s.strip(" \t\r\n\"'「」")
    for line in s.splitlines():
        t = line.strip()
        if t:
            s = t
            break
    if len(s) > 80:
        s = s[:80].rstrip()
    return s or fallback


def _persona_intent_keyword_tokens(persona_kb: Optional[Dict[str, str]] = None) -> List[str]:
    raw = ""
    if persona_kb:
        raw = (persona_kb.get("intentKeywordsCustom") or "").strip()
    out: List[str] = []
    if raw:
        for p in re.split(r"[/|，,、\s\n]+", raw):
            s = p.strip()
            if len(s) >= 1:
                out.append(s)
    return out


def _is_intent_comment(text: str, persona_kb: Optional[Dict[str, str]] = None) -> bool:
    """评论是否含意向词：内置 INTENT_KEYWORDS + config persona.intent_keywords（/ 或逗号分隔）。"""
    t = (text or "").strip().lower()
    if not t:
        return False
    keys = list(INTENT_KEYWORDS)
    keys.extend(_persona_intent_keyword_tokens(persona_kb))
    seen: Set[str] = set()
    uniq: List[str] = []
    for k in keys:
        lk = k.strip().lower()
        if not lk or lk in seen:
            continue
        seen.add(lk)
        uniq.append(k.strip())
    return any(k.lower() in t for k in uniq)


def _load_profile_dir_from_config() -> str:
    if yaml is None:
        return "Profile 3"
    p = THIS_DIR / "config.yaml"
    if not p.exists():
        return "Profile 3"
    try:
        with open(p, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return (cfg.get("browser") or {}).get("profile_directory") or "Profile 3"
    except Exception:
        return "Profile 3"


def _append_jsonl(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _industry_keyword_sequence(persona_kb: Dict[str, str], cli_fallback: str) -> List[str]:
    """persona.industry_keywords 用 / 或 | 或中英文逗号分隔；空则用 CLI --keyword。"""
    raw = (persona_kb.get("industryKeywords") or "").strip()
    if raw:
        parts = [p.strip() for p in re.split(r"[/|，,、]+", raw) if p.strip()]
        if parts:
            return parts
    fb = (cli_fallback or "").strip()
    return [fb] if fb else ["不锈钢门窗"]


def _keyword_rotation_fingerprint(seq: List[str]) -> str:
    return hashlib.md5("|".join(seq).encode("utf-8")).hexdigest()


def _load_rotation_next_start(path: Path, fingerprint: str, n: int) -> int:
    if n <= 0:
        return 0
    if not path.exists():
        return 0
    try:
        o = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        if str(o.get("fingerprint") or "") != fingerprint:
            return 0
        return int(o.get("next_start", 0)) % n
    except Exception:
        return 0


def _save_rotation_next_start(path: Path, fingerprint: str, next_start: int, n: int) -> None:
    if n <= 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ns = next_start % n
    path.write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "next_start": ns,
                "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _log_today_comment_exposure(comment_log: Path, day: str) -> None:
    """播放量/曝光暂停对接：仅汇总当日成功评论条数，播放量按 0 计。"""
    n_ok = count_comment_success_on_date(comment_log, day)
    logger.info(
        f"[SeleniumIntercept] 今日已成功评论 {n_ok} 条；播放量/曝光未对接，合计按 0 计"
    )


def load_lifetime_dm_user_ids(dm_path: Path) -> Set[str]:
    """已成功私信的用户（jsonl 中每一行均视为已成功，兼容旧数据）。"""
    s: Set[str] = set()
    if not dm_path.exists():
        return s
    for line in dm_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
            uid = _normalize_user_id(str(o.get("user_id") or ""))
            if not uid:
                continue
            if o.get("success") is False:
                continue
            s.add(uid)
        except Exception:
            continue
    return s


def count_dm_success_on_date(dm_path: Path, day: str) -> int:
    c = 0
    if not dm_path.exists():
        return 0
    for line in dm_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
            if o.get("success") is False:
                continue
            ts = str(o.get("ts") or "")
            if ts[:10] == day[:10]:
                c += 1
        except Exception:
            continue
    return c


def load_commented_video_ids(comment_log: Path) -> Set[str]:
    s: Set[str] = set()
    if not comment_log.exists():
        return s
    for line in comment_log.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
            if o.get("success") is False:
                continue
            vid = str(o.get("video_id") or "")
            if vid:
                s.add(vid)
        except Exception:
            continue
    return s


def count_comment_success_on_date(comment_log: Path, day: str) -> int:
    c = 0
    if not comment_log.exists():
        return 0
    for line in comment_log.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
            if o.get("success") is False:
                continue
            ts = str(o.get("ts") or "")
            if ts[:10] == day[:10]:
                c += 1
        except Exception:
            continue
    return c


def _doubao_call(messages: List[Dict[str, str]], temperature: float, timeout_s: int = 55) -> Optional[str]:
    try:
        return doubao_chat_completion(messages, temperature=temperature, timeout_s=timeout_s)
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 豆包失败: {e}")
        return None


def ai_intent_doubao_second_pass(comment_text: str, keyword: str) -> bool:
    """
    在已命中关键词意向后，用豆包二次判断是否真意向（需 PROMPT_INTENT_DECISION）。
    失败或含糊时偏保守返回 False。
    """
    if not PROMPT_INTENT_DECISION.exists():
        logger.warning(f"[SeleniumIntercept] 缺少意向判定提示词: {PROMPT_INTENT_DECISION}，二阶段跳过")
        return True
    prompt = PROMPT_INTENT_DECISION.read_text(encoding="utf-8", errors="ignore")
    filled = _fill_template(
        prompt,
        {"commentText": (comment_text or "").strip()[:800], "keyword": (keyword or "").strip()},
    )
    out = _doubao_call(
        [
            {"role": "system", "content": "你必须只输出一个字：是 或 不是。"},
            {"role": "user", "content": filled},
        ],
        temperature=0.0,
        timeout_s=35,
    )
    s = (out or "").strip()
    if not s:
        return False
    if "不是" in s or s in ("否", "否。"):
        return False
    if s == "是" or s.startswith("是"):
        return True
    if "是" in s and "不是" not in s:
        return True
    return False


def build_dm_text(
    comment_snippet: str,
    use_doubao: bool,
    fixed_dm: str,
    *,
    keyword: str = "",
    list_caption: str = "",
    persona: Optional[Dict[str, str]] = None,
) -> str:
    if USE_TEMP_INPUT_666:
        return TEMP_INPUT_TEXT
    if not use_doubao:
        return fixed_dm
    if not PROMPT_DM.exists():
        logger.warning(f"[SeleniumIntercept] 缺少私信提示词文件: {PROMPT_DM}，使用 --fixed-dm")
        return fixed_dm
    kb = persona if persona is not None else _load_persona_from_config()
    scene = (
        "截流-主动首条私信：对方尚未给您发过私信；您是因为看到对方在某条抖音视频评论区里的留言，"
        "才进入对方主页并发送这第一条私信。请按提示词写可发送正文。"
    )
    um_parts = [
        f"本次搜索关键词：{keyword}" if (keyword or "").strip() else "",
        f"该视频在搜索结果列表上的主文案（标题+#话题，可能不完整）：{list_caption.strip()}"
        if (list_caption or "").strip()
        else "",
        "",
        "对方在视频下的评论（理解需求用）：",
        (comment_snippet or "").strip()[:520],
    ]
    user_message = "\n".join(x for x in um_parts if x is not None and str(x).strip() != "")
    persona_vars = {
        "interceptScene": scene,
        "userMessage": user_message,
        "chatHistory": "",
        "nickname": "",
        "priceRange": kb.get("priceRange", ""),
        "wechatId": kb.get("wechatId", ""),
        "companyName": kb.get("companyName", ""),
        "serviceRegion": kb.get("serviceRegion", ""),
        "targetAudience": kb.get("targetAudience", ""),
        "companyAddress": kb.get("companyAddress", ""),
        "businessYear": kb.get("businessYear", ""),
        "keyFeatures": kb.get("keyFeatures", ""),
        "relatedNotes": kb.get("relatedNotes", ""),
    }
    dm_prompt = PROMPT_DM.read_text(encoding="utf-8", errors="ignore")
    filled = _fill_template(dm_prompt, persona_vars)
    dm_text = _doubao_call(
        [
            {
                "role": "system",
                "content": "你严格按用户消息里的任务与规则生成内容，只输出一段可直接发送的中文私信正文，不要标题、引号或解释。",
            },
            {"role": "user", "content": filled},
        ],
        temperature=0.65,
    )
    out = _finalize_dm_body(dm_text, fixed_dm)
    if not (dm_text or "").strip():
        logger.warning("[SeleniumIntercept] 豆包未返回有效私信文案，使用 --fixed-dm")
    return out


def build_comment_text(
    keyword: str,
    use_doubao: bool,
    fixed_comment: str,
    *,
    list_caption: str = "",
    intent_snippet: str = "",
    persona: Optional[Dict[str, str]] = None,
) -> str:
    if USE_TEMP_INPUT_666:
        return TEMP_INPUT_TEXT
    if not use_doubao:
        return fixed_comment
    if not PROMPT_COMMENT.exists():
        logger.warning(f"[SeleniumIntercept] 缺少评论提示词文件: {PROMPT_COMMENT}，使用 --fixed-comment")
        return fixed_comment
    kb = persona if persona is not None else _load_persona_from_config()
    vars2 = {
        "videoTitle": (list_caption or "").strip()[:400],
        "videoDesc": "",
        "keyword": (keyword or "").strip(),
        "intentSnippet": (intent_snippet or "").strip()[:400],
        "priceRange": kb.get("priceRange", ""),
        "companyName": kb.get("companyName", ""),
        "serviceRegion": kb.get("serviceRegion", ""),
        "targetAudience": kb.get("targetAudience", ""),
        "businessYear": kb.get("businessYear", ""),
        "keyFeatures": kb.get("keyFeatures", ""),
        "relatedNotes": kb.get("relatedNotes", ""),
        "commentExample": (kb.get("commentExample") or "").strip()[:600],
    }
    c_prompt = PROMPT_COMMENT.read_text(encoding="utf-8", errors="ignore")
    filled = _fill_template(c_prompt, vars2)
    c_text = _doubao_call(
        [
            {
                "role": "system",
                "content": "你严格按用户消息里的任务与规则生成内容，只输出一句中文评论正文，不要标题、引号或解释。",
            },
            {"role": "user", "content": filled},
        ],
        temperature=0.72,
    )
    out = _finalize_comment_body(c_text, fixed_comment)
    if not (c_text or "").strip():
        logger.warning("[SeleniumIntercept] 豆包未返回有效评论文案，使用 --fixed-comment")
    return out


def _wait_new_window(driver: webdriver.Chrome, before: List[str], timeout: float = 12.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        after = driver.window_handles
        if len(after) > len(before):
            return True
        time.sleep(0.2)
    return False


def _switch_to_newest(driver: webdriver.Chrome) -> None:
    driver.switch_to.window(driver.window_handles[-1])


def _safe_screenshot(driver: webdriver.Chrome, name: str) -> None:
    try:
        p = ART_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{name}.png"
        driver.save_screenshot(str(p))
        logger.info(f"[SeleniumIntercept] 截图 {p}")
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 截图失败: {e}")


def _chrome_singleton_lock_hint(user_data_dir: Path, profile_dir: str) -> None:
    """Chrome 未退干净时常见根目录 SingletonLock，会导致启动长时间无响应。"""
    root = user_data_dir.resolve()
    candidates = [root / "SingletonLock", root / "SingletonSocket", root / "SingletonCookie"]
    pd_name = (profile_dir or "").strip()
    if pd_name:
        pd = (root / pd_name).resolve()
        if pd.is_dir():
            candidates.extend([pd / "SingletonLock", pd / "SingletonCookie"])
    found = [p for p in candidates if p.exists()]
    if found:
        logger.warning(
            "[SeleniumIntercept] 检测到用户数据目录下仍有锁文件（说明很可能还有 Chrome 进程占着该 Profile）："
            + ", ".join(str(p) for p in found[:5])
            + " — 请在任务管理器中结束所有 chrome.exe / Google Chrome 后再运行脚本。"
        )


def _resolve_intercept_chrome_binary() -> str:
    env_bin = (os.environ.get("INTERCEPT_CHROME_BINARY") or "").strip()
    if env_bin and Path(env_bin).is_file():
        return env_bin
    system_paths = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    for p in system_paths:
        if p.is_file():
            return str(p.resolve())
    try:
        from douyin_publish_mcp import load_browser_config

        cfg = load_browser_config() or {}
        cp = (cfg.get("chrome_path") or "").strip()
        if cp:
            cp_path = Path(cp)
            if not cp_path.is_absolute():
                cp_path = THIS_DIR.parent / cp
            if cp_path.is_file():
                return str(cp_path.resolve())
    except Exception:
        pass
    bundled = THIS_DIR.parent / "env" / "chrome" / "chrome.exe"
    if bundled.is_file():
        return str(bundled.resolve())
    return ""


def _resolve_intercept_chromedriver_path() -> str:
    try:
        from douyin_publish_mcp import get_chromedriver_path

        p = get_chromedriver_path()
        if p and Path(p).is_file():
            return str(Path(p).resolve())
    except Exception:
        pass
    bundled = THIS_DIR.parent / "env" / "chromedriver" / "chromedriver.exe"
    if bundled.is_file():
        return str(bundled.resolve())
    return ""


def create_driver(user_data_dir: Path, profile_dir: str, headless: bool) -> webdriver.Chrome:
    udir = user_data_dir.resolve()
    _chrome_singleton_lock_hint(udir, profile_dir)
    opts = Options()
    opts.add_argument(f"--user-data-dir={udir}")
    opts.add_argument(f"--profile-directory={profile_dir}")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1400,900")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        dbg_port = s.getsockname()[1]
        s.close()
        opts.add_argument(f"--remote-debugging-port={dbg_port}")
    except Exception:
        pass
    if headless:
        opts.add_argument("--headless=new")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_bin = _resolve_intercept_chrome_binary()
    if chrome_bin:
        opts.binary_location = chrome_bin
        logger.info(f"[SeleniumIntercept] Chrome 二进制: {chrome_bin}")

    def _launch(service: Service) -> webdriver.Chrome:
        logger.info(
            "[SeleniumIntercept] 正在创建浏览器会话（此处若超过 2～3 分钟无下文，多为 Profile 未释放或驱动在下载）…"
        )
        d = webdriver.Chrome(service=service, options=opts)
        d.set_page_load_timeout(60)
        return d

    bundled_drv = _resolve_intercept_chromedriver_path()
    if bundled_drv:
        logger.info(f"[SeleniumIntercept] 优先使用内置 ChromeDriver: {bundled_drv}")
        try:
            return _launch(Service(executable_path=bundled_drv))
        except SessionNotCreatedException as e:
            logger.warning(f"[SeleniumIntercept] 内置 ChromeDriver 启动失败，尝试其它来源: {e}")

    wdm_first = (os.environ.get("INTERCEPT_WDM_FIRST", "0") or "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    if wdm_first:
        try:
            from webdriver_manager.chrome import ChromeDriverManager

            drv_path = ChromeDriverManager().install()
            logger.info(f"[SeleniumIntercept] 使用 webdriver-manager 驱动: {drv_path}")
            return _launch(Service(executable_path=drv_path))
        except ImportError:
            logger.info("[SeleniumIntercept] 未安装 webdriver-manager，改用 Selenium 自带驱动解析…")
        except Exception as e:
            logger.warning(f"[SeleniumIntercept] webdriver-manager 不可用，回退 Selenium 默认驱动: {e}")

    try:
        return _launch(Service())
    except SessionNotCreatedException as e:
        logger.warning(
            "[SeleniumIntercept] Chrome 未能创建会话（常见原因：①已有 Chrome 占用同一 user-data-dir/Profile；"
            "②Chrome 与 ChromeDriver 主版本不一致）。"
            f" user-data-dir={udir}"
        )
        try:
            from webdriver_manager.chrome import ChromeDriverManager

            drv_path = ChromeDriverManager().install()
            logger.info(f"[SeleniumIntercept] 已用 webdriver-manager 驱动: {drv_path}")
            return _launch(Service(executable_path=drv_path))
        except ImportError:
            logger.error(
                "[SeleniumIntercept] 未安装 webdriver-manager，无法自动拉取匹配驱动。"
                "请执行: py -m pip install webdriver-manager"
            )
            raise
        except SessionNotCreatedException as e2:
            logger.error(
                "[SeleniumIntercept] 换用自动驱动后仍失败：几乎肯定是 Profile 被占用。"
                "请完全退出 Chrome（任务管理器结束 chrome.exe）后再运行；"
                "或设置环境变量 INTERCEPT_CHROME_BINARY 指向本机 chrome.exe。"
            )
            raise e2 from e


def find_first(driver: webdriver.Chrome, by: By, sel: str, timeout: float = 8.0):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, sel)))


def find_clickable(driver: webdriver.Chrome, by: By, sel: str, timeout: float = 8.0):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, sel)))


def open_search(driver: webdriver.Chrome, keyword: str) -> None:
    driver.get("https://www.douyin.com/")
    _rand_sleep(1.2, 2.0)
    inp = find_first(driver, By.CSS_SELECTOR, 'input[data-e2e="searchbar-input"]', 15)
    inp.clear()
    time.sleep(0.2)
    inp.send_keys(keyword)
    inp.send_keys(Keys.ENTER)
    # 等跳到搜索结果页（否则「视频/筛选」可能未渲染）
    try:
        WebDriverWait(driver, 20).until(
            lambda d: ("search" in (d.current_url or "").lower())
            or bool(d.find_elements(By.CSS_SELECTOR, 'span[data-key="video"]'))
        )
    except TimeoutException:
        logger.warning("[SeleniumIntercept] 等待搜索页超时，仍尝试点「视频」…")
    _rand_sleep(1.2, 2.0)


def _find_visible_filter_trigger(driver: webdriver.Chrome):
    """定位「筛选」触发器：需悬停/点击后才会出现「最新发布」「半年内」。"""
    xps = [
        "//span[contains(@class,'mGU8JlJS')][contains(normalize-space(),'筛选')]",
        "//span[normalize-space()='筛选']",
        "//div[contains(@class,'mGU8JlJS')][contains(normalize-space(),'筛选')]",
        "//*[contains(normalize-space(),'筛选')][not(contains(normalize-space(),'筛选结果'))]",
    ]
    best = None
    best_score = -1
    for xp in xps:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if not el.is_displayed():
                        continue
                    tx = (el.text or el.get_attribute("innerText") or "").strip()
                    if "筛选" not in tx:
                        continue
                    if "筛选结果" in tx:
                        continue
                    score = 3 if tx == "筛选" else 2 if len(tx) <= 6 else 1
                    if score > best_score:
                        best_score = score
                        best = el
                except StaleElementReferenceException:
                    continue
        except Exception:
            continue
    return best


def _click_filter_option(driver: webdriver.Chrome, label: str) -> bool:
    """点击筛选项：先精确文案，再 data-index 兜底。"""
    label = label.strip()
    xpath_text = (
        f"//span[normalize-space()='{label}'] | "
        f"//div[normalize-space()='{label}'] | "
        f"//*[self::span or self::div][contains(normalize-space(),'{label}')]"
    )
    try:
        el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath_text)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.15)
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)
        logger.info(f"[SeleniumIntercept] 已点击筛选项: {label}")
        return True
    except TimeoutException:
        pass
    # data-index 兜底（与你抓的 DOM 一致）
    fallback_css = {
        "最新发布": 'span[data-index1="0"][data-index2="1"]',
        "半年内": 'span[data-index1="1"][data-index2="3"]',
    }
    css = fallback_css.get(label)
    if css:
        try:
            el = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            el.click()
            logger.info(f"[SeleniumIntercept] 已点击筛选项(data-index): {label}")
            return True
        except Exception as e:
            logger.warning(f"[SeleniumIntercept] 筛选项 {label} data-index 兜底失败: {e}")
    logger.warning(f"[SeleniumIntercept] 未能点击筛选项: {label}")
    _safe_screenshot(driver, f"filter_miss_{label}")
    return False


def _wait_filter_popover_ready(driver: webdriver.Chrome, timeout: float = 18.0) -> bool:
    """
    点「筛选」后等悬浮层：同时存在可见的「最新发布」「半年内」节点（优先 data-index）。
    不需要等很久，但必须在弹层渲染后再点，否则会点空或点到错误层。
    """
    css_latest = 'span[data-index1="0"][data-index2="1"]'
    css_half = 'span[data-index1="1"][data-index2="3"]'

    def _visible_pair(d: webdriver.Chrome) -> bool:
        try:
            for a in d.find_elements(By.CSS_SELECTOR, css_latest):
                if a.is_displayed():
                    for b in d.find_elements(By.CSS_SELECTOR, css_half):
                        if b.is_displayed():
                            return True
        except Exception:
            pass
        return False

    try:
        WebDriverWait(driver, timeout).until(lambda d: _visible_pair(d))
        logger.info("[SeleniumIntercept] 筛选悬浮层已出现（可见：最新发布 + 半年内）")
        return True
    except TimeoutException:
        return False


def _click_visible_filter_span(driver: webdriver.Chrome, css: str, name: str) -> bool:
    """在同一悬浮层内点击：只点当前可见的节点，优先 JS click。"""
    try:
        targets = [e for e in driver.find_elements(By.CSS_SELECTOR, css) if e.is_displayed()]
    except Exception:
        targets = []
    for el in targets:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.12)
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            logger.info(f"[SeleniumIntercept] 已在悬浮层点击: {name}")
            return True
        except StaleElementReferenceException:
            continue
        except Exception:
            continue
    return False


def _visible_search_video_link_count(driver: webdriver.Chrome) -> int:
    """当前页面上可见的「视频详情」链接数量（用于等筛选后列表异步刷出）。"""
    n = 0
    try:
        for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]'):
            try:
                if not a.is_displayed():
                    continue
                href = (a.get_attribute("href") or "").lower()
                if "/video/" not in href:
                    continue
                n += 1
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
    except Exception:
        pass
    return n


def _wait_search_results_after_filter(
    driver: webdriver.Chrome, min_links: int = 1, timeout: float = 25.0
) -> bool:
    """筛选并收起浮层后，列表常异步刷新，需等待可见视频链接出现。"""
    logger.info(
        f"[SeleniumIntercept] 等待搜索结果渲染（至少 {min_links} 条可见 /video/ 链接，最长 {int(timeout)}s）…"
    )
    try:
        WebDriverWait(driver, timeout).until(lambda d: _visible_search_video_link_count(d) >= min_links)
        logger.info(f"[SeleniumIntercept] 已检测到可见视频链接（约 {_visible_search_video_link_count(driver)} 条）")
        return True
    except TimeoutException:
        logger.warning(
            f"[SeleniumIntercept] {int(timeout)}s 内可见视频链接仍不足 {min_links}，仍将尝试 collect_video_cards"
        )
        return False


def _dismiss_filter_popover(driver: webdriver.Chrome) -> None:
    """
    选完「最新发布」「半年内」后，筛选浮层常仍展开，会挡住下方视频列表的可见区域/交互。
    再点一次「筛选」一般为开关，可收起；并尝试 ESC 兜底。
    """
    try:
        filt = _find_visible_filter_trigger(driver)
        if filt is None:
            return
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", filt)
        time.sleep(0.15)
        try:
            filt.click()
        except Exception:
            driver.execute_script("arguments[0].click();", filt)
        logger.info("[SeleniumIntercept] 已再次点击「筛选」以收起悬浮层（便于抓取视频列表）")
        time.sleep(0.5)
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 收起筛选浮层失败: {e}")
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.25)
    except Exception:
        pass


def _open_filter_panel(driver: webdriver.Chrome, filt_el) -> bool:
    """展开筛选悬浮层（悬停 + 点击 + 必要时 JS 再点一次）。"""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", filt_el)
        time.sleep(0.2)
        ActionChains(driver).move_to_element(filt_el).pause(0.5).click().perform()
        logger.info("[SeleniumIntercept] 已点击「筛选」（展开悬浮层）")
        if _wait_filter_popover_ready(driver, 12.0):
            return True
        # 再试一次：有的页面第一次只 focus，第二次才出层
        driver.execute_script("arguments[0].click();", filt_el)
        time.sleep(0.35)
        if _wait_filter_popover_ready(driver, 10.0):
            return True
        logger.warning("[SeleniumIntercept] 点击「筛选」后悬浮层仍未就绪（可观察是否需人工先点一次页面）")
        _safe_screenshot(driver, "filter_popover_timeout")
        return False
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 展开「筛选」失败: {e}")
        _safe_screenshot(driver, "filter_open_fail")
        return False


def apply_video_filters(driver: webdriver.Chrome) -> None:
    try:
        tab = find_clickable(driver, By.CSS_SELECTOR, 'span[data-key="video"]', 15)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
        time.sleep(0.2)
        tab.click()
        logger.info("[SeleniumIntercept] 已点击「视频」Tab")
        _rand_sleep(1.0, 1.6)
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 点击「视频」Tab 失败: {e}")
        _safe_screenshot(driver, "video_tab_fail")

    filt = _find_visible_filter_trigger(driver)
    if filt is None:
        logger.warning("[SeleniumIntercept] 未找到「筛选」入口")
        _safe_screenshot(driver, "no_filter_trigger")
        return

    if not _open_filter_panel(driver, filt):
        # 悬浮层未出现时不强行点「最新/半年内」，避免误点页面其它区域
        return

    # 关键：「最新发布」「半年内」在同一次弹出的悬浮层里依次点，中间不要再点「筛选」
    # （再点「筛选」会关掉弹层，导致「半年内」点不到，看起来像元素不稳定）
    css_latest = 'span[data-index1="0"][data-index2="1"]'
    css_half = 'span[data-index1="1"][data-index2="3"]'

    ok_latest = _click_visible_filter_span(driver, css_latest, "最新发布")
    if not ok_latest:
        ok_latest = _click_filter_option(driver, "最新发布")
    time.sleep(0.35)

    ok_half = _click_visible_filter_span(driver, css_half, "半年内")
    if not ok_half:
        ok_half = _click_filter_option(driver, "半年内")

    # 若点完「最新」后弹层被收起，再单独补一轮「半年内」
    if not ok_half:
        logger.info("[SeleniumIntercept] 「半年内」首次未成功，尝试重新展开筛选后只点「半年内」")
        filt2 = _find_visible_filter_trigger(driver)
        if filt2 is not None and _open_filter_panel(driver, filt2):
            ok_half = _click_visible_filter_span(driver, css_half, "半年内")
            if not ok_half:
                ok_half = _click_filter_option(driver, "半年内")

    if not ok_half:
        _safe_screenshot(driver, "filter_halfyear_fail")

    _rand_sleep(0.8, 1.2)
    # 收起浮层后再抓列表（用户反馈：浮窗未下去时列表采不到）
    _dismiss_filter_popover(driver)
    _rand_sleep(0.6, 1.0)
    try:
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.2)
        driver.execute_script("window.scrollBy(0, 320);")
        time.sleep(0.35)
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass

    # 筛选后列表多为异步刷新：先固定缓冲 1～2 秒，再等可见 /video/ 链接（最长约 25s）
    time.sleep(2.0)
    _wait_search_results_after_filter(driver, min_links=1, timeout=25.0)

    logger.info(
        f"[SeleniumIntercept] 筛选流程结束：最新发布={ok_latest} 半年内={ok_half}；"
        f"已收起浮层、滚动并等待列表渲染"
    )


def _scroll_search_results_page(driver: webdriver.Chrome, px: int = 850) -> None:
    """搜索列表首屏可能没有足够高赞视频，需向下滚动加载更多卡片。"""
    try:
        driver.execute_script("window.scrollBy(0, arguments[0]);", px)
    except Exception:
        pass
    try:
        for sel in ('[class*="search-result"]', "[class*='SearchResult']", "main"):
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                driver.execute_script("arguments[0].scrollTop += arguments[1];", el, px)
            except Exception:
                continue
    except Exception:
        pass
    time.sleep(0.5)


def find_search_list_video_link(driver: webdriver.Chrome, video_id: str):
    """在搜索列表中按 vid 重新定位可点击链（滚动后须刷新 element，避免 Stale）。"""
    ev = (video_id or "").strip()
    if not ev:
        return None
    for root_sel in ("div.search-result-card", "li.QdtBFx1O"):
        try:
            for card in driver.find_elements(By.CSS_SELECTOR, root_sel):
                try:
                    link = card.find_element(By.CSS_SELECTOR, f'a[href*="/video/{ev}"]')
                    if link.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
                        _rand_sleep(0.2, 0.45)
                        return link
                except Exception:
                    continue
        except Exception:
            continue
    try:
        for link in driver.find_elements(By.CSS_SELECTOR, f'a[href*="/video/{ev}"]'):
            try:
                if link.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
                    _rand_sleep(0.2, 0.45)
                    return link
            except Exception:
                continue
    except Exception:
        pass
    return None


def _link_sort_position(link_el) -> Tuple[float, float]:
    try:
        loc = link_el.location
        return (float(loc.get("y", 0)), float(loc.get("x", 0)))
    except Exception:
        return (0.0, 0.0)


def pick_next_video_by_list_order(
    driver: webdriver.Chrome,
    processed_videos: Set[str],
    min_likes: int,
    *,
    max_scroll_rounds: int,
    scroll_px: int,
    no_new_streak_max: int,
) -> Optional[Tuple[str, int, str, Any, str]]:
    """
    边下滑边在「当前已加载列表」里按自上而下顺序选下一条：第一个未处理且达 min_likes 的视频。
    同一屏上 49、89、24 会依次进，不会先跳到后面全局最高赞。
    返回: (href, likes, vid, link_el, list_caption)。
    list_caption 为列表卡片主文案（标题+#话题），供后续 AI 评论等使用。
    """
    seen_vids: Set[str] = set()
    no_new_streak = 0
    last_cards: List[Tuple[str, int, Any, str]] = []

    for _round_i in range(max(1, max_scroll_rounds)):
        cards = collect_video_cards(driver)
        last_cards = cards
        new_id_this_round = False
        for href, likes, el, _cap in cards:
            vid = _video_id_from_url(href)
            if vid and vid not in seen_vids:
                seen_vids.add(vid)
                new_id_this_round = True

        ordered: List[Tuple[Tuple[float, float], str, int, str, Any, str]] = []
        for href, likes, el, caption in cards:
            vid = _video_id_from_url(href)
            if not vid or vid in processed_videos:
                continue
            if not _meets_min_likes(likes, min_likes):
                continue
            ordered.append((_link_sort_position(el), href, likes, vid, el, caption))
        ordered.sort(key=lambda t: (t[0][0], t[0][1], t[3]))

        for _pos, href, likes, vid, _el, caption in ordered:
            link = find_search_list_video_link(driver, vid)
            if link is not None:
                cap = (caption or "").strip()
                if not cap:
                    cap = _parse_search_card_caption_near_link(link)
                logger.info(
                    f"[SeleniumIntercept] 按列表自上而下选中下一条: vid={vid} likes={likes} "
                    f"（当前已见 {len(seen_vids)} 个去重 vid）"
                )
                return (href, likes, vid, link, cap)

        if not new_id_this_round:
            no_new_streak += 1
        else:
            no_new_streak = 0

        if no_new_streak >= no_new_streak_max:
            logger.info(
                f"[SeleniumIntercept] 连续 {no_new_streak_max} 轮无新视频 id，停止下滑 "
                f"（累计见过 {len(seen_vids)} 个去重 vid）"
            )
            break

        _scroll_search_results_page(driver, px=scroll_px)
        _rand_sleep(0.45, 0.85)

    if last_cards:
        sample = [(_video_id_from_url(h), lk) for h, lk, _, _c in last_cards[:10]]
        logger.info(
            f"[SeleniumIntercept] 列表到底或无可选：min_likes={min_likes} "
            f"已处理/跳过 {len(processed_videos)} 条 示例(vid,likes)={sample}"
        )
    return None


def collect_video_cards(driver: webdriver.Chrome) -> List[Tuple[str, int, Any, str]]:
    """
    返回 [(video_url, likes, element_for_click, list_caption), ...]
    element 用于点击打开视频（尽量点 a 标签）。
    list_caption 为卡片内主文案（多为标题+#话题），与点赞同属一张卡。
    """
    out: List[Tuple[str, int, Any, str]] = []
    seen: Set[str] = set()
    js_likes = _batch_parse_search_likes_js(driver)
    if js_likes:
        pos = sum(1 for v in js_likes.values() if v > 0)
        logger.info(
            f"[SeleniumIntercept] JS批量点赞映射 {len(js_likes)} 条，其中 >0 共 {pos} 条"
        )
    # 从视频页返回列表后，偶发需再等一小会儿
    if _visible_search_video_link_count(driver) == 0:
        time.sleep(1.2)
        _wait_search_results_after_filter(driver, min_links=1, timeout=8.0)
        js_likes = _batch_parse_search_likes_js(driver) or js_likes

    # 优先按「视频链接」采集：避免嵌套 search-result-card 空壳导致点赞全为 0
    link_scoped = (
        "div.search-result-card a[href*='/video/'], "
        "li.QdtBFx1O a[href*='/video/']"
    )
    try:
        for link in driver.find_elements(By.CSS_SELECTOR, link_scoped):
            try:
                if not link.is_displayed():
                    continue
                href = (link.get_attribute("href") or "").strip()
                if "/video/" not in href:
                    continue
                vid = _video_id_from_url(href)
                if not vid or vid in seen:
                    continue
                likes = _parse_likes_from_search_card(None, link)
                cap = _parse_search_card_caption(None, link)
                seen.add(vid)
                out.append((href, likes, link, cap))
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
    except Exception:
        pass

    if out:
        out = _merge_js_likes_into_cards(out, js_likes)
        _log_likes_parse_diagnostics(driver, out, js_likes)
        logger.info(f"[SeleniumIntercept] collect_video_cards 得到 {len(out)} 条（按 video_id 去重）")
        return out

    cards_sr: List[Any] = []
    cards_li: List[Any] = []
    try:
        cards_sr = driver.find_elements(By.CSS_SELECTOR, "div.search-result-card")
    except Exception:
        pass
    try:
        cards_li = driver.find_elements(By.CSS_SELECTOR, "li.QdtBFx1O")
    except Exception:
        pass
    cards = cards_sr if cards_sr else cards_li

    for card in cards:
        try:
            link = None
            try:
                link = card.find_element(By.CSS_SELECTOR, 'a[href*="/video/"]')
            except NoSuchElementException:
                continue
            href = link.get_attribute("href") or ""
            if "/video/" not in href:
                continue
            vid = _video_id_from_url(href)
            if not vid or vid in seen:
                continue
            likes = _parse_likes_from_search_card(card, link)
            cap = _parse_search_card_caption(card, link)
            seen.add(vid)
            out.append((href, likes, link, cap))
        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    # 兜底：只在搜索结果卡片内找链接，避免点到侧栏/推荐里同域 /video/ 链
    if not out:
        try:
            scoped = "li.QdtBFx1O a[href*='/video/'], div.search-result-card a[href*='/video/']"
            for a in driver.find_elements(By.CSS_SELECTOR, scoped):
                try:
                    if not a.is_displayed():
                        continue
                    href = (a.get_attribute("href") or "").strip()
                    if "/video/" not in href:
                        continue
                    vid = _video_id_from_url(href)
                    if not vid or vid in seen:
                        continue
                    likes = _parse_likes_near_element(a)
                    cap = _parse_search_card_caption_near_link(a)
                    seen.add(vid)
                    out.append((href, likes, a, cap))
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue
        except Exception:
            pass

    # 再兜底：用视口内几何判断「可见」，避免 Selenium is_displayed 与真实列表不一致导致 0 条
    if not out:
        try:
            hrefs = driver.execute_script(
                """
                const v = [];
                const seen = new Set();
                const H = window.innerHeight || 900;
                const roots = document.querySelectorAll('li.QdtBFx1O, div.search-result-card');
                for (const root of roots) {
                  const a = root.querySelector('a[href*="/video/"]');
                  if (!a) continue;
                  const r = a.getBoundingClientRect();
                  if (r.width < 2 || r.height < 2) continue;
                  if (r.bottom < -50 || r.top > H + 100) continue;
                  const href = a.href || '';
                  const m = href.match(/\\/video\\/(\\d+)/);
                  if (!m) continue;
                  const id = m[1];
                  if (seen.has(id)) continue;
                  seen.add(id);
                  v.push(href);
                }
                return v;
                """
            )
            for href in hrefs or []:
                vid = _video_id_from_url(href)
                if not vid or vid in seen:
                    continue
                el = None
                try:
                    for cand in driver.find_elements(By.CSS_SELECTOR, f'a[href*="/video/{vid}"]'):
                        try:
                            if cand.is_displayed():
                                el = cand
                                break
                        except StaleElementReferenceException:
                            continue
                except Exception:
                    pass
                if el is None:
                    continue
                lk = _parse_likes_near_element(el)
                cap = _parse_search_card_caption_near_link(el)
                seen.add(vid)
                out.append((href, lk, el, cap))
        except Exception as e:
            logger.warning(f"[SeleniumIntercept] JS 兜底采集视频列表失败: {e}")

    out = _merge_js_likes_into_cards(out, js_likes)
    _log_likes_parse_diagnostics(driver, out, js_likes)

    if out:
        sample = [(_video_id_from_url(h), lk) for h, lk, _, _ in out[:8]]
        logger.info(
            f"[SeleniumIntercept] collect_video_cards 得到 {len(out)} 条（按 video_id 去重）"
            f" 示例(vid,likes)={sample}"
        )
    else:
        vc = _visible_search_video_link_count(driver)
        logger.warning(
            f"[SeleniumIntercept] collect_video_cards 得到 0 条，但可见 /video/ 链接计数={vc}（若不等，多为结构变化）"
        )

    return out


def try_open_video_in_new_tab(driver: webdriver.Chrome, link_el) -> bool:
    """同页悬浮窗迟迟不出时：Ctrl+点击尝试新开标签（仍不 driver.get 视频链）。"""
    before = list(driver.window_handles)
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_el)
        time.sleep(0.2)
        ActionChains(driver).key_down(Keys.CONTROL).click(link_el).key_up(Keys.CONTROL).perform()
        time.sleep(1.0)
        return len(driver.window_handles) > len(before)
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] Ctrl+点击新开标签失败: {e}")
        return False


def click_open_video(driver: webdriver.Chrome, link_el) -> str:
    """
    拟人：只通过点击列表里的链接/卡片打开视频，禁止 driver.get(视频 URL) 进详情。
    滚入视窗 → 停顿 → 移入 → 短停 → 点击，给悬浮窗留出渲染时间。
    """
    before = list(driver.window_handles)
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link_el)
        _rand_sleep(0.28, 0.62)
        ActionChains(driver).move_to_element(link_el).pause(
            random.uniform(0.1, 0.26)
        ).click(link_el).perform()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", link_el)
        except Exception as e:
            logger.warning(f"[SeleniumIntercept] 打开视频失败: {e}")
            return "same"
    _rand_sleep(0.55, 1.05)
    after = driver.window_handles
    if len(after) > len(before):
        _switch_to_newest(driver)
        time.sleep(0.45)
        return "new"
    return "same"


def wait_video_detail_ready(driver: webdriver.Chrome, video_id: str, timeout: float = 35.0) -> bool:
    """
    等待悬浮窗/播放区在 DOM 上就绪（可见 dialog + 目标视频或大屏 video），不根据地址栏判断。
    网速慢时依赖 WebDriverWait 轮询直至超时。
    """
    ev = (video_id or "").strip()
    if not ev:
        return False

    def _ready(d: webdriver.Chrome) -> bool:
        return _page_has_floating_video_for_id(d, ev)

    try:
        WebDriverWait(driver, timeout).until(_ready)
        root = _find_modal_root_for_video(driver, ev)
        kind = "悬浮窗" if root is not None else "大屏播放区"
        logger.info(
            f"[SeleniumIntercept] 视频详情已就绪（DOM/{kind}，非地址栏） video_id={ev}"
        )
        return True
    except TimeoutException:
        logger.warning(
            f"[SeleniumIntercept] {int(timeout)}s 内悬浮窗/播放区未就绪（DOM 未出现目标 video_id={ev}），"
            "可增大 --detail-wait 或检查网速"
        )
        return False


def restore_search_list_context(
    driver: webdriver.Chrome,
    *,
    list_page_url: str,
    mode: str,
    before_handles: List[str],
    force_reload: bool = False,
) -> None:
    """
    离开视频回到搜索列表：新标签则关标签切回。
    同页一律不 driver.get（会丢「最新发布/半年内」等筛选态）；须先 close_video_or_overlay 点关闭。
    仅当 force_reload=True（异常兜底）时才用 list_page_url 整页刷新。
    """
    try:
        if mode == "new":
            extras = [h for h in driver.window_handles if h not in before_handles]
            for h in extras:
                try:
                    driver.switch_to.window(h)
                    driver.close()
                except Exception:
                    pass
            if before_handles:
                driver.switch_to.window(before_handles[0])
        else:
            if force_reload and list_page_url:
                driver.get(list_page_url)
                logger.warning(
                    "[SeleniumIntercept] 同页强制刷新列表 URL（可能丢失筛选，仅异常兜底）"
                )
                time.sleep(2.0)
            else:
                _rand_sleep(0.35, 0.7)
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 恢复搜索列表上下文失败: {e}")
        try:
            if before_handles:
                driver.switch_to.window(before_handles[0])
        except Exception:
            pass


def has_no_comments_placeholder(driver: webdriver.Chrome, video_id: str = "") -> bool:
    ev = (video_id or "").strip()
    if ev and not _page_has_floating_video_for_id(driver, ev):
        return False
    root = _find_modal_root_for_video(driver, ev) if ev else None
    try:
        icon_scope = root if root is not None else driver
        for icon in icon_scope.find_elements(By.CSS_SELECTOR, '[data-e2e="feed-comment-icon"]'):
            try:
                if icon.is_displayed() and "抢首评" in (icon.text or ""):
                    return True
            except Exception:
                continue
        if root is not None:
            for el in root.find_elements(By.CSS_SELECTOR, "[class*='X_wB9MpJ'], [class*='RfKJW3Qx']"):
                try:
                    if el.is_displayed() and "抢首评" in (el.text or ""):
                        return True
                except Exception:
                    continue
            for el in root.find_elements(By.CSS_SELECTOR, "[class*='SfwAcdr1']"):
                try:
                    if el.is_displayed() and "抢首评" in (el.text or ""):
                        return True
                except Exception:
                    continue
        for phrase in ("抢首评", "暂无评论", "还没有评论"):
            xp = f".//*[contains(text(),'{phrase}')]" if root is not None else f"//*[contains(text(),'{phrase}')]"
            els = root.find_elements(By.XPATH, xp) if root is not None else driver.find_elements(By.XPATH, xp)
            for e in els:
                try:
                    if e.is_displayed():
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


def _element_visible_area(el) -> float:
    try:
        r = el.rect
        return float(max(0, r.get("width", 0)) * max(0, r.get("height", 0)))
    except Exception:
        return 0.0


def _comment_list_is_visible(driver: webdriver.Chrome) -> bool:
    try:
        for e in driver.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-list"]'):
            if e.is_displayed():
                return True
    except Exception:
        pass
    return False


def _js_click(driver: webdriver.Chrome, el) -> bool:
    try:
        driver.execute_script(
            "var n=arguments[0]; try{n.scrollIntoView({block:'center',inline:'center'});}catch(e){} "
            "if(n.click) n.click(); else if(n.parentElement) n.parentElement.click();",
            el,
        )
        return True
    except Exception:
        return False


def _comment_overlay_roots_for_video(driver: webdriver.Chrome, video_id: str = "") -> List[Any]:
    """
    与 click_comment_panel 使用同一套「视频浮层」根节点顺序：
    当前 video_id 对应 modal → 其它 _find_video_modal_candidates。
    评论区列表、评论输入框与点评论气泡（jp8u3iov）应在这些根的同一层子树内。
    """
    ev = (video_id or "").strip()
    roots: List[Any] = []
    seen_root: Set[int] = set()
    if ev:
        mr = _find_modal_root_for_video(driver, ev)
        if mr is not None:
            roots.append(mr)
            seen_root.add(id(mr))
    for c in _find_video_modal_candidates(driver):
        if id(c) in seen_root:
            continue
        seen_root.add(id(c))
        roots.append(c)
    return roots


def _extra_comment_ui_roots_from_sidebar(driver: webdriver.Chrome, video_id: str = "") -> List[Any]:
    """
    与右侧「点赞/评论气泡/作者头像」同一条竖向互动区相关的祖先容器。
    用户反馈评论输入与点头像同属这一视觉层，补充进搜索根，避免只 match 到 dialog 外壳而漏掉内层。
    """
    out: List[Any] = []
    seen: Set[int] = set()
    ev = (video_id or "").strip()
    try:
        vw = float(driver.execute_script("return window.innerWidth||1200") or 1200)
    except Exception:
        vw = 1200.0
    try:
        for jp in driver.find_elements(By.CSS_SELECTOR, _COMMENT_ENTRY_ICON_CSS):
            try:
                if not jp.is_displayed():
                    continue
                r = jp.rect
                if float(r.get("x", 0)) < vw * 0.36:
                    continue
                cur: Any = jp
                for _ in range(16):
                    try:
                        cur = cur.find_element(By.XPATH, "./..")
                    except Exception:
                        break
                    try:
                        if not cur.is_displayed():
                            continue
                        br = cur.rect
                        if float(br.get("width", 0)) < 160:
                            continue
                        cid = id(cur)
                        if cid in seen:
                            continue
                        seen.add(cid)
                        out.append(cur)
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    if ev:
        try:
            for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/user/"]'):
                try:
                    if not a.is_displayed():
                        continue
                    r = a.rect
                    if float(r.get("x", 0)) + float(r.get("width", 0)) / 2 < vw * 0.40:
                        continue
                    try:
                        dlg = a.find_element(By.XPATH, "./ancestor::div[@role='dialog'][1]")
                    except NoSuchElementException:
                        continue
                    cid = id(dlg)
                    if cid in seen:
                        continue
                    html = dlg.get_attribute("innerHTML") or ""
                    if ev not in html:
                        continue
                    seen.add(cid)
                    out.append(dlg)
                except Exception:
                    continue
        except Exception:
            pass
    return out


def click_comment_panel(driver: webdriver.Chrome, video_id: str = "") -> bool:
    """
    悬浮窗内评论入口：优先 data-e2e=feed-comment-icon（含零评论「抢首评」文案），
    兜底 div.jp8u3iov / 评论 Tab。
    不在全页用 element_to_be_clickable（易匹配到隐藏节点）；优先当前视频所在 dialog，再 JS 点击。
    """
    roots = _comment_overlay_roots_for_video(driver, video_id)

    def collect_comment_entry_nodes(container) -> List[Any]:
        out: List[Any] = []
        seen: Set[int] = set()
        for sel in (
            '[data-e2e="feed-comment-icon"]',
            "div.jp8u3iov, div[class*='jp8u3iov']",
        ):
            try:
                for el in container.find_elements(By.CSS_SELECTOR, sel):
                    eid = id(el)
                    if eid in seen:
                        continue
                    seen.add(eid)
                    out.append(el)
            except Exception:
                pass
        return out

    def try_one(el) -> bool:
        try:
            if not el.is_displayed():
                return False
        except Exception:
            return False
        if _element_visible_area(el) < 36:
            return False
        if not _js_click(driver, el):
            try:
                el.click()
            except Exception:
                return False
        _rand_sleep(0.7, 1.1)
        end = time.time() + 10.0
        while time.time() < end:
            if _comment_list_is_visible(driver):
                logger.info("[SeleniumIntercept] 已点开评论区（出现 comment-list）")
                return True
            time.sleep(0.2)
        logger.info("[SeleniumIntercept] 已点击评论入口，未在 10s 内检测到 comment-list（仍继续流程）")
        return True

    for root in roots:
        try:
            cands = collect_comment_entry_nodes(root)
            cands.sort(key=_element_visible_area, reverse=True)
            for el in cands:
                if try_one(el):
                    return True
        except Exception:
            continue

    try:
        all_j = driver.find_elements(
            By.CSS_SELECTOR,
            _COMMENT_ENTRY_ICON_CSS,
        )
        all_j.sort(key=_element_visible_area, reverse=True)
        for el in all_j:
            if try_one(el):
                return True
    except Exception:
        pass

    try:
        dialog_xps = (
            "//div[@role='dialog']",
            "//div[contains(@class,'Modal')]",
            "//div[contains(@class,'modal')]",
        )
        for dx in dialog_xps:
            try:
                dialogs = driver.find_elements(By.XPATH, dx)
            except Exception:
                continue
            for dlg in dialogs:
                try:
                    if not dlg.is_displayed():
                        continue
                except Exception:
                    continue
                tabs = dlg.find_elements(
                    By.XPATH,
                    ".//div[contains(@class,'semi-tabs-tab')][contains(.,'评论')]"
                    " | .//div[@role='tab'][contains(.,'评论')]"
                    " | .//span[contains(normalize-space(),'评论')][string-length(normalize-space())<28]",
                )
                for el in tabs:
                    try:
                        if el.is_displayed() and try_one(el):
                            return True
                    except Exception:
                        continue
    except Exception:
        pass

    try:
        for el in driver.find_elements(
            By.XPATH,
            "//button[contains(normalize-space(),'评论')][string-length(normalize-space())<24]"
            " | //div[@role='button'][contains(normalize-space(),'评论')]",
        ):
            try:
                if el.is_displayed() and try_one(el):
                    return True
            except Exception:
                continue
    except Exception:
        pass

    logger.warning(
        "[SeleniumIntercept] 未点到评论入口（请检查 data-e2e=feed-comment-icon 或 div.jp8u3iov 是否被遮挡）"
    )
    return False


def _first_dialog_around_visible_comment_list(driver: webdriver.Chrome) -> Optional[Any]:
    for cl in driver.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-list"]'):
        try:
            if not cl.is_displayed():
                continue
            return cl.find_element(By.XPATH, "./ancestor::div[@role='dialog'][1]")
        except NoSuchElementException:
            continue
        except Exception:
            continue
    return None


def _iter_comment_dialog_roots(driver: webdriver.Chrome, video_id: str = "") -> List[Any]:
    """
    找评论输入框时的搜索根：先与点开评论完全相同的浮层（不依赖 modal 内能否用 Selenium 直接 find 到 comment-list），
    再补充其它含 comment-list 的 dialog、Modal 祖先、以及沿 comment-list 向上的祖先链。
    """
    roots: List[Any] = []
    seen: Set[int] = set()
    for r in _comment_overlay_roots_for_video(driver, video_id):
        cid = id(r)
        if cid in seen:
            continue
        seen.add(cid)
        roots.append(r)
    for r in _extra_comment_ui_roots_from_sidebar(driver, video_id):
        cid = id(r)
        if cid in seen:
            continue
        seen.add(cid)
        roots.append(r)
    try:
        for dlg in driver.find_elements(By.XPATH, "//div[@role='dialog']"):
            if id(dlg) in seen:
                continue
            try:
                if not dlg.is_displayed():
                    continue
            except Exception:
                continue
            for cl in dlg.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-list"]'):
                try:
                    if cl.is_displayed():
                        roots.append(dlg)
                        seen.add(id(dlg))
                        break
                except Exception:
                    continue
    except Exception:
        pass
    if not roots:
        fb = _first_dialog_around_visible_comment_list(driver)
        if fb is not None:
            roots.append(fb)
    if not roots:
        for cl in driver.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-list"]'):
            try:
                if not cl.is_displayed():
                    continue
                root = cl.find_element(
                    By.XPATH,
                    "./ancestor::div[contains(@class,'Modal') or contains(@class,'modal')][1]",
                )
                if root.is_displayed():
                    roots.append(root)
                    break
            except (NoSuchElementException, Exception):
                continue
    # 输入框常在 comment-list 的「旁系」分支（与列表同层或不同子树），仅 dialog/Modal 不一定包住；沿列表向上把所有祖先加入搜索根。
    for cl in driver.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-list"]'):
        try:
            if not cl.is_displayed():
                continue
        except Exception:
            continue
        cur: Any = cl
        for _ in range(28):
            try:
                cur = cur.find_element(By.XPATH, "./..")
            except Exception:
                break
            try:
                tn = (cur.tag_name or "").lower()
            except Exception:
                break
            if tn in ("body", "html"):
                break
            cid = id(cur)
            if cid in seen:
                continue
            seen.add(cid)
            roots.append(cur)
    return roots


def _element_is_danmaku_or_video_bar(driver: webdriver.Chrome, el: Any) -> bool:
    """
    视频区弹层与右侧评论栏分离时，全页扫到的第一个 contenteditable 往往是左下「发弹幕」条。
    用占位/祖先 data-e2e、class 与几何（偏左且靠下）排除，避免误聚焦视频层。
    """
    try:
        return bool(
            driver.execute_script(
                """
                var el = arguments[0];
                if (!el || !el.getBoundingClientRect) return false;
                function ph(n) {
                  if (!n || !n.getAttribute) return '';
                  return (n.getAttribute('data-placeholder')||'') + (n.getAttribute('placeholder')||'') +
                    (n.getAttribute('aria-placeholder')||'') + (n.getAttribute('aria-label')||'');
                }
                var p = el;
                for (var i = 0; i < 28 && p; i++) {
                  var t = ph(p);
                  if (/弹幕|bullet|Barrage|发弹幕/i.test(t)) return true;
                  var e2 = p.getAttribute && p.getAttribute('data-e2e');
                  if (e2 && /bullet|barrage|danmu|danmaku|dm-input|send-danmu/i.test(e2)) return true;
                  var cls = (p.className && p.className.baseVal !== undefined)
                    ? String(p.className.baseVal) : String(p.className || '');
                  if (/danmu|Danmu|bullet|barrage|Barrage|dm-bar|dmBar|dm-input|DmInput/i.test(cls))
                    return true;
                  p = p.parentElement;
                }
                var r = el.getBoundingClientRect();
                var W = window.innerWidth || 1200, H = window.innerHeight || 800;
                var cx = r.left + r.width / 2;
                if (cx < W * 0.41 && r.bottom > H * 0.60) return true;
                if (cx < W * 0.36 && r.top + r.height / 2 > H * 0.45) return true;
                return false;
                """,
                el,
            )
        )
    except Exception:
        return False


def _element_in_comment_column_with_list(driver: webdriver.Chrome, el: Any) -> bool:
    """输入框须与「右侧可见 comment-list」同列（几何重叠），避免视频层同名容器。"""
    try:
        return bool(
            driver.execute_script(
                """
                var ed = arguments[0];
                if (!ed || !ed.getBoundingClientRect) return false;
                var ec = ed.getBoundingClientRect();
                if (ec.width < 2 && ec.height < 2) return false;
                var ecx = ec.left + ec.width / 2;
                var W = window.innerWidth || 1200;
                if (ecx >= W * 0.47) return true;
                var lists = document.querySelectorAll('[data-e2e="comment-list"]');
                for (var i = 0; i < lists.length; i++) {
                  var L = lists[i];
                  var st = window.getComputedStyle(L);
                  if (st.visibility === 'hidden' || st.display === 'none') continue;
                  var lr = L.getBoundingClientRect();
                  if (lr.width < 10 || lr.height < 10) continue;
                  var lcx = lr.left + lr.width / 2;
                  if (lcx < W * 0.40) continue;
                  var overlapH = !(ec.right < lr.left - 60 || ec.left > lr.right + 100);
                  var overlapV = !(ec.bottom < lr.top - 220 || ec.top > lr.bottom + 320);
                  if (overlapH && overlapV) return true;
                }
                return false;
                """,
                el,
            )
        )
    except Exception:
        try:
            vw = float(driver.execute_script("return window.innerWidth||1200") or 1200)
            r = el.rect
            midx = float(r.get("x", 0)) + float(r.get("width", 0)) / 2.0
            return midx >= vw * 0.47
        except Exception:
            return True


_VIDEO_COMMENT_EDITOR_SELECTORS: Tuple[str, ...] = (
    # 抖音 Web 实为 class=comment-input-container（见用户快照 带评论框元素.txt），不是 id；#comment-input-container 会永远匹配不到。
    "div.comment-input-container [contenteditable='true']",
    "div.comment-input-container div.public-DraftEditor-content[contenteditable='true']",
    ".comment-input-inner-container [contenteditable='true']",
    "div[class*='comment-input-inner-container'] [contenteditable='true']",
    "div[class*='comment-input-container'] [contenteditable='true']",
    "#comment-input-container div[contenteditable='true']",
    "[data-e2e='comment-input'] [contenteditable='true']",
    "[data-e2e='comment-input'] div[contenteditable='true']",
    "div[contenteditable='true'][data-placeholder*='评论']",
    "div[contenteditable='true'][data-placeholder*='留下']",
    "div[contenteditable='true'][data-placeholder*='友善']",
    "div[contenteditable='true'][data-placeholder*='抢首评']",
    "div[contenteditable='true'][data-placeholder*='精彩评论']",
    "div.public-DraftEditor-content[contenteditable='true']",
    "div[role='textbox'][contenteditable='true']",
    "textarea[placeholder*='评论']",
    "div.public-DraftStyleDefault-block",
    '[data-e2e="comment-list"] ~ * div[contenteditable="true"]',
    "footer [contenteditable='true']",
    "div[contenteditable='true']",
)


def _score_video_comment_editor_candidate(el: Any) -> int:
    """分高者更像「发评论」框（可见但无 dialog 包一层时靠打分区分）。"""
    s = 0
    try:
        ph = (el.get_attribute("data-placeholder") or "") + (el.get_attribute("placeholder") or "")
        ph += (el.get_attribute("aria-placeholder") or "") + (el.get_attribute("aria-label") or "")
        for kw in ("精彩评论", "评论", "留下", "友善", "抢首评", "有爱", "发条评论", "说点什么"):
            if kw in ph:
                s += 120
                break
    except Exception:
        pass
    try:
        el.find_element(By.XPATH, "./ancestor::*[@data-e2e='comment-input'][1]")
        s += 100
    except NoSuchElementException:
        pass
    except Exception:
        pass
    try:
        el.find_element(By.XPATH, "./ancestor::*[@id='comment-input-container'][1]")
        s += 90
    except NoSuchElementException:
        pass
    except Exception:
        pass
    try:
        el.find_element(
            By.XPATH, "./ancestor::div[contains(@class,'comment-input-container')][1]"
        )
        s += 95
    except NoSuchElementException:
        pass
    except Exception:
        pass
    try:
        cls = el.get_attribute("class") or ""
        if "DraftEditor" in cls or "public-DraftEditor" in cls:
            s += 35
    except Exception:
        pass
    try:
        if (el.tag_name or "").lower() == "textarea":
            s += 25
    except Exception:
        pass
    try:
        if el.get_attribute("contenteditable") == "true":
            s += 8
    except Exception:
        pass
    return s


def _root_skip_generic_contenteditable(driver: webdriver.Chrome, root: Any) -> bool:
    """过大根节点上不跑最后的 div[contenteditable=true]，以免扫全页且误选。"""
    try:
        if (root.tag_name or "").lower() == "body":
            return True
        r = root.rect
        area = float(max(0, r.get("width", 0)) * max(0, r.get("height", 0)))
        return area >= 800_000.0
    except Exception:
        return False


def _pick_video_comment_editor_selenium_roots(
    driver: webdriver.Chrome, video_id: str = ""
) -> Optional[Any]:
    """
    在含 comment-list 的各层祖先内找输入框；列表与输入框常属兄弟子树，必须把祖先链都当作 root。
    多候选时按「像评论框」打分取最优，避免与页内其它 contenteditable 混淆。
    """
    roots = _iter_comment_dialog_roots(driver, video_id)
    best: Optional[Tuple[int, float, Any]] = None
    for root in roots:
        skip_broad = _root_skip_generic_contenteditable(driver, root)
        sels = (
            _VIDEO_COMMENT_EDITOR_SELECTORS[:-1] if skip_broad else _VIDEO_COMMENT_EDITOR_SELECTORS
        )
        for sel in sels:
            try:
                cands = list(root.find_elements(By.CSS_SELECTOR, sel))
            except Exception:
                continue
            for e in cands:
                try:
                    if not e.is_displayed():
                        continue
                    ar = _element_visible_area(e)
                    if ar < 20:
                        continue
                    if _element_is_danmaku_or_video_bar(driver, e):
                        continue
                    if not _element_in_comment_column_with_list(driver, e):
                        continue
                    sc = _score_video_comment_editor_candidate(e)
                    if sc < 10:
                        continue
                    if best is None or sc > best[0] or (sc == best[0] and ar > best[1]):
                        best = (sc, ar, e)
                except Exception:
                    continue
    if best is not None:
        return best[2]
    for root in roots:
        skip_broad = _root_skip_generic_contenteditable(driver, root)
        sels = (
            _VIDEO_COMMENT_EDITOR_SELECTORS[:-1] if skip_broad else _VIDEO_COMMENT_EDITOR_SELECTORS
        )
        for sel in sels:
            try:
                cands = list(root.find_elements(By.CSS_SELECTOR, sel))
            except Exception:
                continue
            cands.sort(key=_element_visible_area, reverse=True)
            for e in cands:
                try:
                    if not e.is_displayed():
                        continue
                    ar = _element_visible_area(e)
                    if ar < 20:
                        continue
                    if _element_is_danmaku_or_video_bar(driver, e):
                        continue
                    if not _element_in_comment_column_with_list(driver, e):
                        continue
                    return e
                except Exception:
                    continue
    return None


_COMMENT_PLACEHOLDER_TO_EDITOR_AXES: Tuple[str, ...] = (
    "./preceding-sibling::div[@contenteditable='true']",
    "./following-sibling::div[@contenteditable='true']",
    "./preceding-sibling::*//div[@contenteditable='true']",
    "./following-sibling::*//div[@contenteditable='true']",
    "./parent::div/div[@contenteditable='true']",
    "./ancestor::div[@contenteditable='true'][1]",
    "./ancestor::div[contains(@class,'notranslate')][1]//div[@contenteditable='true']",
    "./ancestor::div[.//span[contains(@class,'hVeIqFGi') or contains(@class,'j_kd_P_l')]][1]"
    "//div[contains(@class,'public-DraftEditor-content')][@contenteditable='true']",
)


def _pick_comment_editor_via_placeholder_text_xpath(driver: webdriver.Chrome) -> Optional[Any]:
    """不依赖 class 哈希：占位「留下你的精彩评论吧」全文 XPath；排除偏左的弹幕区。"""
    for xp in (
        "//span[contains(normalize-space(),'留下你的精彩评论吧')]",
        "//span[contains(normalize-space(),'精彩评论吧')]",
    ):
        try:
            for sp in driver.find_elements(By.XPATH, xp):
                try:
                    if not sp.is_displayed():
                        continue
                    if "弹幕" in ((sp.text or "").strip()):
                        continue
                except Exception:
                    continue
                try:
                    vw = float(driver.execute_script("return window.innerWidth||1200") or 1200)
                    r = sp.rect
                    midx = float(r.get("x", 0)) + float(r.get("width", 0)) / 2.0
                    if midx < vw * 0.40:
                        continue
                except Exception:
                    pass
                for ax in _COMMENT_PLACEHOLDER_TO_EDITOR_AXES:
                    try:
                        ed = sp.find_element(By.XPATH, ax)
                        if ed.is_displayed() and _element_visible_area(ed) >= 10:
                            if _element_is_danmaku_or_video_bar(driver, ed):
                                continue
                            if not _element_in_comment_column_with_list(driver, ed):
                                continue
                            return ed
                    except (NoSuchElementException, Exception):
                        continue
        except Exception:
            continue
    return None


def _inner_width_for_layout(driver: webdriver.Chrome) -> float:
    try:
        return float(driver.execute_script("return window.innerWidth||1200") or 1200)
    except Exception:
        return 1200.0


def _best_right_side_comment_list(driver: webdriver.Chrome) -> Optional[Any]:
    """右侧主评论列上的 comment-list（面积大者优先），避免点到视频区隐藏的同名节点。"""
    vw = _inner_width_for_layout(driver)
    best = None
    best_area = -1.0
    try:
        for cl in driver.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-list"]'):
            try:
                if not cl.is_displayed():
                    continue
                r = cl.rect
                area = float(r.get("width", 0) or 0) * float(r.get("height", 0) or 0)
                midx = float(r.get("x", 0) or 0) + float(r.get("width", 0) or 0) / 2.0
                if midx < vw * 0.40:
                    continue
                if area > best_area:
                    best_area = area
                    best = cl
            except Exception:
                continue
    except Exception:
        return None
    return best


def _best_right_side_comment_scroll_host(driver: webdriver.Chrome) -> Optional[Any]:
    """滚到底时的滚动容器：优先 comment-list，否则右侧主内容区。"""
    w = _best_right_side_comment_list(driver)
    if w is not None:
        return w
    vw = _inner_width_for_layout(driver)
    for sel in ("div.Rwb9ssMc", "[class*='comment-mainContent']"):
        try:
            cand = None
            cand_area = -1.0
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                try:
                    if not el.is_displayed():
                        continue
                    r = el.rect
                    midx = float(r.get("x", 0) or 0) + float(r.get("width", 0) or 0) / 2.0
                    if midx < vw * 0.40:
                        continue
                    area = float(r.get("width", 0) or 0) * float(r.get("height", 0) or 0)
                    if area > cand_area:
                        cand_area = area
                        cand = el
                except Exception:
                    continue
            if cand is not None:
                return cand
        except Exception:
            continue
    return None


def _js_mouse_click_center(driver: webdriver.Chrome, el: Any) -> None:
    """用视口坐标派发鼠标事件，减轻被视频层截获 native click 的情况。"""
    try:
        driver.execute_script(
            """
            var n = arguments[0];
            if (!n || !n.getBoundingClientRect) return;
            try { n.scrollIntoView({block: 'center', inline: 'nearest'}); } catch (e0) {}
            var r = n.getBoundingClientRect();
            var x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2);
            ['mousedown', 'mouseup', 'click'].forEach(function (tp) {
              try {
                n.dispatchEvent(new MouseEvent(tp, {
                  bubbles: true, cancelable: true, view: window,
                  clientX: x, clientY: y, button: 0
                }));
              } catch (e1) {}
            });
            try { n.click(); } catch (e2) {}
            """,
            el,
        )
    except Exception:
        pass


def _js_click_comment_placeholder_right_column(driver: webdriver.Chrome) -> None:
    """点击右侧「留下你的精彩评论吧」占位，促发 Draft 挂载与焦点（与手工二次点击一致）。"""
    try:
        driver.execute_script(
            """
            var W = window.innerWidth || 1200;
            var spans = document.querySelectorAll(
              'span.hVeIqFGi, span[class*="hVeIqFGi"], span.j_kd_P_l, span[class*="j_kd_P_l"]'
            );
            for (var i = 0; i < spans.length; i++) {
              var sp = spans[i];
              var t = (sp.textContent || '').trim();
              if (t.indexOf('弹幕') >= 0) continue;
              if (t.indexOf('精彩评论') < 0 && t.indexOf('留下') < 0) continue;
              var r = sp.getBoundingClientRect();
              if (r.width < 0.5 && r.height < 0.5) continue;
              if (r.left + r.width / 2 < W * 0.40) continue;
              try { sp.scrollIntoView({block: 'center', inline: 'nearest'}); } catch (e) {}
              r = sp.getBoundingClientRect();
              var x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2);
              ['mousedown', 'mouseup', 'click'].forEach(function (tp) {
                try {
                  sp.dispatchEvent(new MouseEvent(tp, {
                    bubbles: true, cancelable: true, view: window,
                    clientX: x, clientY: y, button: 0
                  }));
                } catch (e2) {}
              });
              try { sp.click(); } catch (e3) {}
              return true;
            }
            return false;
            """
        )
    except Exception:
        pass


def _activate_comment_side_before_input(driver: webdriver.Chrome) -> None:
    """
    焦点常在视频层时，仅 focus 输入框不够。先点右侧评论列再滚到底并点占位，与手工「激活窗口 → 滚到暂无评论 → 点输入条」一致。
    """
    _videos_set_pointer_events(driver, "none")
    try:
        cl = _best_right_side_comment_list(driver)
        if cl is not None:
            _js_mouse_click_center(driver, cl)
            _rand_sleep(0.14, 0.28)
        _scroll_comment_list_to_bottom(driver)
        _rand_sleep(0.08, 0.16)
        _js_click_comment_placeholder_right_column(driver)
        _rand_sleep(0.12, 0.22)
    finally:
        _videos_set_pointer_events(driver, "")


def _prime_comment_editor_click(driver: webdriver.Chrome, ed: Any) -> None:
    """输入前再点一次容器 + 编辑器中心，避免焦点仍在 video。"""
    try:
        driver.execute_script(
            """
            var ed = arguments[0];
            if (!ed || !ed.getBoundingClientRect) return;
            function clickCenter(n) {
              if (!n || !n.getBoundingClientRect) return;
              try { n.scrollIntoView({block: 'center', inline: 'nearest'}); } catch (e0) {}
              var r = n.getBoundingClientRect();
              var x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2);
              ['mousedown', 'mouseup', 'click'].forEach(function (tp) {
                try {
                  n.dispatchEvent(new MouseEvent(tp, {
                    bubbles: true, cancelable: true, view: window,
                    clientX: x, clientY: y, button: 0
                  }));
                } catch (e1) {}
              });
              try { n.click(); } catch (e2) {}
              try { n.focus(); } catch (e3) {}
            }
            var host = ed;
            try {
              if (ed.closest) {
                host = ed.closest('div.comment-input-container') ||
                  ed.closest('[class*="comment-input-container"]') || ed;
              }
            } catch (e) {}
            if (host && host !== ed) clickCenter(host);
            clickCenter(ed);
            """,
            ed,
        )
    except Exception:
        pass
    _rand_sleep(0.08, 0.16)


def _scroll_comment_list_to_bottom(driver: webdriver.Chrome) -> None:
    """把评论列表滚到底，底部输入条有时依赖滚动才稳定挂载。"""
    best = _best_right_side_comment_scroll_host(driver)
    if best is not None:
        try:
            driver.execute_script(
                "var n=arguments[0]; try{n.scrollTop=n.scrollHeight;}catch(e){}",
                best,
            )
            time.sleep(0.12)
        except Exception:
            pass


def _pick_comment_editor_via_hVeIqFGi_placeholder(
    driver: webdriver.Chrome, video_id: str = ""
) -> Optional[Any]:
    """
    抖音评论占位常挂在独立 span（hVeIqFGi / j_kd_P_l，「留下你的精彩评论吧」），与 Draft 的 contenteditable 平级，
    故 contenteditable 上可能没有 data-placeholder；从该 span 用兄弟/祖先轴找真正可编辑节点。
    """
    roots = _iter_comment_dialog_roots(driver, video_id)
    if not roots:
        try:
            roots = [driver.find_element(By.TAG_NAME, "body")]
        except Exception:
            return None
    for root in roots:
        try:
            spans = root.find_elements(
                By.CSS_SELECTOR,
                _COMMENT_PLACEHOLDER_SPAN_CSS,
            )
        except Exception:
            continue
        for sp in spans:
            try:
                if not sp.is_displayed():
                    continue
                tx = (sp.text or "").strip()
                if "弹幕" in tx:
                    continue
                if tx and all(
                    k not in tx for k in ("精彩评论", "留下", "评论", "友善")
                ):
                    continue
            except Exception:
                continue
            for ax in _COMMENT_PLACEHOLDER_TO_EDITOR_AXES:
                try:
                    ed = sp.find_element(By.XPATH, ax)
                    if ed.is_displayed() and _element_visible_area(ed) >= 12:
                        if _element_is_danmaku_or_video_bar(driver, ed):
                            continue
                        if not _element_in_comment_column_with_list(driver, ed):
                            continue
                        return ed
                except NoSuchElementException:
                    continue
                except Exception:
                    continue
            try:
                for blk in sp.find_elements(
                    By.XPATH,
                    "./ancestor::div[1]//div[contains(@class,'public-DraftStyleDefault-block')]",
                ):
                    try:
                        ed = blk.find_element(
                            By.XPATH, "./ancestor::div[@contenteditable='true'][1]"
                        )
                        if ed.is_displayed() and _element_visible_area(ed) >= 12:
                            if _element_is_danmaku_or_video_bar(driver, ed):
                                continue
                            if not _element_in_comment_column_with_list(driver, ed):
                                continue
                            return ed
                    except (NoSuchElementException, Exception):
                        continue
            except Exception:
                pass
    return None


def _pick_video_comment_editor_js(driver: webdriver.Chrome, scope: Any = None) -> Optional[Any]:
    """
    在浏览器内收集 contenteditable/textarea（含 open shadowRoot），按占位与相对 comment-list 位置打分，
    排除左下角「弹幕」输入（占位常含「弹幕」）。解决外层 CSS 扫不到 shadow 内 Draft 的情况。
    scope 传入浮层根元素时只在子树内查找（与点评论气泡/右侧互动条同层）；None 表示整页 documentElement。
    """
    try:
        el = driver.execute_script(
            """
            function visible(el) {
              if (!el || el.nodeType !== 1) return false;
              var r = el.getBoundingClientRect();
              if (r.width < 6 || r.height < 3) return false;
              var st = window.getComputedStyle(el);
              if (st.visibility === 'hidden' || st.display === 'none') return false;
              if (parseFloat(st.opacity || '1') < 0.08) return false;
              return true;
            }
            function collectEditables(root, out) {
              if (!root) return;
              if (root.querySelectorAll) {
                var q = root.querySelectorAll('[contenteditable="true"], textarea');
                for (var i = 0; i < q.length; i++) out.push(q[i]);
                var all = root.querySelectorAll('*');
                for (var j = 0; j < all.length; j++) {
                  if (all[j].shadowRoot) collectEditables(all[j].shadowRoot, out);
                }
              }
            }
            function phStr(el) {
              return (el.getAttribute('data-placeholder') || '') +
                (el.getAttribute('placeholder') || '') +
                (el.getAttribute('aria-placeholder') || '') +
                (el.getAttribute('aria-label') || '');
            }
            function isDanmu(el) {
              return /弹幕|bullet/i.test(phStr(el));
            }
            var scopeArg = arguments[0];
            var topNode = (scopeArg && scopeArg.nodeType === 1) ? scopeArg : document.documentElement;
            function looksLikeDanmuBar(el, W, H) {
              var er = el.getBoundingClientRect();
              var cx = er.left + er.width / 2;
              if (cx < W * 0.42 && er.bottom > H * 0.70) return true;
              return false;
            }
            function pickEditableUnderAncestor(root, anchorX, anchorMidY, W, H) {
              var best = null, bestD = 1e12;
              function visit(r) {
                if (!r) return;
                if (r.nodeType === 11) {
                  var c = r.firstElementChild;
                  while (c) { visit(c); c = c.nextElementSibling; }
                  return;
                }
                if (r.nodeType !== 1 || !r.querySelectorAll) return;
                var tryq = r.querySelectorAll('[contenteditable="true"], textarea');
                for (var i = 0; i < tryq.length; i++) {
                  var e = tryq[i];
                  if (!visible(e) || isDanmu(e)) continue;
                  if (looksLikeDanmuBar(e, W, H)) continue;
                  var er = e.getBoundingClientRect();
                  if (er.width < 4 || er.height < 2) continue;
                  var ecx = er.left + er.width / 2;
                  if (Math.abs(ecx - anchorX) > 300) continue;
                  var d = Math.abs(er.top - anchorMidY) + Math.abs(ecx - anchorX) * 0.15;
                  if (d < bestD) { bestD = d; best = e; }
                }
                var all = r.querySelectorAll('*');
                for (var j = 0; j < all.length; j++) {
                  if (all[j].shadowRoot) visit(all[j].shadowRoot);
                }
              }
              visit(root);
              return best;
            }
            function findEditorNearPlaceholderSpan(sp, W, H) {
              var sr = sp.getBoundingClientRect();
              var ax = sr.left + sr.width / 2;
              var ay = sr.top + sr.height / 2;
              var p = sp.parentElement;
              for (var up = 0; up < 30 && p; up++) {
                var cand = pickEditableUnderAncestor(p, ax, ay, W, H);
                if (cand) return cand;
                p = p.parentElement;
              }
              return null;
            }
            function walkTreeForPlaceholderThenEditor(W, H) {
              function walk(node) {
                if (!node) return null;
                if (node.nodeType === 11) {
                  var c = node.firstElementChild;
                  while (c) {
                    var h = walk(c);
                    if (h) return h;
                    c = c.nextElementSibling;
                  }
                  return null;
                }
                if (node.nodeType !== 1) return null;
                var tag = node.tagName;
                if (tag === 'SPAN' || tag === 'DIV') {
                  var t = (node.textContent || '').trim();
                  if ((t.indexOf('留下你的精彩评论吧') >= 0 ||
                       (t.indexOf('精彩评论吧') >= 0 && t.indexOf('弹幕') < 0)) && t.length < 120) {
                    var zr = node.getBoundingClientRect();
                    if (zr.left + zr.width / 2 >= W * 0.36) {
                      var ed = findEditorNearPlaceholderSpan(node, W, H);
                      if (ed) return ed;
                    }
                  }
                }
                var ch = node.children;
                for (var i = 0; i < ch.length; i++) {
                  var h2 = walk(ch[i]);
                  if (h2) return h2;
                }
                var all = node.querySelectorAll('*');
                for (var j = 0; j < all.length; j++) {
                  if (all[j].shadowRoot) {
                    var h3 = walk(all[j].shadowRoot);
                    if (h3) return h3;
                  }
                }
                return null;
              }
              return walk(topNode);
            }
            var W = window.innerWidth || 1200, H = window.innerHeight || 800;
            var deepHit = walkTreeForPlaceholderThenEditor(W, H);
            if (deepHit) return deepHit;
            try {
              var xpr = document.evaluate(
                ".//span[contains(normalize-space(string(.)),'留下你的精彩评论吧') or contains(normalize-space(string(.)),'精彩评论吧')]",
                topNode, null,
                XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
              var sp0;
              while (sp0 = xpr.iterateNext()) {
                var zr = sp0.getBoundingClientRect();
                if (zr.width < 2 && zr.height < 2) continue;
                if (zr.left + zr.width / 2 < W * 0.40) continue;
                var t0 = (sp0.textContent || '').trim();
                if (t0.indexOf('弹幕') >= 0) continue;
                var ed0 = findEditorNearPlaceholderSpan(sp0, W, H);
                if (ed0) return ed0;
              }
            } catch (eTop) {}
            var lists = topNode.querySelectorAll('[data-e2e="comment-list"]');
            var listRects = [];
            for (var a = 0; a < lists.length; a++) {
              var br = lists[a].getBoundingClientRect();
              if (br.width < 2 && br.height < 2) continue;
              listRects.push(br);
            }
            if (!listRects.length) {
              listRects.push({
                left: W * 0.52, top: 40, right: W - 2, bottom: H - 4,
                width: W * 0.48, height: H - 44
              });
            }
            function tryHVeIqInRoot(root) {
              if (!root || !root.querySelectorAll) return null;
              var spans = root.querySelectorAll(
                'span.hVeIqFGi, span[class*="hVeIqFGi"], span.j_kd_P_l, span[class*="j_kd_P_l"]'
              );
              for (var si = 0; si < spans.length; si++) {
                var sp = spans[si];
                var srChk = sp.getBoundingClientRect();
                if (srChk.width < 1 && srChk.height < 1) continue;
                var tx = (sp.textContent || '').trim();
                if (tx.indexOf('弹幕') >= 0) continue;
                if (tx.indexOf('精彩评论') < 0 && tx.indexOf('留下') < 0) continue;
                var sr = sp.getBoundingClientRect();
                var nearList = false;
                for (var m = 0; m < listRects.length; m++) {
                  var lr = listRects[m];
                  var cx = sr.left + sr.width / 2;
                  if (sr.bottom >= lr.top - 70 && cx > lr.left - 120 && cx < lr.right + 320)
                    nearList = true;
                }
                if (!nearList) continue;
                var hit = findEditorNearPlaceholderSpan(sp, W, H);
                if (hit) return hit;
              }
              var all = root.querySelectorAll('*');
              for (var j = 0; j < all.length; j++) {
                if (all[j].shadowRoot) {
                  var hit = tryHVeIqInRoot(all[j].shadowRoot);
                  if (hit) return hit;
                }
              }
              return null;
            }
            var byPhSpan = tryHVeIqInRoot(topNode);
            if (byPhSpan) return byPhSpan;
            var edits = [];
            collectEditables(topNode, edits);
            var best = null, bestSc = -9999;
            for (var k = 0; k < edits.length; k++) {
              var e = edits[k];
              if (!visible(e)) continue;
              if (isDanmu(e)) continue;
              var ph = phStr(e);
              var r = e.getBoundingClientRect();
              var sc = 0;
              if (/精彩评论|留下你的精彩|留下.*评论|友善.*评论|发条评论|抢首评|说点.*评论/.test(ph)) sc += 220;
              else if (/留下|精彩|评论/.test(ph)) sc += 140;
              if (r.left > W * 0.36) sc += 55;
              if (r.bottom > H * 0.55) sc += 35;
              var nearList = false;
              for (var m = 0; m < listRects.length; m++) {
                var lr = listRects[m];
                var cx = r.left + r.width / 2;
                if (r.bottom >= lr.top - 40 && cx > lr.left - 80 && cx < lr.right + 280)
                  nearList = true;
              }
              if (nearList) sc += 90;
              var cls = (e.className && e.className.baseVal !== undefined)
                ? String(e.className.baseVal) : String(e.className || '');
              if (cls.indexOf('DraftEditor') >= 0 || cls.indexOf('public-DraftEditor') >= 0) sc += 42;
              if (sc > bestSc) { bestSc = sc; best = e; }
            }
            return best;
            """,
            scope,
        )
        return el
    except Exception:
        return None


def _pick_comment_editor_element_from_point_js(driver: webdriver.Chrome) -> Optional[Any]:
    """占位文案处 elementFromPoint，再沿命中节点向上找 contenteditable（穿透叠层）。"""
    try:
        return driver.execute_script(
            """
            function walk(node, cb) {
              if (!node) return;
              if (node.nodeType === 11) {
                var c = node.firstElementChild;
                while (c) { walk(c, cb); c = c.nextElementSibling; }
                return;
              }
              if (node.nodeType !== 1) return;
              var tag = node.tagName;
              if (tag === 'SPAN' || tag === 'DIV' || tag === 'P' || tag === 'I') {
                var t = (node.textContent || '').trim();
                if (t.indexOf('留下你的精彩评论吧') >= 0 ||
                    (t.indexOf('精彩评论吧') >= 0 && t.indexOf('弹幕') < 0 && t.length < 100)) {
                  cb(node);
                }
              }
              var ch = node.children;
              for (var i = 0; i < ch.length; i++) walk(ch[i], cb);
              var all = node.querySelectorAll('*');
              for (var j = 0; j < all.length; j++) {
                if (all[j].shadowRoot) walk(all[j].shadowRoot, cb);
              }
            }
            function climbToEditable(start) {
              var n = start;
              for (var d = 0; d < 26 && n; d++) {
                if (n.getAttribute && n.getAttribute('contenteditable') === 'true') return n;
                if (n.tagName === 'TEXTAREA') return n;
                n = n.parentElement;
              }
              return null;
            }
            var W = window.innerWidth || 1200, H = window.innerHeight || 800;
            var found = null;
            walk(document.documentElement, function(node) {
              if (found) return;
              var r = node.getBoundingClientRect();
              if (r.width + r.height < 0.5) return;
              if (r.left + r.width / 2 < W * 0.34) return;
              var pts = [
                [r.left + r.width / 2, r.bottom + 6],
                [r.left + r.width / 2, r.bottom + 20],
                [r.left + Math.min(24, r.width * 0.35), r.top + r.height / 2],
              ];
              for (var pi = 0; pi < pts.length; pi++) {
                var x = Math.round(pts[pi][0]), y = Math.round(pts[pi][1]);
                if (x < 3 || y < 3 || x >= W - 3 || y >= H - 3) continue;
                var hit = document.elementFromPoint(x, y);
                if (!hit) continue;
                var ed = climbToEditable(hit);
                if (ed) {
                  var er = ed.getBoundingClientRect();
                  if (er.width > 5 && er.height > 1) {
                    var ph = (ed.getAttribute('data-placeholder') || '') + (ed.getAttribute('placeholder') || '');
                    if (/弹幕/.test(ph)) continue;
                    found = ed;
                    return;
                  }
                }
              }
            });
            return found;
            """
        )
    except Exception:
        return None


def _pick_comment_editor_bruteforce_js(driver: webdriver.Chrome, min_score: float = 35.0) -> Optional[Any]:
    """
    收集页内全部 contenteditable（含 shadow），纯几何 + Draft 特征打分，用于前面策略全失败时的穷尽兜底。
    min_score 越低越敢选（可能误选，最后才用极低阈值）。
    """
    try:
        return driver.execute_script(
            """
            var minSc = Number(arguments[0]);
            if (isNaN(minSc) || minSc < 1) minSc = 20;
            function visible(el) {
              if (!el || el.nodeType !== 1) return false;
              var r = el.getBoundingClientRect();
              if (r.width < 4 || r.height < 2) return false;
              var st = window.getComputedStyle(el);
              return st.visibility !== 'hidden' && st.display !== 'none' &&
                parseFloat(st.opacity || '1') > 0.06;
            }
            function phStr(el) {
              return (el.getAttribute('data-placeholder') || '') +
                (el.getAttribute('placeholder') || '') +
                (el.getAttribute('aria-label') || '');
            }
            function collect(root, out) {
              if (!root || !root.querySelectorAll) return;
              var q = root.querySelectorAll('[contenteditable="true"], textarea');
              for (var i = 0; i < q.length; i++) out.push(q[i]);
              var all = root.querySelectorAll('*');
              for (var j = 0; j < all.length; j++) {
                if (all[j].shadowRoot) collect(all[j].shadowRoot, out);
              }
            }
            var edits = [];
            collect(document, edits);
            var W = window.innerWidth || 1200, H = window.innerHeight || 800;
            var best = null, bestSc = -1e9;
            for (var k = 0; k < edits.length; k++) {
              var e = edits[k];
              if (!visible(e)) continue;
              var ph = phStr(e);
              if (/弹幕|bullet/i.test(ph)) continue;
              var r = e.getBoundingClientRect();
              var cx = r.left + r.width / 2;
              if (cx < W * 0.33) continue;
              if (r.bottom < 72) continue;
              if (cx < W * 0.42 && r.bottom > H * 0.72) continue;
              var sc = 0;
              if (r.left > W * 0.48) sc += 55;
              else if (r.left > W * 0.40) sc += 38;
              if (r.bottom > H * 0.58) sc += 45;
              else if (r.bottom > H * 0.48) sc += 28;
              var cls = (e.className && e.className.baseVal !== undefined)
                ? String(e.className.baseVal) : String(e.className || '');
              if (cls.indexOf('DraftEditor') >= 0 || cls.indexOf('public-DraftEditor') >= 0) sc += 70;
              if (/评论|留下|精彩/.test(ph)) sc += 120;
              if (r.height > 120 && r.width > 200) sc -= 40;
              if (sc > bestSc) { bestSc = sc; best = e; }
            }
            if (best && bestSc >= minSc) return best;
            return null;
            """,
            float(min_score),
        )
    except Exception:
        return None


def _pick_comment_editor_via_douyin_input_container(
    driver: webdriver.Chrome, video_id: str = ""
) -> Optional[Any]:
    """
    与手工快照一致：外层 `div.comment-input-container`，内层 Draft 可能在 shadow。
    必须在「含 comment-list 的侧栏浮层」内查找；全页第一个容器常在视频层，会误触弹幕条且与评论框分离。
    """
    roots = _iter_comment_dialog_roots(driver, video_id)
    if not roots:
        return None
    sels = (
        "div.comment-input-container [contenteditable='true']",
        "div.comment-input-container div.public-DraftEditor-content[contenteditable='true']",
        ".comment-input-inner-container [contenteditable='true']",
        "div[class*='comment-input-inner-container'] [contenteditable='true']",
        "div[class*='comment-input-container'] [contenteditable='true']",
    )
    for root in roots:
        for sel in sels:
            try:
                for e in root.find_elements(By.CSS_SELECTOR, sel):
                    try:
                        if not e.is_displayed() or _element_visible_area(e) < 6:
                            continue
                        if _element_is_danmaku_or_video_bar(driver, e):
                            continue
                        if not _element_in_comment_column_with_list(driver, e):
                            continue
                        return e
                    except Exception:
                        continue
            except Exception:
                continue
        try:
            el = driver.execute_script(
                """
                function walkSh(sub) {
                  if (!sub || !sub.querySelectorAll) return null;
                  var q = sub.querySelector('[contenteditable="true"]');
                  if (q) {
                    var b = q.getBoundingClientRect();
                    if (b.width > 2 && b.height > 1) return q;
                  }
                  var all = sub.querySelectorAll('*');
                  for (var j = 0; j < all.length; j++) {
                    if (all[j].shadowRoot) {
                      var h = walkSh(all[j].shadowRoot);
                      if (h) return h;
                    }
                  }
                  return null;
                }
                function collectContainers(r, acc) {
                  if (!r || !r.querySelectorAll) return;
                  var q = r.querySelectorAll(
                    'div.comment-input-container, div[class*="comment-input-container"]');
                  for (var i = 0; i < q.length; i++) acc.push(q[i]);
                  var all = r.querySelectorAll('*');
                  for (var j = 0; j < all.length; j++) {
                    if (all[j].shadowRoot) collectContainers(all[j].shadowRoot, acc);
                  }
                }
                var acc = [];
                collectContainers(arguments[0], acc);
                for (var k = 0; k < acc.length; k++) {
                  var hit = walkSh(acc[k]);
                  if (hit) return hit;
                }
                return null;
                """,
                root,
            )
            if el is None:
                continue
            try:
                if _element_is_danmaku_or_video_bar(driver, el):
                    continue
                if not _element_in_comment_column_with_list(driver, el):
                    continue
            except Exception:
                continue
            return el
        except Exception:
            continue
    return None


def _merge_js_scope_roots(driver: webdriver.Chrome, video_id: str) -> List[Any]:
    roots: List[Any] = []
    seen: Set[int] = set()
    for r in _comment_overlay_roots_for_video(driver, video_id):
        i = id(r)
        if i not in seen:
            seen.add(i)
            roots.append(r)
    for r in _extra_comment_ui_roots_from_sidebar(driver, video_id):
        i = id(r)
        if i not in seen:
            seen.add(i)
            roots.append(r)
    return roots


def _try_all_comment_editor_strategies(driver: webdriver.Chrome, video_id: str) -> Optional[Any]:
    """
    在本 document 内按顺序穷尽多种方式，直到找到评论输入框（单 Chrome 进程下可全跑一遍）。
    """
    el = _pick_comment_editor_via_douyin_input_container(driver, video_id)
    if el is not None:
        return el
    el = _pick_video_comment_editor_selenium_roots(driver, video_id)
    if el is not None:
        return el
    el = _pick_comment_editor_via_placeholder_text_xpath(driver)
    if el is not None:
        return el
    el = _pick_comment_editor_via_hVeIqFGi_placeholder(driver, video_id)
    if el is not None:
        return el
    for r in _merge_js_scope_roots(driver, video_id):
        try:
            el = _pick_video_comment_editor_js(driver, r)
            if el is not None:
                if _element_is_danmaku_or_video_bar(driver, el):
                    continue
                if not _element_in_comment_column_with_list(driver, el):
                    continue
                return el
        except Exception:
            continue
    el = _pick_video_comment_editor_js(driver, None)
    if el is not None:
        if not _element_is_danmaku_or_video_bar(driver, el) and _element_in_comment_column_with_list(
            driver, el
        ):
            return el
    el = _pick_comment_editor_element_from_point_js(driver)
    if el is not None:
        if not _element_is_danmaku_or_video_bar(driver, el) and _element_in_comment_column_with_list(
            driver, el
        ):
            return el
    el = _pick_comment_editor_bruteforce_js(driver, min_score=48.0)
    if el is not None:
        if not _element_is_danmaku_or_video_bar(driver, el) and _element_in_comment_column_with_list(
            driver, el
        ):
            return el
    el = _pick_comment_editor_bruteforce_js(driver, min_score=28.0)
    if el is not None:
        if not _element_is_danmaku_or_video_bar(driver, el) and _element_in_comment_column_with_list(
            driver, el
        ):
            return el
    el = _pick_comment_editor_bruteforce_js(driver, min_score=12.0)
    if el is not None:
        if not _element_is_danmaku_or_video_bar(driver, el) and _element_in_comment_column_with_list(
            driver, el
        ):
            return el
    return None


def _pick_video_comment_editor(driver: webdriver.Chrome, video_id: str = "") -> Optional[Any]:
    """
    default_content 后在本页穷尽策略；再遍历 iframe，并在每个 iframe 内再套一层子 iframe 重复同样穷尽。
    """
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    el = _try_all_comment_editor_strategies(driver, video_id)
    if el is not None:
        return el
    try:
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
    except Exception:
        frames = []
    for fr in frames:
        try:
            driver.switch_to.default_content()
            driver.switch_to.frame(fr)
        except Exception:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            continue
        try:
            el = _try_all_comment_editor_strategies(driver, video_id)
            if el is not None:
                return el
            try:
                inner = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
            except Exception:
                inner = []
            for fr2 in inner:
                try:
                    driver.switch_to.frame(fr2)
                    el = _try_all_comment_editor_strategies(driver, video_id)
                    if el is not None:
                        return el
                except Exception:
                    pass
                try:
                    driver.switch_to.parent_frame()
                except Exception:
                    try:
                        driver.switch_to.default_content()
                        driver.switch_to.frame(fr)
                    except Exception:
                        break
        except Exception:
            pass
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
    return None


def _ensure_video_tab_and_comment_open(
    driver: webdriver.Chrome,
    video_handle: str,
    video_id: str,
) -> None:
    """从用户主页返回后，评论区常被收起或重绘，需确认标签并必要时再点评论入口。"""
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    try:
        if driver.current_window_handle != video_handle:
            driver.switch_to.window(video_handle)
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 切回视频页标签失败: {e}")
    _rand_sleep(0.35, 0.75)
    if not _comment_list_is_visible(driver):
        logger.info("[SeleniumIntercept] 返回视频页后未检测到 comment-list，重新点开评论区")
        click_comment_panel(driver, video_id)
        _rand_sleep(0.55, 1.15)


def close_video_or_overlay(driver: webdriver.Chrome) -> bool:
    """
    优先点悬浮窗/播放器上的关闭控件，保持搜索列表与筛选态；避免整页 navigate。
    返回是否至少完成一轮点击尝试。
    """
    tried = False
    css_list = [
        "div.K5AaygDB",
        "div[role='dialog'] button[aria-label*='关闭']",
        "div[role='dialog'] [aria-label*='关闭']",
        "[data-e2e*='close']",
        "[data-e2e*='Close']",
        "div[role='dialog'] [class*='close']",
    ]
    for _ in range(2):
        for css in css_list:
            try:
                for e in driver.find_elements(By.CSS_SELECTOR, css):
                    try:
                        if not e.is_displayed():
                            continue
                        tried = True
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", e)
                        time.sleep(0.12)
                        try:
                            driver.execute_script(
                                "var n=arguments[0]; if(n&&n.click) n.click();",
                                e,
                            )
                        except WebDriverException:
                            pass
                        except Exception:
                            try:
                                e.click()
                            except Exception:
                                pass
                        _rand_sleep(0.45, 0.85)
                    except Exception:
                        continue
            except Exception:
                continue
        try:
            for el in driver.find_elements(
                By.XPATH,
                "//div[@role='dialog']//*[self::button or self::div][contains(@aria-label,'关闭')]",
            ):
                if el.is_displayed():
                    tried = True
                    driver.execute_script("arguments[0].click();", el)
                    _rand_sleep(0.45, 0.85)
                    break
        except Exception:
            pass
    if not tried:
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            tried = True
            _rand_sleep(0.35, 0.55)
        except Exception:
            pass
    return tried


def scroll_comment_list(driver: webdriver.Chrome, px: int) -> None:
    scrolled = False
    for sel in (
        '[data-e2e="comment-list"]',
        "div.Rwb9ssMc",
        "[class*='comment-mainContent']",
        "[class*='ufktjxUm']",
    ):
        try:
            lst = driver.find_element(By.CSS_SELECTOR, sel)
            if lst.is_displayed():
                driver.execute_script("arguments[0].scrollTop += arguments[1];", lst, px)
                scrolled = True
                break
        except Exception:
            continue
    if not scrolled:
        try:
            driver.execute_script("window.scrollBy(0, arguments[0]);", px)
        except Exception:
            pass
    _rand_sleep(0.65, 1.15)


def list_comment_items(driver: webdriver.Chrome) -> List[Any]:
    sels = (
        '[data-e2e="comment-item"]',
        'div[class*="CommentItem"]',
        'div[class*="comment-item"]',
        'li[class*="comment"]',
    )
    for sel in sels:
        try:
            items = driver.find_elements(By.CSS_SELECTOR, sel)
            vis = [i for i in items if i.is_displayed()]
            if vis:
                return vis
        except Exception:
            continue
    return []


def extract_comment_row_info(item) -> Tuple[str, Optional[Any]]:
    """返回 (可见文本, 用户主页链接元素)。"""
    try:
        txt = (item.text or "").strip()
    except Exception:
        txt = ""
    link_el = None
    try:
        link_el = item.find_element(By.CSS_SELECTOR, 'a[href*="/user/"]')
    except NoSuchElementException:
        pass
    return txt, link_el


def _element_inside_video_comment_panel(driver: webdriver.Chrome, el: Any) -> bool:
    """排除视频页评论区输入框，避免与私信 Draft 编辑器混淆。"""
    try:
        return bool(
            driver.execute_script(
                """
                var n = arguments[0];
                while (n) {
                  if (!n.getAttribute) { n = n.parentElement; continue; }
                  var e2e = n.getAttribute('data-e2e');
                  if (e2e === 'comment-list' || e2e === 'comment-input') return true;
                  if ((n.id || '') === 'comment-input-container') return true;
                  var cls = (n.className && n.className.baseVal !== undefined)
                    ? String(n.className.baseVal) : String(n.className || '');
                  if (cls.indexOf('comment-input-container') >= 0) return true;
                  n = n.parentElement;
                }
                return false;
                """,
                el,
            )
        )
    except Exception:
        return False


# 私信输入区选择器顺序：Draft 在前（抖音 Web 常见）。
# 注意：不要用过于泛化的 contenteditable 做「弹层已出」判断——主页上常有其它 Draft 节点在 DOM 里显示为 true，
# 但实际聊天浮层并未打开，必须配合 _dm_editor_is_real_chat_layer 做命中与壳层校验。
_DM_EDITOR_CSS_ORDER: Tuple[str, ...] = (
    "div.public-DraftEditor-content[contenteditable='true']",
    "div.notranslate.public-DraftEditor-content[contenteditable='true']",
    "div[contenteditable='true'][data-slate-editor='true']",
    "div[role='textbox'][contenteditable='true']",
    "div[contenteditable='true'][data-placeholder]",
    "textarea[placeholder*='消息']",
    "textarea[placeholder*='私信']",
    "textarea[placeholder*='发送']",
    "textarea[placeholder*='聊聊']",
    "textarea",
    "div.public-DraftStyleDefault-block",
    "div[contenteditable='true']",
)


def _dm_editor_is_real_chat_layer(driver: webdriver.Chrome, el: Any) -> bool:
    """
    真·私信聊天浮层：几何中心等处 elementFromPoint 须落在该输入框子树内（未被视频/其它层盖住）；
    且须在 fixed/sticky 的足够大的面板内，面板文案含聊天相关提示，或符合右侧会话栏布局（避免主页其它 Draft 误判）。
    """
    try:
        return bool(
            driver.execute_script(
                """
                var el = arguments[0];
                if (!el || !el.getBoundingClientRect) return false;
                var r = el.getBoundingClientRect();
                if (r.width < 80 || r.height < 10) return false;
                var W = window.innerWidth || 1200, H = window.innerHeight || 800;
                if (r.bottom < 30 || r.top > H - 8) return false;

                function hitSelf(cx, cy) {
                  if (cx < 2 || cy < 2 || cx >= W - 2 || cy >= H - 2) return false;
                  var top = document.elementFromPoint(cx, cy);
                  if (!top) return false;
                  var n = top;
                  while (n) {
                    if (n === el) return true;
                    n = n.parentElement;
                  }
                  try { return el.contains(top); } catch (e) { return false; }
                }
                var cx0 = Math.floor(r.left + Math.min(r.width * 0.5, 120));
                var cy0 = Math.floor(r.top + Math.min(r.height * 0.5, 24));
                var cx1 = Math.floor(r.left + Math.min(32, r.width * 0.35));
                var cy1 = Math.floor(r.top + Math.min(12, r.height * 0.45));
                if (!hitSelf(cx0, cy0) || !hitSelf(cx1, cy1)) return false;

                var dp = el.getAttribute('data-placeholder') || el.getAttribute('aria-placeholder') || '';
                if (/消息|聊聊|说点|私信|发送|按住/i.test(dp)) return true;
                try {
                  var ap = el.closest && el.closest('[aria-modal="true"]');
                  if (ap) {
                    var brm = ap.getBoundingClientRect();
                    if (brm.width >= 220 && brm.height >= 100) return true;
                  }
                } catch (e3) {}

                var p = el;
                for (var d = 0; d < 24 && p; d++) {
                  var st = window.getComputedStyle(p);
                  var pos = st.position;
                  if (pos === 'fixed' || pos === 'sticky') {
                    var br = p.getBoundingClientRect();
                    if (br.width < 220 || br.height < 100) { p = p.parentElement; continue; }
                    var slice = '';
                    try { slice = (p.innerText || '').slice(0, 500); } catch (e2) { slice = ''; }
                    if (/发消息|私信|发送消息|说点什么|输入消息|聊聊|按住\\s*说话|Enter|换行发送/i.test(slice))
                      return true;
                    if (br.width >= 300 && br.height >= 160 && br.left >= W * 0.28)
                      return true;
                  }
                  p = p.parentElement;
                }
                return false;
                """,
                el,
            )
        )
    except Exception:
        return False


def _collect_dm_editor_candidates(driver: webdriver.Chrome) -> List[Any]:
    out: List[Any] = []
    for sel in _DM_EDITOR_CSS_ORDER:
        try:
            for e in driver.find_elements(By.CSS_SELECTOR, sel):
                try:
                    if not e.is_displayed():
                        continue
                    r = e.rect
                    if r.get("height", 0) < 12 or r.get("width", 0) < 50:
                        continue
                    if _element_inside_video_comment_panel(driver, e):
                        continue
                    out.append(e)
                except Exception:
                    continue
        except Exception:
            continue
    return out


def _pick_dm_chat_editor(driver: webdriver.Chrome) -> Optional[Any]:
    """取当前页面上「已真正弹出」的私信聊天输入控件。"""
    for e in _collect_dm_editor_candidates(driver):
        try:
            if _dm_editor_is_real_chat_layer(driver, e):
                return e
        except Exception:
            continue
    return None


def _videos_set_pointer_events(driver: webdriver.Chrome, value: str) -> None:
    """临时把页面内 video 设为 pointer-events:none，避免挡住私信/评论输入区的坐标点击与 focus。"""
    try:
        driver.execute_script(
            "document.querySelectorAll('video').forEach(function(v){ v.style.pointerEvents = arguments[0] || ''; });",
            value,
        )
    except Exception:
        pass


def _dm_composer_visible(driver: webdriver.Chrome) -> bool:
    """私信聊天输入区是否已可见（短检，用于判断「点私信」是否真正弹出层）。"""
    return _pick_dm_chat_editor(driver) is not None


def _find_dm_button(driver: webdriver.Chrome) -> Optional[Any]:
    for text in ("私信", "发消息", "消息"):
        try:
            for el in driver.find_elements(
                By.XPATH,
                f"//span[contains(@class,'semi-button-content') and normalize-space()='{text}']",
            ):
                try:
                    if el.is_displayed():
                        return el
                except Exception:
                    continue
        except Exception:
            continue
    for xp in (
        "//button[.//span[normalize-space()='私信']]",
        "//div[.//span[normalize-space()='私信']]",
        "//*[self::button][contains(normalize-space(),'私信')]",
    ):
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed():
                        return el
                except Exception:
                    continue
        except Exception:
            continue
    return None


def click_follow_then_dm(
    driver: webdriver.Chrome,
    *,
    dm_open_wait_min: float = 5.0,
    dm_open_wait_max: float = 8.0,
    dm_click_retries: int = 4,
    dm_retry_gap_min: float = 2.0,
    dm_retry_gap_max: float = 4.5,
) -> bool:
    """在用户主页：先关注，再多次尝试点「私信」直到聊天输入区出现（私密账号仍尝试私信，不误判整页文案）。"""
    try:
        follow = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//span[contains(@class,'semi-button-content') and normalize-space()='关注']")
            )
        )
        follow.click()
        _rand_sleep(0.5, 0.9)
    except TimeoutException:
        try:
            follow = driver.find_element(
                By.XPATH,
                "//button[.//span[normalize-space()='关注']] | //div[.//span[normalize-space()='关注']]",
            )
            follow.click()
            _rand_sleep(0.5, 0.9)
        except Exception:
            logger.info("[SeleniumIntercept] 未找到「关注」或已关注")
    except Exception as e:
        logger.info(f"[SeleniumIntercept] 点击关注异常（可能已关注）: {e}")

    try:
        if driver.find_elements(By.XPATH, "//*[contains(text(),'已请求')]"):
            logger.info("[SeleniumIntercept] 关注请求待通过，跳过私信")
            return False
    except Exception:
        pass

    n_try = max(1, int(dm_click_retries))
    gap_a, gap_b = float(dm_retry_gap_min), float(dm_retry_gap_max)
    if gap_b < gap_a:
        gap_a, gap_b = gap_b, gap_a

    for attempt in range(n_try):
        dm_btn = _find_dm_button(driver)
        if dm_btn is None:
            logger.warning("[SeleniumIntercept] 未找到私信入口")
            return False
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dm_btn)
            time.sleep(0.12)
            try:
                dm_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", dm_btn)
        except Exception as e:
            logger.warning(f"[SeleniumIntercept] 第 {attempt + 1} 次点击私信异常: {e}")
        gap = random.uniform(gap_a, gap_b)
        logger.info(
            f"[SeleniumIntercept] 已点私信（第 {attempt + 1}/{n_try} 次），等待 {gap:.1f}s 看是否弹出输入区…"
        )
        time.sleep(gap)
        if _dm_composer_visible(driver):
            logger.info("[SeleniumIntercept] 私信聊天输入区已出现")
            wmin, wmax = float(dm_open_wait_min), float(dm_open_wait_max)
            if wmax < wmin:
                wmin, wmax = wmax, wmin
            settle = random.uniform(wmin, wmax)
            logger.info(f"[SeleniumIntercept] 输入区出现后稳定等待 {settle:.1f}s 再输入…")
            time.sleep(settle)
            return True

    logger.warning(f"[SeleniumIntercept] 已点私信 {n_try} 次仍未检测到聊天输入区")
    return False


def _count_substring(hay: str, needle: str) -> int:
    if not needle:
        return 0
    return (hay or "").count(needle)


def _dm_snippet_visible_outside_draft(driver: webdriver.Chrome, snippet: str) -> bool:
    """
    在真实 DOM（含 open shadowRoot）里找可见文本是否含 snippet，且不在 Draft/私信输入框子树内。
    用于 page_source 不增长或气泡在 shadow 内时仍能判定发送成功。
    """
    if not snippet or len(snippet) > 500:
        return False
    try:
        return bool(
            driver.execute_script(
                """
                var sn = arguments[0];
                function visible(el) {
                  if (!el || el.nodeType !== 1) return false;
                  var r = el.getBoundingClientRect();
                  if (r.width < 1 && r.height < 1) return false;
                  var st = window.getComputedStyle(el);
                  if (st.visibility === 'hidden' || st.display === 'none') return false;
                  if (parseFloat(st.opacity || '1') < 0.05) return false;
                  return true;
                }
                function inDraftOrComposer(el) {
                  var p = el;
                  for (var d = 0; d < 32 && p; d++) {
                    if (p.getAttribute && p.getAttribute('contenteditable') === 'true') return true;
                    if (p.tagName === 'TEXTAREA') return true;
                    var cls = p.className || '';
                    if (typeof cls !== 'string') cls = String(cls || '');
                    if (cls.indexOf('DraftEditor') >= 0 || cls.indexOf('public-DraftEditor') >= 0)
                      return true;
                    p = p.parentElement;
                  }
                  return false;
                }
                var stack = [document.body];
                while (stack.length) {
                  var r = stack.pop();
                  if (!r || !r.querySelectorAll) continue;
                  var hosts = r.querySelectorAll('*');
                  for (var si = 0; si < hosts.length; si++) {
                    var h = hosts[si];
                    if (h.shadowRoot) stack.push(h.shadowRoot);
                  }
                  var nodes = r.querySelectorAll('div, span, p, li');
                  for (var j = 0; j < nodes.length; j++) {
                    var e = nodes[j];
                    if (!visible(e)) continue;
                    if (inDraftOrComposer(e)) continue;
                    var it = '';
                    try { it = (e.innerText || '').trim(); } catch (ex) { continue; }
                    if (it.indexOf(sn) < 0) continue;
                    if (it.length > 900) continue;
                    if (it === sn || it.length <= sn.length + 80) return true;
                  }
                }
                return false;
                """,
                snippet,
            )
        )
    except Exception:
        return False


def _dm_echo_detected(driver: webdriver.Chrome, snippet: str, baseline_html_count: int) -> bool:
    if not snippet:
        return False
    if _count_substring(driver.page_source, snippet) > baseline_html_count:
        return True
    return _dm_snippet_visible_outside_draft(driver, snippet)


def send_dm_and_verify(driver: webdriver.Chrome, msg: str, *, editor_wait: float = 18.0) -> bool:
    msg = (msg or "").strip()
    if not msg:
        return False

    editor = None
    try:
        editor = WebDriverWait(driver, max(5.0, editor_wait)).until(_pick_dm_chat_editor)
    except TimeoutException:
        editor = _pick_dm_chat_editor(driver)
    if editor is None:
        logger.warning("[SeleniumIntercept] 未找到私信输入框")
        _safe_screenshot(driver, "dm_no_editor")
        return False

    snippet = msg[:120] if len(msg) > 120 else msg
    # 必须在输入前采样：发送后编辑区清空 + 气泡出现，page_source 里子串计数可能不变，导致误判失败。
    baseline_html = _count_substring(driver.page_source, snippet)

    def _type_into_dm(ed: Any) -> None:
        # 勿对 contenteditable 做原生 click：抖音页面上层 video 常拦截命中，报 ElementClickInterceptedException。
        _videos_set_pointer_events(driver, "none")
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center',inline:'nearest'}); arguments[0].focus();",
                ed,
            )
            time.sleep(0.12)
            ed.send_keys(Keys.CONTROL, "a")
            ed.send_keys(Keys.BACKSPACE)
            ed.send_keys(msg)
            time.sleep(0.2)
            ed.send_keys(Keys.ENTER)
        finally:
            _videos_set_pointer_events(driver, "")

    try:
        _type_into_dm(editor)
    except StaleElementReferenceException:
        editor = _pick_dm_chat_editor(driver)
        if editor is None:
            logger.warning("[SeleniumIntercept] 私信输入框已失效且未找到新节点")
            _safe_screenshot(driver, "dm_type_fail")
            return False
        try:
            _type_into_dm(editor)
        except Exception as e:
            logger.warning(f"[SeleniumIntercept] 私信输入失败: {e}")
            _safe_screenshot(driver, "dm_type_fail")
            return False
    except Exception as e:
        logger.warning(f"[SeleniumIntercept] 私信输入失败: {e}")
        _safe_screenshot(driver, "dm_type_fail")
        return False

    time.sleep(2.2)
    try:
        WebDriverWait(driver, 22).until(
            lambda d: _dm_echo_detected(d, snippet, baseline_html)
        )
        if _count_substring(driver.page_source, snippet) <= baseline_html:
            logger.info(
                "[SeleniumIntercept] 私信回显：DOM（含 shadow）中可见气泡/列表含文案；"
                "page_source 子串计数未高于发送前，旧逻辑会误判失败"
            )
        return True
    except TimeoutException:
        if _dm_echo_detected(driver, snippet, baseline_html):
            logger.info("[SeleniumIntercept] 私信回显：超时边界再次检测通过")
            return True
        logger.warning("[SeleniumIntercept] 私信未检测到回显")
        _safe_screenshot(driver, "dm_no_echo")
        return False


def post_video_comment_and_verify(
    driver: webdriver.Chrome,
    text: str,
    *,
    video_id: str = "",
    editor_wait: float = 18.0,
) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    snippet = text[:120] if len(text) > 120 else text

    try:
        editor = None
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        _activate_comment_side_before_input(driver)
        _scroll_comment_list_to_bottom(driver)
        time.sleep(0.08)
        try:
            editor = WebDriverWait(driver, max(6.0, float(editor_wait))).until(
                lambda d: _pick_video_comment_editor(d, video_id)
            )
        except TimeoutException:
            editor = _pick_video_comment_editor(driver, video_id)
        if editor is None:
            logger.warning("[SeleniumIntercept] 未找到视频评论输入框（可加大 --comment-editor-wait）")
            _safe_screenshot(driver, "comment_no_editor")
            return False

        baseline = _count_substring(driver.page_source, snippet)

        def _type_comment(ed: Any) -> None:
            _videos_set_pointer_events(driver, "none")
            try:
                _prime_comment_editor_click(driver, ed)
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center',inline:'nearest'}); arguments[0].focus();",
                    ed,
                )
                time.sleep(0.12)
                ed.send_keys(Keys.CONTROL, "a")
                ed.send_keys(Keys.BACKSPACE)
                ed.send_keys(text)
                time.sleep(0.2)
                ed.send_keys(Keys.ENTER)
            finally:
                _videos_set_pointer_events(driver, "")

        try:
            _type_comment(editor)
        except StaleElementReferenceException:
            editor = _pick_video_comment_editor(driver, video_id)
            if editor is None:
                logger.warning("[SeleniumIntercept] 评论输入框已失效且未找到新节点")
                _safe_screenshot(driver, "comment_no_editor")
                return False
            try:
                _type_comment(editor)
            except Exception as e:
                logger.warning(f"[SeleniumIntercept] 评论输入失败: {e}")
                return False
        except Exception as e:
            logger.warning(f"[SeleniumIntercept] 评论输入失败: {e}")
            return False

        time.sleep(1.5)
        try:
            WebDriverWait(driver, 14).until(
                lambda d: _count_substring(d.page_source, snippet) > baseline
            )
            return True
        except TimeoutException:
            logger.warning("[SeleniumIntercept] 评论未检测到回显")
            _safe_screenshot(driver, "comment_no_echo")
            return False
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass


def run(args: argparse.Namespace) -> int:
    day = _today_calendar()
    dm_path = Path(args.dedup_path)
    comment_log = Path(args.comment_log_path)

    lifetime_dm = load_lifetime_dm_user_ids(dm_path)
    commented_videos = load_commented_video_ids(comment_log)
    dm_today = count_dm_success_on_date(dm_path, day)
    comment_today = count_comment_success_on_date(comment_log, day)
    logger.info(
        f"[SeleniumIntercept] 自然日 {day} 已成功私信 {dm_today}/{args.dm_daily_limit}，"
        f"已成功评论 {comment_today}/{args.comment_daily_limit}；终身已私信用户数 {len(lifetime_dm)}"
    )

    use_doubao = not bool(getattr(args, "no_doubao", False))
    persona_kb = _load_persona_from_config()
    ol = (getattr(args, "persona_overlay_json", "") or "").strip()
    if ol:
        persona_kb = _apply_persona_overlay_json(persona_kb, ol)
    if use_doubao and not USE_TEMP_INPUT_666:
        logger.info(
            "[SeleniumIntercept] 豆包：已开启（私信/评论走 prompts + config.yaml persona）；"
            "若需固定文案请加 --no-doubao"
        )

    user_data = Path(args.user_data_dir).resolve()
    expected_ud = CHROME_USER_DATA_DIR_DEFAULT.resolve()
    if user_data == expected_ud:
        logger.info(f"[SeleniumIntercept] Chrome user-data-dir 与 BrowserManager 一致: {user_data}")
    else:
        logger.warning(
            f"[SeleniumIntercept] user-data-dir={user_data} ，与系统内 BrowserManager 默认 {expected_ud} 不一致；"
            f"若需同一抖音登录态，请使用默认目录或不传 --user-data-dir"
        )
    profile = args.profile_directory or _load_profile_dir_from_config()
    logger.info(f"[SeleniumIntercept] Chrome profile-directory: {profile}")
    logger.info("[SeleniumIntercept] 正在启动 Chrome（若长时间无输出，请关闭占用同一 user-data-dir 的手动 Chrome 后重试）…")
    driver = create_driver(user_data, profile, args.headless)
    logger.info("[SeleniumIntercept] Chrome 已启动")

    def _human_op_sleep() -> None:
        lo = max(0.0, float(getattr(args, "human_delay_min", 3.0)))
        hi = max(lo, float(getattr(args, "human_delay_max", 7.0)))
        time.sleep(random.uniform(lo, hi))

    processed_videos: Set[str] = set()
    kw_seq: List[str] = []
    kw_idx = 0
    kw_fp = ""
    active_keyword = (args.keyword or "").strip() or "不锈钢门窗"

    try:
        kw_seq = _industry_keyword_sequence(persona_kb, args.keyword)
        kw_fp = _keyword_rotation_fingerprint(kw_seq)
        nk = max(1, len(kw_seq))
        kw_idx = _load_rotation_next_start(KEYWORD_ROTATION_STATE, kw_fp, nk) % nk
        active_keyword = kw_seq[kw_idx]
        logger.info(
            f"[SeleniumIntercept] 行业关键词轮换: 共{len(kw_seq)}个，"
            f"下次起始下标(状态文件)={kw_idx}，本次先搜 {active_keyword!r}"
        )
        sd = max(0.0, float(getattr(args, "start_delay_seconds", 0.0) or 0.0))
        if sd > 0:
            logger.info(f"[SeleniumIntercept] 启动延迟 {sd:.0f}s 后开始搜索…")
            time.sleep(sd)
        open_search(driver, active_keyword)
        _human_op_sleep()
        # 每换一个搜索词后需重新点「视频 Tab + 筛选」；同页尽量不反复 driver.get 列表
        list_page_url = ""
        search_filters_applied = False

        videos_done = 0
        keyword_round_failures = 0
        while videos_done < args.max_videos:
            if dm_today >= args.dm_daily_limit and comment_today >= args.comment_daily_limit:
                logger.info("[SeleniumIntercept] 当日私信与评论均已达上限，结束")
                break

            if not search_filters_applied:
                try:
                    apply_video_filters(driver)
                except WebDriverException as e:
                    err = str(e).lower()
                    if "no such window" in err or "target window already closed" in err:
                        logger.error("[SeleniumIntercept] 浏览器窗口已关闭，结束运行")
                        break
                    raise
                search_filters_applied = True
                _human_op_sleep()
                try:
                    list_page_url = driver.current_url or ""
                except Exception:
                    list_page_url = ""
            else:
                _human_op_sleep()

            picked = pick_next_video_by_list_order(
                driver,
                processed_videos,
                args.min_likes,
                max_scroll_rounds=args.search_scroll_rounds,
                scroll_px=args.search_scroll_px,
                no_new_streak_max=args.search_no_new_streak,
            )

            if picked is None:
                logger.info(
                    "[SeleniumIntercept] 当前关键词下列表无可用视频（已尽量下滑至无新卡）。"
                    "将轮换下一行业关键词；可调低 --min-likes 或看 list_no_pick 截图。"
                )
                _safe_screenshot(driver, "list_no_pick")
                keyword_round_failures += 1
                kw_idx = (kw_idx + 1) % nk
                active_keyword = kw_seq[kw_idx]
                logger.info(
                    f"[SeleniumIntercept] 轮换搜索词 → [{kw_idx + 1}/{nk}] {active_keyword!r}"
                )
                open_search(driver, active_keyword)
                _human_op_sleep()
                search_filters_applied = False
                list_page_url = ""
                if keyword_round_failures >= nk:
                    logger.info("[SeleniumIntercept] 全部关键词均已尝试仍无可用列表，结束")
                    break
                continue
            keyword_round_failures = 0

            href, likes, vid, link_el, list_caption = picked
            logger.info(f"[SeleniumIntercept] 打开视频 {vid} likes={likes}")
            _human_op_sleep()
            if (list_caption or "").strip():
                lc = (list_caption or "").strip()
                logger.info(
                    f"[SeleniumIntercept] 当前视频列表文案（供 AI）: {lc[:160]!r}"
                    f"{'…' if len(lc) > 160 else ''}"
                )

            before_handles = list(driver.window_handles)
            _human_op_sleep()
            mode = click_open_video(driver, link_el)
            if mode == "new":
                _switch_to_newest(driver)
            _rand_sleep(0.5, 1.15)
            video_handle = driver.current_window_handle

            detail_timeout = float(args.detail_wait)
            if not wait_video_detail_ready(driver, vid, timeout=detail_timeout):
                if mode == "same" and try_open_video_in_new_tab(driver, link_el):
                    _switch_to_newest(driver)
                    mode = "new"
                    video_handle = driver.current_window_handle
                    _rand_sleep(0.45, 0.95)
                    if wait_video_detail_ready(driver, vid, timeout=detail_timeout):
                        logger.info("[SeleniumIntercept] Ctrl+新开标签后已进入视频详情页")
                    else:
                        processed_videos.add(vid)
                        if mode == "same":
                            close_video_or_overlay(driver)
                        restore_search_list_context(
                            driver,
                            list_page_url=list_page_url,
                            mode=mode,
                            before_handles=before_handles,
                        )
                        videos_done += 1
                        continue
                else:
                    processed_videos.add(vid)
                    close_video_or_overlay(driver)
                    restore_search_list_context(
                        driver, list_page_url=list_page_url, mode=mode, before_handles=before_handles
                    )
                    videos_done += 1
                    continue

            processed_videos.add(vid)

            video_play_count = 0

            try:
                if has_no_comments_placeholder(driver, vid):
                    logger.info("[SeleniumIntercept] 无评论（抢首评/暂无评论），关闭")
                    close_video_or_overlay(driver)
                    restore_search_list_context(
                        driver, list_page_url=list_page_url, mode=mode, before_handles=before_handles
                    )
                    videos_done += 1
                    continue

                if not click_comment_panel(driver, vid):
                    close_video_or_overlay(driver)
                    restore_search_list_context(
                        driver, list_page_url=list_page_url, mode=mode, before_handles=before_handles
                    )
                    videos_done += 1
                    continue

                _human_op_sleep()
                first_intent_this_video = False
                first_intent_comment_text = ""
                seen_snippets: Set[str] = set()

                for _round in range(args.comment_rounds):
                    _rand_sleep(0.45, 0.95)
                    items = list_comment_items(driver)
                    for item in items:
                        try:
                            txt, user_link = extract_comment_row_info(item)
                        except StaleElementReferenceException:
                            continue
                        if not txt or len(txt) > 500:
                            continue
                        if "下载抖音精选" in txt or "京ICP备" in txt:
                            continue
                        sig = txt[:120].replace("\n", " ")
                        if sig in seen_snippets:
                            continue

                        if not _is_intent_comment(txt, persona_kb):
                            continue
                        if args.ai_intent and use_doubao:
                            if not ai_intent_doubao_second_pass(txt, active_keyword):
                                logger.info("[SeleniumIntercept] 豆包二判：非意向客户，跳过")
                                continue

                        seen_snippets.add(sig)
                        if not first_intent_this_video:
                            first_intent_this_video = True
                            first_intent_comment_text = txt
                            logger.info(f"[SeleniumIntercept] 本视频首次意向: {txt[:60]!r}")

                        user_href = ""
                        if user_link is not None:
                            try:
                                user_href = user_link.get_attribute("href") or ""
                            except StaleElementReferenceException:
                                user_href = ""
                        uid = _normalize_user_id(user_href)
                        if not uid:
                            logger.warning("[SeleniumIntercept] 无法解析用户 id，跳过私信")
                            continue

                        need_dm = uid not in lifetime_dm and dm_today < args.dm_daily_limit
                        if not need_dm:
                            logger.info(f"[SeleniumIntercept] 跳过私信 uid={uid[:16]}… （已私信或当日已满）")
                            continue

                        before_u = list(driver.window_handles)
                        try:
                            driver.execute_script("window.open(arguments[0], '_blank');", user_href)
                        except Exception as e:
                            logger.warning(f"[SeleniumIntercept] window.open 用户页失败: {e}")
                            continue
                        if not _wait_new_window(driver, before_u):
                            logger.warning("[SeleniumIntercept] 用户页未新开窗口")
                            continue
                        _switch_to_newest(driver)
                        _rand_sleep(0.8, 1.4)
                        user_url = driver.current_url

                        ok_flow = click_follow_then_dm(
                            driver,
                            dm_open_wait_min=args.dm_open_wait_min,
                            dm_open_wait_max=args.dm_open_wait_max,
                            dm_click_retries=args.dm_click_retries,
                            dm_retry_gap_min=args.dm_retry_gap_min,
                            dm_retry_gap_max=args.dm_retry_gap_max,
                        )
                        dm_text = build_dm_text(
                            txt,
                            use_doubao,
                            args.fixed_dm,
                            keyword=active_keyword,
                            list_caption=list_caption or "",
                            persona=persona_kb,
                        )
                        sent_ok = False
                        if ok_flow:
                            sent_ok = send_dm_and_verify(
                                driver, dm_text, editor_wait=args.dm_editor_wait
                            )

                        if sent_ok:
                            dm_today += 1
                            lifetime_dm.add(uid)
                            _append_jsonl(
                                dm_path,
                                {
                                    "user_id": uid,
                                    "user_url": user_url,
                                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "keyword": active_keyword,
                                    "video_id": vid,
                                    "intent_snippet": txt[:300],
                                    "dm_text": dm_text,
                                    "success": True,
                                },
                            )
                            logger.info(f"[SeleniumIntercept] ✅ 私信成功 dm_today={dm_today}")
                        else:
                            logger.info("[SeleniumIntercept] 私信未成功，不写入终身去重")

                        try:
                            driver.close()
                        except Exception:
                            pass
                        driver.switch_to.window(video_handle)
                        _rand_sleep(0.5, 1.0)

                        if dm_today >= args.dm_daily_limit:
                            logger.info("[SeleniumIntercept] 当日私信已达上限")
                            break

                    scroll_comment_list(driver, args.comment_scroll_px)
                    _rand_sleep(0.55, 1.0)

                # 素材评论：首次意向即评一次
                if (
                    first_intent_this_video
                    and vid not in commented_videos
                    and comment_today < args.comment_daily_limit
                ):
                    _ensure_video_tab_and_comment_open(driver, video_handle, vid)
                    ctext = build_comment_text(
                        active_keyword,
                        use_doubao,
                        args.fixed_comment,
                        list_caption=list_caption or "",
                        intent_snippet=first_intent_comment_text,
                        persona=persona_kb,
                    )
                    if post_video_comment_and_verify(
                        driver,
                        ctext,
                        video_id=vid,
                        editor_wait=args.comment_editor_wait,
                    ):
                        comment_today += 1
                        commented_videos.add(vid)
                        _append_jsonl(
                            comment_log,
                            {
                                "video_id": vid,
                                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "keyword": active_keyword,
                                "text": ctext,
                                "success": True,
                                "play_count": video_play_count,
                            },
                        )
                        logger.info(f"[SeleniumIntercept] ✅ 视频评论成功 comment_today={comment_today}")
                        _log_today_comment_exposure(comment_log, day)
                    else:
                        _append_jsonl(
                            comment_log,
                            {
                                "video_id": vid,
                                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "keyword": active_keyword,
                                "text": ctext,
                                "success": False,
                                "play_count": video_play_count,
                            },
                        )
                elif first_intent_this_video and vid in commented_videos:
                    logger.info("[SeleniumIntercept] 该视频历史已成功评论，跳过")
                elif first_intent_this_video and comment_today >= args.comment_daily_limit:
                    logger.info("[SeleniumIntercept] 当日评论已达上限，跳过素材评论")

                close_video_or_overlay(driver)
                _human_op_sleep()
                restore_search_list_context(
                    driver, list_page_url=list_page_url, mode=mode, before_handles=before_handles
                )

            except WebDriverException as e:
                logger.exception(f"[SeleniumIntercept] 处理视频异常: {e}")
                _safe_screenshot(driver, "error")
                try:
                    if mode == "same":
                        close_video_or_overlay(driver)
                    restore_search_list_context(
                        driver, list_page_url=list_page_url, mode=mode, before_handles=before_handles
                    )
                except Exception:
                    try:
                        if len(driver.window_handles) > 1:
                            driver.close()
                            driver.switch_to.window(before_handles[0])
                        elif list_page_url:
                            restore_search_list_context(
                                driver,
                                list_page_url=list_page_url,
                                mode="same",
                                before_handles=before_handles,
                                force_reload=True,
                            )
                    except Exception:
                        pass

            videos_done += 1

        logger.info(
            f"[SeleniumIntercept] 结束：本 run 处理约 {videos_done} 个候选视频；"
            f"当日私信成功累计 {dm_today}，评论成功累计 {comment_today}"
        )
        _log_today_comment_exposure(comment_log, day)
        return 0
    finally:
        try:
            if kw_seq:
                nk3 = len(kw_seq)
                _save_rotation_next_start(
                    KEYWORD_ROTATION_STATE,
                    kw_fp,
                    (kw_idx + 1) % nk3,
                    nk3,
                )
        except Exception as e:
            logger.warning(f"[SeleniumIntercept] 保存关键词轮换状态失败: {e}")
        try:
            driver.quit()
        except Exception:
            pass


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="抖音截流 Selenium 脚本")
    p.add_argument("--keyword", type=str, default="不锈钢门窗")
    p.add_argument(
        "--min-likes",
        type=int,
        default=20,
        help="须解析到点赞且 likes>=该值；likes<=0 不入选。不卡赞数用 --min-likes 0",
    )
    p.add_argument("--max-videos", type=int, default=30, help="本轮最多依次处理的视频个数上限")
    p.add_argument("--dm-daily-limit", type=int, default=10, help="自然日私信成功上限（默认 10）")
    p.add_argument("--comment-daily-limit", type=int, default=12, help="自然日评论成功上限（默认 12）")
    p.add_argument("--dedup-path", type=str, default=str(DEDUP_DM_DEFAULT))
    p.add_argument("--comment-log-path", type=str, default=str(COMMENT_LOG_DEFAULT))
    p.add_argument(
        "--user-data-dir",
        type=str,
        default=str(CHROME_USER_DATA_DIR_DEFAULT),
        help="与 BrowserManager 相同默认：pixelle_wrapper/browser_data/chrome_user_data",
    )
    p.add_argument("--profile-directory", type=str, default="", help="留空则读 config.yaml 的 browser.profile_directory")
    p.add_argument("--headless", action="store_true", default=False)
    p.add_argument(
        "--no-doubao",
        action="store_true",
        help="关闭豆包：私信/评论使用 --fixed-dm 与 --fixed-comment（默认启用豆包）",
    )
    p.add_argument(
        "--use-doubao",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--ai-intent",
        action="store_true",
        help="命中内置/persona 意向词后，再用豆包二次判定（需 --no-doubao 关闭时仅关键词）",
    )
    p.add_argument(
        "--start-delay-seconds",
        type=float,
        default=0.0,
        help="Chrome 就绪后、首次搜索前的等待秒数（主系统可传 600）",
    )
    p.add_argument(
        "--human-delay-min",
        type=float,
        default=3.0,
        help="主要步骤间：每一步在 min～max 秒之间独立随机（均匀分布），本参数为下限",
    )
    p.add_argument(
        "--human-delay-max",
        type=float,
        default=7.0,
        help="主要步骤间：每一步在 min～max 秒之间独立随机（均匀分布），本参数为上限",
    )
    p.add_argument(
        "--persona-overlay-json",
        type=str,
        default="",
        help="可选：JSON 文件路径，字段与内存中人设 dict 同键，非空值覆盖 config.yaml 读出的 persona",
    )
    p.add_argument(
        "--fixed-dm",
        type=str,
        default="您好，看到您留言想了解一下，方便说下需求吗？",
        help="--no-doubao 或豆包失败时的私信兜底文案",
    )
    p.add_argument(
        "--fixed-comment",
        type=str,
        default="说得挺清楚的，补充一点同行小经验供参考～",
        help="--no-doubao 或豆包失败时的评论兜底文案",
    )
    p.add_argument("--comment-rounds", type=int, default=5)
    p.add_argument("--comment-scroll-px", type=int, default=1200)
    p.add_argument(
        "--search-scroll-rounds",
        type=int,
        default=60,
        help="列表边滑边选时最多下滑轮数（自上而下依次处理达阈视频）",
    )
    p.add_argument(
        "--search-scroll-px",
        type=int,
        default=850,
        help="每轮列表页 window.scrollBy 的像素（同时尝试滚动搜索结果容器）",
    )
    p.add_argument(
        "--search-no-new-streak",
        type=int,
        default=5,
        help="连续多少轮 collect 都没有出现新的视频 id 则停止下滑（认为到底或无更多加载）",
    )
    p.add_argument(
        "--detail-wait",
        type=float,
        default=38.0,
        help="点击列表后等待悬浮窗/播放区在 DOM 就绪的最长时间（秒），网速慢可调大",
    )
    p.add_argument(
        "--dm-open-wait-min",
        type=float,
        default=5.0,
        help="用户页点「私信」后最短等待秒数（弹层/新页加载）",
    )
    p.add_argument(
        "--dm-open-wait-max",
        type=float,
        default=8.0,
        help="用户页点「私信」后最长等待秒数（与 min 之间随机）",
    )
    p.add_argument(
        "--dm-editor-wait",
        type=float,
        default=20.0,
        help="等待私信输入框出现在 DOM 的最长时间（秒）",
    )
    p.add_argument(
        "--comment-editor-wait",
        type=float,
        default=18.0,
        help="返回视频页后等待评论输入框出现的最大时间（秒）；从用户页切回后评论区可能收起需重开",
    )
    p.add_argument(
        "--dm-click-retries",
        type=int,
        default=4,
        help="用户页点「私信」未弹出输入区时的最多重试次数（每次点完等待再检测）",
    )
    p.add_argument(
        "--dm-retry-gap-min",
        type=float,
        default=2.0,
        help="两次点私信之间等待秒数下限（用于检测弹层是否出现）",
    )
    p.add_argument(
        "--dm-retry-gap-max",
        type=float,
        default=4.5,
        help="两次点私信之间等待秒数上限（与 min 之间随机）",
    )
    return p


def main() -> None:
    _setup_logging()
    args = build_arg_parser().parse_args()
    if USE_TEMP_INPUT_666:
        logger.info(f"[SeleniumIntercept] 联调：私信/评论输入固定为 {TEMP_INPUT_TEXT!r}（USE_TEMP_INPUT_666=True）")
    elif not args.no_doubao:
        logger.info("[SeleniumIntercept] 默认使用豆包生成文案；固定文案请传 --no-doubao")
    if args.ai_intent:
        if args.no_doubao:
            logger.warning(
                "[SeleniumIntercept] 已传 --ai-intent 但同时 --no-doubao，意向仅走关键词/persona.intent_keywords，无豆包二判"
            )
        else:
            logger.info(
                "[SeleniumIntercept] 已传 --ai-intent：命中意向词后将调用豆包二次确认（prompts/意向客户判定_豆包prompt.txt）"
            )
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
