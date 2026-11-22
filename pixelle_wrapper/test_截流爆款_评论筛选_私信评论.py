"""
测试脚本：关键词 -> 找点赞>=阈值的视频(前N) -> 扫评论 -> 判定意向 -> 关注 -> 私信 -> 最后发一条素材评论

说明：
- 这是“测试阶段”的可跑脚本：先把整条链路跑通（含日志/截图落盘/去重/日上限）。
- 私信文案与素材评论可先固定；也支持接豆包（读取 prompts 模板 + 变量替换 + 调用 doubao_client）。

运行（PowerShell）：
& "F:\\shuziren\\dist\\Axon_Program\\runtime_env\\python\\python.exe" "F:\\shuziren\\pixelle_wrapper\\test_截流爆款_评论筛选_私信评论.py" --keyword "不锈钢门窗"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

# 运行时环境的 sys.path 可能不包含脚本目录；手动补齐本地包路径
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from ai_pipeline.browser_manager import browser_manager
from ai_pipeline.doubao_client import doubao_chat_completion


logger = logging.getLogger(__name__)


THIS_DIR = Path(__file__).resolve().parent
ART_DIR = THIS_DIR / "debug_artifacts_intercept"
ART_DIR.mkdir(parents=True, exist_ok=True)

PROMPT_DM = THIS_DIR / "prompts" / "私信回复_豆包prompt.txt"
PROMPT_COMMENT = THIS_DIR / "prompts" / "素材评论一句话_豆包prompt.txt"
PROMPT_INTENT_DECISION = THIS_DIR / "prompts" / "意向客户判定_豆包prompt.txt"

DEDUP_PATH_DEFAULT = THIS_DIR / "data" / "dm_sent.jsonl"
RUNS_BASE_DIR = THIS_DIR / "output" / "intercept_runs"


INTENT_KEYWORDS = [
    "联系方式", "怎么合作", "合作", "代理", "加盟", "在哪", "地址",
    "报价", "多少钱", "价格", "怎么联系", "电话", "微信", "vx", "V信", "加V",
]


def _setup_logging() -> Path:
    log_dir = THIS_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"intercept_test_{time.strftime('%Y%m%d_%H%M%S')}.log"

    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s")

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"[Intercept] 日志文件: {log_path}")
    return log_path


def _rand_sleep(a: float = 0.8, b: float = 2.2) -> float:
    s = random.uniform(a, b)
    return s


async def _human_pause(page, a: float = 0.6, b: float = 1.8) -> None:
    await page.wait_for_timeout(int(_rand_sleep(a, b) * 1000))


async def _dump(page, step: str) -> None:
    base = ART_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{step}"
    try:
        await page.screenshot(path=str(base) + ".png", full_page=True)
        logger.info(f"[Intercept][Debug] 截图: {base}.png")
    except Exception as e:
        logger.warning(f"[Intercept][Debug] 截图失败: {e}")
    try:
        html = await page.content()
        with open(str(base) + ".html", "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"[Intercept][Debug] HTML: {base}.html")
    except Exception as e:
        logger.warning(f"[Intercept][Debug] HTML保存失败: {e}")


def _load_dedup(path: Path) -> Dict[str, dict]:
    sent: Dict[str, dict] = {}
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        return sent
    for line in path.read_text("utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            raw_uid = str(obj.get("user_id") or obj.get("nickname") or "")
            if not raw_uid:
                continue
            uid = _normalize_user_id(raw_uid)
            sent[uid or raw_uid] = obj
        except Exception:
            continue
    return sent


def _append_dedup(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _normalize_user_id(text: str) -> str:
    """
    把用户标识规范化到稳定的 /user/<id> 里的 <id>。
    如果传进来的是 url 或包含 douyin.com/user/，提取 <id>。
    否则返回空字符串让调用方兜底使用原值。
    """
    if not text:
        return ""
    s = str(text)
    m = re.search(r"douyin\\.com/user/([^/?#]+)", s)
    if m:
        return m.group(1)
    m = re.search(r"/user/([^/?#]+)", s)
    if m:
        return m.group(1)
    return ""


def _is_intent_comment(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(k.lower() in t for k in INTENT_KEYWORDS)


def _fill_template(template_text: str, vars_map: Dict[str, str]) -> str:
    out = template_text
    for k, v in vars_map.items():
        out = out.replace("${" + k + "}", v or "")
    return out


async def _doubao_with_timeout(
    messages: List[Dict[str, str]],
    *,
    temperature: float,
    timeout_s: float = 20.0,
) -> Optional[str]:
    """
    doubao_chat_completion 是同步函数，这里用线程执行并加超时，避免脚本在网络抖动时“卡死无输出”。
    超时/异常返回 None，由调用方降级使用固定文案。
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(doubao_chat_completion, messages, temperature=temperature),
            timeout=timeout_s,
        )
    except Exception as e:
        logger.warning(f"[Intercept] 豆包调用超时/失败，降级固定文案: {e}")
        return None


def _parse_like_to_int(s: str) -> int:
    """
    解析点赞文案（可能是 23 / 1.2w / 3万 等），尽量转成 int。
    """
    s = (s or "").strip().lower()
    if not s:
        return 0
    s = s.replace(",", "")
    m = re.match(r"^(\d+(?:\.\d+)?)(w|万)?$", s)
    if not m:
        # 含杂字符，提取数字
        m2 = re.search(r"(\d+(?:\.\d+)?)", s)
        if not m2:
            return 0
        num = float(m2.group(1))
        return int(num)
    num = float(m.group(1))
    unit = m.group(2)
    if unit in ("w", "万"):
        num *= 10000
    return int(num)


async def _open_user_card_from_comment(page, comment_item):
    """
    你提供的逻辑：在评论区直接点“头像”即可进入用户卡片/弹层。
    这里尽量不写死DOM：在 comment_item 内找 img，然后点它（或可点祖先）。
    """
    try:
        async def _is_user_not_found(p) -> bool:
            """某些点击会打开“用户不存在”页，直接视为失败跳过。"""
            try:
                # 给页面一点时间把渲染结果写进 DOM
                await p.wait_for_timeout(500)

                # 1) 先用 locator（如果可见可检索）
                if await p.locator("text=用户不存在").count() > 0:
                    return True
                if await p.locator("text=此用户不存在").count() > 0:
                    return True

                # 2) 兜底：用 content 字符串包含（即使 locator 抓不到也能判定）
                try:
                    html = await p.content()
                    return ("用户不存在" in html) or ("此用户不存在" in html)
                except Exception:
                    return False
            except Exception:
                return False

        # 注意：不要先按 href 直接 goto。评论容器可能很宽，first href 常会命中无效/非当前作者链接。
        # 先执行“真实点击头像/作者区域”，更贴近人工操作。

        # 优先：真正的头像组件（避免点到用户名链接/表情图标）
        avatar = comment_item.locator("[data-e2e='live-avatar']").first
        if await avatar.count() == 0:
            avatar = comment_item.locator(".semi-avatar").first
        # 其次：作者主页链接（部分布局头像被包在 <a href=/user/>）
        if await avatar.count() == 0:
            avatar = comment_item.locator("a[href*='/user/']").first
        if await avatar.count() == 0:
            avatar = comment_item.locator("a[href*='//www.douyin.com/user/']").first
        # 最后：img（可能命中表情/图标，放最后兜底）
        if await avatar.count() == 0:
            avatar = comment_item.locator("img").first
        if await avatar.count() == 0:
            # 兜底：一些头像可能不是 img，而是 div 背景图
            avatar = comment_item.locator("[class*='avatar'], [class*='Avatar']").first
        if await avatar.count() == 0:
            return False

        # 候选点击范围尽量收窄：优先点头像/其外层链接，避免点到大范围祖先导致乱跳/新开一堆页
        candidates = [
            avatar.locator("xpath=ancestor::a[1]"),
            avatar,
        ]
        ctx = page.context
        before_pages = list(ctx.pages)
        before_url = page.url

        for c in candidates:
            try:
                if await c.count() == 0:
                    continue
                t = c.first
                await t.scroll_into_view_if_needed(timeout=2000)
                await t.click(timeout=3000, force=True)
                # 等待可能的新开页/跳转
                await page.wait_for_timeout(800)
                after_pages = list(ctx.pages)
                if len(after_pages) > len(before_pages):
                    # 取最新页
                    new_pages = [p for p in after_pages if p not in before_pages]
                    if not new_pages:
                        newp = after_pages[-1]
                    else:
                        newp = new_pages[-1]
                    try:
                        await newp.wait_for_load_state("domcontentloaded", timeout=15000)
                        await newp.bring_to_front()
                    except Exception:
                        pass

                    # 新开的其他页先关掉，避免“越点越多界面”
                    try:
                        for p in new_pages:
                            if p != newp:
                                await p.close()
                    except Exception:
                        pass

                    if await _is_user_not_found(newp):
                        try:
                            await newp.close()
                        except Exception:
                            pass
                        continue
                    return newp
                if page.url != before_url and ("/user/" in page.url):
                    if await _is_user_not_found(page):
                        continue
                    return page
                # 可能是弹层：如果出现“关注/私信/发消息”等按钮，也认为成功
                try:
                    if await page.get_by_role("button", name=re.compile(r"(关注|私信|发消息|消息)")).first.count():
                        if await _is_user_not_found(page):
                            continue
                        return page
                except Exception:
                    pass
                # 未成功则继续尝试其他候选
            except Exception:
                continue

        # 最后兜底：如果点击都不成功，再尝试用作者链接直接打开
        try:
            a = comment_item.locator("a[href*='/user/']").first
            if await a.count():
                href = await a.get_attribute("href")
            else:
                href = None
            if href:
                url = href
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    url = "https://www.douyin.com" + url
                if "douyin.com/user/" in url:
                    await page.goto(url, wait_until="domcontentloaded", timeout=90000)
                    await page.wait_for_timeout(800)
                    if not await _is_user_not_found(page):
                        return page
        except Exception:
            pass
        return None
    except Exception:
        return None


async def _dm_ui_ready(page) -> bool:
    """判断是否已进入私信聊天UI（能看到消息输入框）"""
    candidates = [
        page.locator("div[contenteditable='true'][data-slate-editor='true']").first,
        page.locator("div[contenteditable='true'][data-placeholder*='发送']").first,
        page.locator("textarea[placeholder*='发送']").first,
        page.locator("div[contenteditable='true'][data-placeholder*='消息']").first,
        page.locator("textarea[placeholder*='消息']").first,
    ]
    for c in candidates:
        try:
            if await c.count():
                await c.wait_for(state="visible", timeout=2500)
                return True
        except Exception:
            continue
    return False


async def _click_follow_and_dm(page):
    """
    你提供的第二步：进入后弹出两个选项：关注、私信。
    - 先点关注（若已关注则跳过）
    - 再点私信
    """
    # 1) 永远先关注（你要求：所有都先关注，再私信）
    # 关注按钮文案可能有：关注 / 回关 / 互相关注 / 已关注 / 已请求
    follow_clicked = False
    try:
        follow_btn = page.get_by_role("button", name=re.compile(r"^(关注|回关|互相关注|已关注|已请求)$")).first
        if await follow_btn.count():
            await follow_btn.click(timeout=5000, force=True)
            follow_clicked = True
            await page.wait_for_timeout(800)
    except Exception:
        # 兜底：按文本找
        try:
            follow_btn = page.get_by_text(re.compile(r"^(关注|回关|互相关注|已关注|已请求)$")).first
            if await follow_btn.count():
                await follow_btn.click(timeout=5000, force=True)
                follow_clicked = True
                await page.wait_for_timeout(800)
        except Exception:
            pass

    # 私密账号/已请求：通常无法私信（你说“发不了就发不了了”，直接跳过）
    try:
        if await page.get_by_text("私密账号").count():
            logger.info("[Intercept] 该账号为私密账号，关注后无法私信，跳过")
            return None
        if await page.get_by_text("已请求").count():
            logger.info("[Intercept] 已发送关注请求（待同意），无法私信，跳过")
            return None
    except Exception:
        pass

    # 私信/发消息 按钮（不同页面叫法可能不同）
    try:
        ctx = page.context
        before_pages = list(ctx.pages)

        dm_btn = page.get_by_role("button", name=re.compile(r"(私信|发消息|消息|聊天)")).first
        await dm_btn.wait_for(state="visible", timeout=8000)
        await dm_btn.click(timeout=5000, force=True)
        await page.wait_for_timeout(800)

        # 处理可能的新开聊天页
        try:
            after_pages = list(ctx.pages)
            if len(after_pages) > len(before_pages):
                page = after_pages[-1]
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    await page.bring_to_front()
                except Exception:
                    pass
        except Exception:
            pass

        # 等待聊天输入框就绪（给足时间）
        for _ in range(4):
            if await _dm_ui_ready(page):
                return page
            await page.wait_for_timeout(2500)
        return page if await _dm_ui_ready(page) else None
    except Exception:
        # 兜底：用文本定位
        try:
            ctx = page.context
            before_pages = list(ctx.pages)

            dm_btn = page.get_by_text(re.compile(r"(私信|发消息|消息|聊天)")).first
            await dm_btn.wait_for(state="visible", timeout=8000)
            await dm_btn.click(timeout=5000, force=True)
            await page.wait_for_timeout(800)

            # 处理可能的新开聊天页
            try:
                after_pages = list(ctx.pages)
                if len(after_pages) > len(before_pages):
                    page = after_pages[-1]
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await page.bring_to_front()
                    except Exception:
                        pass
            except Exception:
                pass

            for _ in range(4):
                if await _dm_ui_ready(page):
                    return page
                await page.wait_for_timeout(2500)
            return page if await _dm_ui_ready(page) else None
        except Exception:
            # 最强兜底：胶囊按钮可能不是 button role，直接 text/xpath 点击
            try:
                ctx = page.context
                before_pages = list(ctx.pages)
                dm_btn2 = page.locator("text=私信").first
                if await dm_btn2.count() == 0:
                    dm_btn2 = page.locator("xpath=//*[normalize-space()='私信']").first
                if await dm_btn2.count() == 0:
                    dm_btn2 = page.locator("text=发消息").first
                await dm_btn2.scroll_into_view_if_needed(timeout=5000)
                await dm_btn2.click(timeout=5000, force=True)
                await page.wait_for_timeout(800)

                try:
                    after_pages = list(ctx.pages)
                    if len(after_pages) > len(before_pages):
                        page = after_pages[-1]
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=15000)
                            await page.bring_to_front()
                        except Exception:
                            pass
                except Exception:
                    pass

                for _ in range(4):
                    if await _dm_ui_ready(page):
                        return page
                    await page.wait_for_timeout(2500)
                return page if await _dm_ui_ready(page) else None
            except Exception:
                if follow_clicked:
                    logger.info("[Intercept] 已关注但未找到可用私信入口（可能受限），跳过")
                return None


async def _send_dm_and_verify(page, msg: str) -> bool:
    """
    私信界面输入并回车，校验回显。
    抖音新版输入框是 slate editor：contenteditable + data-slate-editor。
    """
    try:
        # 输入框形态多样：slate / contenteditable / textarea
        editor = page.locator("div[contenteditable='true'][data-slate-editor='true']").first
        if await editor.count() == 0:
            editor = page.locator("textarea[placeholder*='消息'], textarea[placeholder*='发送']").first
        if await editor.count() == 0:
            editor = page.locator("div[contenteditable='true'][data-placeholder*='消息']").first
        if await editor.count() == 0:
            editor = page.locator("div[contenteditable='true'][data-placeholder*='发送']").first
        if await editor.count() == 0:
            editor = page.locator("div[contenteditable='true']").first
        await editor.wait_for(state="visible", timeout=15000)
        await editor.scroll_into_view_if_needed(timeout=5000)
        await editor.click(timeout=5000, force=True)
        await editor.focus(timeout=5000)
        # textarea 用 fill 更稳
        if (await editor.get_attribute("contenteditable")) == "true":
            await page.keyboard.type(msg, delay=25)
        else:
            try:
                await editor.fill(msg)
            except Exception:
                await page.keyboard.type(msg, delay=25)
        await page.keyboard.press("Enter")
    except Exception as e:
        logger.warning(f"[Intercept] 私信输入/发送失败: {e}")
        await _dump(page, "dm_send_failed")
        return False

    # 校验回显
    try:
        await page.get_by_text(msg).last.wait_for(state="visible", timeout=8000)
        return True
    except Exception:
        await _dump(page, "dm_no_echo")
        return False


async def _find_comment_editor(root: Any):
    """
    定位抖音评论输入框。新版常见 placeholder：「留下你的精彩评论吧」，不一定含「评论」二字。
    root 可为 Page 或 Frame（评论区常在 iframe 内，必须用对应 frame 的 locator）。
    返回 (locator, is_textarea)；找不到则 (None, False)。
    """
    container = root.locator("#comment-input-container")

    async def _visible_pair(loc, is_textarea: bool | None):
        try:
            if await loc.count() == 0:
                return None
            el = loc.first
            await el.wait_for(state="visible", timeout=4000)
            if is_textarea is None:
                tag = await el.evaluate("e => e.tagName.toLowerCase()")
                is_textarea = tag == "textarea"
            return el, bool(is_textarea)
        except Exception:
            return None

    # 1) Playwright placeholder（支持正则）
    for pat in [r"留下", r"精彩", r"评论", r"说点", r"友善", r"留言"]:
        try:
            ctxs = [root]
            if await container.count():
                ctxs.append(container)
            for ctx in ctxs:
                ph = ctx.get_by_placeholder(re.compile(pat))
                if await ph.count():
                    pair = await _visible_pair(ph, None)
                    if pair:
                        return pair
        except Exception:
            continue

    # 2) CSS：placeholder / data-placeholder（含「精彩」「留下」）
    css_list: list[tuple[str, bool | None]] = [
        ("textarea[placeholder*='留下']", True),
        ("textarea[placeholder*='精彩']", True),
        ("textarea[placeholder*='评论']", True),
        ("div[contenteditable='true'][data-placeholder*='留下']", False),
        ("div[contenteditable='true'][data-placeholder*='精彩']", False),
        ("div[contenteditable='true'][data-placeholder*='评论']", False),
        ("div[contenteditable='true'][data-placeholder*='说点']", False),
        ("#comment-input-container textarea", True),
        ("#comment-input-container div[contenteditable='true']", False),
        ("#comment-input-container [role='textbox']", False),
        ("div[contenteditable='true'][data-slate-editor='true']", False),
    ]
    for sel, is_ta in css_list:
        ctxs = [root]
        try:
            if await container.count():
                ctxs.insert(0, container)
        except Exception:
            pass
        for ctx in ctxs:
            try:
                loc = ctx.locator(sel).first
                pair = await _visible_pair(loc, is_ta)
                if pair:
                    return pair
            except Exception:
                continue

    return None, False


async def _find_comment_editor_any_frame(page: Any) -> Tuple[Optional[Any], bool, Optional[Any]]:
    """
    在所有 frame 中查找评论输入框。返回 (editor, is_textarea, frame_or_none)。
    frame 为 playwright Frame 时供调试；主文档命中则为 None（与原先 page.locator 行为一致）。
    """
    for fr in page.frames:
        try:
            ed, is_ta = await _find_comment_editor(fr)
            if ed is not None:
                return ed, is_ta, fr
        except Exception:
            continue
    return None, False, None


# 评论区可能在 iframe 中；主 document 与每个 frame 各执行一次
_JS_COMMENT_DOM_INJECT = """(t) => {
  const fire = (el) => {
    try {
      el.dispatchEvent(new InputEvent('input', {
        bubbles: true, cancelable: true, inputType: 'insertText', data: t
      }));
    } catch (e) {
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const box = document.querySelector('#comment-input-container');
  if (box) {
    const ta = box.querySelector('textarea');
    if (ta) {
      ta.focus();
      ta.value = t;
      fire(ta);
      return true;
    }
    const tb = box.querySelector('[role="textbox"]');
    if (tb) {
      tb.focus();
      if (tb.tagName === 'TEXTAREA') {
        tb.value = t;
      } else {
        tb.textContent = t;
        tb.innerText = t;
      }
      fire(tb);
      return true;
    }
    const eds = box.querySelectorAll('[contenteditable="true"]');
    for (const el of eds) {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      el.focus();
      el.textContent = t;
      el.innerText = t;
      fire(el);
      return true;
    }
  }
  const pick = (el) => {
    el.focus();
    if (el.tagName === 'TEXTAREA') {
      el.value = t;
    } else {
      el.textContent = t;
      el.innerText = t;
    }
    fire(el);
    return true;
  };
  for (const sel of [
    'textarea[placeholder*="留下"]',
    'textarea[placeholder*="精彩"]',
    'textarea[placeholder*="评论"]',
    'div[contenteditable="true"][data-placeholder*="留下"]',
    'div[contenteditable="true"][data-placeholder*="精彩"]',
    'div[contenteditable="true"][data-placeholder*="评论"]',
  ]) {
    const el = document.querySelector(sel);
    if (el && el.offsetParent !== null) {
      return pick(el);
    }
  }
  // 兜底：容器内任意可见 textarea / textbox / contenteditable
  const box2 = document.querySelector('#comment-input-container');
  if (box2) {
    const cand = box2.querySelectorAll('textarea, [role="textbox"], [contenteditable="true"]');
    for (const el of cand) {
      const r = el.getBoundingClientRect();
      if (r.width > 8 && r.height > 8) {
        return pick(el);
      }
    }
  }
  return false;
}"""

async def _wait_until_comment_editable(page: Any, timeout_ms: int = 10000) -> bool:
    """
    等待评论输入可用：以「能定位到输入框」为准（含 iframe、占位「留下你的精彩评论吧」），
    并兼容 #comment-input-container 已挂载的情况。
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if await _is_comment_input_visible(page):
            return True
        for fr in page.frames:
            try:
                if await fr.evaluate(
                    "() => !!document.querySelector('#comment-input-container')"
                ):
                    return True
            except Exception:
                continue
        await page.wait_for_timeout(400)
    return False


async def _inject_comment_text_dom(page, text: str) -> bool:
    """
    不依赖键盘/剪贴板：在页面内直接写入评论框并触发 input（抖音评论多为 React/Slate）。
    依次尝试每个 frame（评论区可能在 iframe）。不依赖「读回校验」——只要注入返回 true 即视为已尝试写入。
    """
    if not (text or "").strip():
        return False
    last_err: Optional[Exception] = None
    for fr in page.frames:
        try:
            ok = await fr.evaluate(_JS_COMMENT_DOM_INJECT, text)
            if ok:
                logger.info(
                    "[Intercept][MANUAL] 已在某 frame 内执行 DOM 写入评论（请在界面确认文案是否已出现）"
                )
                return True
        except Exception as e:
            last_err = e
            continue
    if last_err:
        logger.debug(f"[Intercept] 多 frame DOM 注入末次异常: {last_err}")
    return False


async def _type_into_comment_editor(page, editor, is_textarea: bool, text: str) -> None:
    """写入评论：优先 insert_text（Slate 常用）；再 DOM 注入；再 fill / Ctrl+V。"""
    await editor.scroll_into_view_if_needed(timeout=5000)
    await editor.click(timeout=4000, force=True)
    await editor.focus(timeout=4000)
    try:
        await page.keyboard.press("Control+A")
    except Exception:
        pass
    try:
        await page.keyboard.press("Backspace")
    except Exception:
        pass
    # 1) insert_text：多数 React/Slate 评论框吃这套
    try:
        await page.keyboard.insert_text(text)
        logger.info("[Intercept][MANUAL] 已用 insert_text 写入评论框（请确认后手动点发送）")
        return
    except Exception as e:
        logger.warning(f"[Intercept] insert_text 失败，尝试 DOM 注入: {e}")
    # 2) 对节点 DOM 注入
    try:
        await editor.evaluate(
            """(el, t) => {
              el.focus();
              if (el.tagName === 'TEXTAREA') {
                el.value = t;
              } else {
                el.textContent = t;
                el.innerText = t;
              }
              try {
                el.dispatchEvent(new InputEvent('input', {
                  bubbles: true, cancelable: true, inputType: 'insertText', data: t
                }));
              } catch (e) {
                el.dispatchEvent(new Event('input', { bubbles: true }));
              }
              el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            text,
        )
        logger.info("[Intercept][MANUAL] 已对定位到的评论节点执行 DOM 写入（请确认后手动点发送）")
        return
    except Exception as e:
        logger.warning(f"[Intercept] 节点 DOM 写入失败，尝试 fill/粘贴: {e}")

    if is_textarea:
        await editor.fill(text)
        logger.info("[Intercept][MANUAL] 已 fill 评论 textarea（请确认后手动点发送）")
        return
    try:
        await page.keyboard.down("Control")
        await page.keyboard.press("V")
        await page.keyboard.up("Control")
        logger.info("[Intercept][MANUAL] 已尝试 Ctrl+V 粘贴（请确认后手动点发送）")
        return
    except Exception:
        pass
    try:
        await page.keyboard.type(text, delay=22)
        logger.info("[Intercept][MANUAL] 已用逐字 typing 写入（请确认后手动点发送）")
    except Exception:
        raise


async def _force_type_comment_by_placeholder(page, text: str, timeout_ms: int = 15000) -> bool:
    """
    当无法稳定拿到“真实输入节点”时，直接点占位文案并键盘输入。
    目标是把文本显示到评论框里（手动发送场景）。
    """
    if not (text or "").strip():
        return False
    _copy_to_clipboard(text)
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        for fr in page.frames:
            # 先走一轮深度 DOM（含 shadowRoot）直写
            try:
                deep_ok = await fr.evaluate(
                    """(t) => {
                      const fire = (n) => {
                        try {
                          n.dispatchEvent(new InputEvent('input', {
                            bubbles: true, cancelable: true, inputType: 'insertText', data: t
                          }));
                        } catch (e) {
                          n.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        n.dispatchEvent(new Event('change', { bubbles: true }));
                      };
                      const editableSel = 'textarea, input, [contenteditable="true"], [role="textbox"]';
                      const seen = new Set();
                      const queue = [document];
                      while (queue.length) {
                        const root = queue.shift();
                        if (!root || seen.has(root)) continue;
                        seen.add(root);
                        const nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
                        for (const n of nodes) {
                          if (n.shadowRoot) queue.push(n.shadowRoot);
                        }
                        const cands = root.querySelectorAll ? root.querySelectorAll(editableSel) : [];
                        for (const n of cands) {
                          const r = n.getBoundingClientRect?.();
                          if (!r || r.width < 2 || r.height < 2) continue;
                          const ph = (n.getAttribute?.('placeholder') || n.getAttribute?.('data-placeholder') || '').toString();
                          const nearComment = /留|精|评|说点|评论/.test(ph) || !!n.closest?.('#comment-input-container');
                          if (!nearComment) continue;
                          n.focus?.();
                          const tag = (n.tagName || '').toUpperCase();
                          if (tag === 'TEXTAREA' || tag === 'INPUT') n.value = t;
                          else { n.textContent = t; n.innerText = t; }
                          fire(n);
                          return true;
                        }
                      }
                      return false;
                    }""",
                    text,
                )
                if deep_ok:
                    logger.info("[Intercept][MANUAL] 已通过深度 DOM（含 shadowRoot）写入评论")
                    return True
            except Exception:
                pass
            clicked = False
            try:
                for loc in [
                    fr.get_by_placeholder(re.compile(r"留下你的精彩评论吧|精彩评论|评论")),
                    fr.get_by_text("留下你的精彩评论吧"),
                    fr.locator("textarea[placeholder*='留下'], textarea[placeholder*='精彩'], textarea[placeholder*='评论']"),
                    fr.locator("div[contenteditable='true'][data-placeholder*='留下'], div[contenteditable='true'][data-placeholder*='精彩'], div[contenteditable='true'][data-placeholder*='评论']"),
                ]:
                    if await loc.count():
                        tar = loc.first
                        await tar.scroll_into_view_if_needed(timeout=1200)
                        await tar.click(timeout=1500, force=True)
                        clicked = True
                        break
            except Exception:
                pass
            if not clicked:
                continue
            # 先对“点击命中节点”就地做 DOM 写入（并向上寻找最近可编辑节点）
            try:
                wrote = await tar.evaluate(
                    """(el, t) => {
                      const fire = (n) => {
                        try {
                          n.dispatchEvent(new InputEvent('input', {
                            bubbles: true, cancelable: true, inputType: 'insertText', data: t
                          }));
                        } catch (e) {
                          n.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        n.dispatchEvent(new Event('change', { bubbles: true }));
                      };
                      const pickEditable = (n) => {
                        if (!n) return null;
                        if (n.matches && n.matches('textarea, input, [contenteditable="true"], [role="textbox"]')) return n;
                        return n.querySelector?.('textarea, input, [contenteditable="true"], [role="textbox"]')
                          || n.closest?.('textarea, input, [contenteditable="true"], [role="textbox"]')
                          || null;
                      };
                      const node = pickEditable(el) || pickEditable(el.parentElement) || pickEditable(document.querySelector('#comment-input-container'));
                      if (!node) return false;
                      node.focus?.();
                      const tag = (node.tagName || '').toUpperCase();
                      if (tag === 'TEXTAREA' || tag === 'INPUT') {
                        node.value = t;
                      } else {
                        node.textContent = t;
                        node.innerText = t;
                      }
                      fire(node);
                      return true;
                    }""",
                    text,
                )
                if wrote:
                    logger.info("[Intercept][MANUAL] 已通过占位命中节点 DOM 写入评论")
                    return True
            except Exception:
                pass
            try:
                await page.keyboard.press("Control+A")
            except Exception:
                pass
            try:
                await page.keyboard.press("Backspace")
            except Exception:
                pass
            try:
                await page.keyboard.insert_text(text)
                logger.info("[Intercept][MANUAL] 已通过占位文案点击 + insert_text 尝试写入评论")
                return True
            except Exception:
                pass
            try:
                await page.keyboard.down("Control")
                await page.keyboard.press("V")
                await page.keyboard.up("Control")
                logger.info("[Intercept][MANUAL] 已通过占位文案点击 + Ctrl+V 尝试写入评论")
                return True
            except Exception:
                pass
        await page.wait_for_timeout(350)
    return False


async def _is_comment_input_visible(page) -> bool:
    """
    判断评论输入框是否可见（避免“DOM 里存在但评论区未展开”的误判）。
    含 iframe：逐 frame 查找。
    """
    ed, _, _ = await _find_comment_editor_any_frame(page)
    return ed is not None


async def _force_open_comment_sidebar(page) -> bool:
    """
    沉浸式右侧竖栏：强制点击评论气泡（通常第 2 个带 svg 的按钮），直到评论输入框可见。
    """
    logger.info("[Intercept] 强制点击右侧评论气泡，尝试展开评论区…")
    try:
        sidebar = page.locator("#videoSideBar").first
        if await sidebar.count():
            await page.wait_for_timeout(500)
            items = sidebar.locator("xpath=.//*[self::button or self::div or self::span][.//*[name()='svg']]")
            n = await items.count()
            order = []
            if n >= 2:
                order.append(1)
            order.extend([i for i in range(min(n, 6)) if i != 1])
            for i in order:
                try:
                    it = items.nth(i)
                    await it.scroll_into_view_if_needed(timeout=2000)
                    await it.click(timeout=3000, force=True)
                    await page.wait_for_timeout(1200)
                    if await _is_comment_input_visible(page):
                        logger.info("[Intercept] ✅ 评论区展开：评论输入框已可见")
                        return True
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"[Intercept] 强制点击评论侧栏失败: {e}")

    try:
        vp = page.viewport_size or {}
        w, h = int(vp.get("width") or 1280), int(vp.get("height") or 720)
        x = max(10, w - 55)
        for y in [int(h * 0.48), int(h * 0.55), int(h * 0.62)]:
            try:
                await page.mouse.click(x, y)
                await page.wait_for_timeout(1200)
                if await _is_comment_input_visible(page):
                    logger.info("[Intercept] ✅ 坐标点击后评论区展开：评论输入框已可见")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


async def _open_comment_panel(page) -> bool:
    """
    打开视频详情页评论区（多策略）。
    成功条件：出现评论输入框（placeholder含“评论”）或出现“回复”列表项。
    """
    # 先滚动到底部附近（评论入口常在底部）
    try:
        await page.mouse.wheel(0, 1600)
        await page.wait_for_timeout(800)
    except Exception:
        pass

    # 多策略点击入口
    click_targets = [
        # 右侧 Tab 常见是“评论(37)”这种形式
        page.get_by_text(re.compile(r"^评论\(\d+\)$")).first,
        page.get_by_text(re.compile(r"^评论\d+$")).first,
        page.get_by_text("评论").first,
        page.get_by_text("全部评论").first,
        # 沉浸式/竖栏：通常是可访问的 button/aria-label
        page.get_by_role("button", name=re.compile(r"评论")).first,
        page.get_by_label(re.compile(r"评论")).first,
        # 兜底：data-e2e 里包含 comment
        page.locator("[data-e2e*='comment'], [data-e2e*='Comment']").first,
    ]
    for t in click_targets:
        try:
            if await t.count():
                await t.scroll_into_view_if_needed(timeout=5000)
                await t.click(timeout=6000, force=True)
                await page.wait_for_timeout(600)
        except Exception:
            pass

    # 兜底：沉浸式右侧竖栏（videoSideBar）是运行时动态渲染，可能没有可检索文本/label。
    # 策略：在 #videoSideBar 内找“带 svg 的可点击项”，按顺序尝试点击，直到评论容器出现。
    try:
        sidebar = page.locator("#videoSideBar").first
        if await sidebar.count():
            # 给 sidebar 一点时间渲染
            await page.wait_for_timeout(600)
            items = sidebar.locator("xpath=.//*[self::button or self::div or self::span][.//*[name()='svg']]")
            n = await items.count()
            # 优先尝试第2个（通常是评论），再从头扫一遍
            order = []
            if n >= 2:
                order.append(1)
            order.extend([i for i in range(min(n, 5)) if i != 1])
            for i in order:
                try:
                    it = items.nth(i)
                    await it.scroll_into_view_if_needed(timeout=2000)
                    await it.click(timeout=2000, force=True)
                    await page.wait_for_timeout(500)
                    if await _is_comment_input_visible(page):
                        return True
                    try:
                        if await page.locator(".comment-title:has-text('全部评论')").first.is_visible():
                            return True
                    except Exception:
                        pass
                except Exception:
                    continue
    except Exception:
        pass

    # 最后兜底：沉浸式右侧竖栏按钮有时无法被稳定定位，直接按坐标点右侧区域（不影响“点击进素材”要求）
    try:
        vp = page.viewport_size
        if vp and vp.get("width") and vp.get("height"):
            w, h = vp["width"], vp["height"]
            x = max(10, w - 60)
            # 评论气泡通常在右侧竖栏中部，尝试几个 y
            for y in [int(h * 0.45), int(h * 0.52), int(h * 0.60)]:
                try:
                    await page.mouse.click(x, y)
                    await page.wait_for_timeout(500)
                    if await _is_comment_input_visible(page):
                        return True
                    try:
                        if await page.locator(".comment-title:has-text('全部评论')").first.is_visible():
                            return True
                    except Exception:
                        pass
                except Exception:
                    continue
    except Exception:
        pass

    # 等待输入框出现（含「留下你的精彩评论吧」等）
    input_targets = [
        page.locator("textarea[placeholder*='精彩']").first,
        page.locator("div[contenteditable='true'][data-placeholder*='精彩']").first,
        page.locator("textarea[placeholder*='评论']").first,
        page.locator("div[contenteditable='true'][data-placeholder*='评论']").first,
        page.locator("div[contenteditable='true'][data-placeholder*='评']").first,
        page.locator(".comment-title:has-text('全部评论')").first,
    ]
    for it in input_targets:
        try:
            if await it.count():
                await it.wait_for(state="visible", timeout=4000)
                return True
        except Exception:
            pass

    # 必须可见：避免 #comment-input-container 已挂载但评论区未展开
    if await _is_comment_input_visible(page):
        return True

    # 不再用全页“回复”文本做成功条件（容易误匹配页脚/其它区域）
    return False

async def _extract_visible_comment_items(page):
    """
    提取可见评论条目（尽量贴近你截图：每条都有“回复/分享”等操作区）。
    返回 locator 列表（最多取前若干，避免过慢）。
    """
    # 优先尝试更明确的 comment 结构（不同版本可能不同）
    selector_candidates = [
        "[data-e2e*='comment']",
        "div[class*='comment'][class*='item']",
        "div[class*='Comment'][class*='Item']",
    ]
    for sel in selector_candidates:
        try:
            items = page.locator(sel)
            n = await items.count()
            if n > 0:
                return items, min(n, 60)
        except Exception:
            pass

    # 通用做法：以“回复”文字为锚点，向上找包含头像的祖先作为“单条评论”
    # 注意：这个 selector 仍可能偏宽，但比全页容器要窄很多
    items = page.get_by_text("回复").locator("xpath=ancestor::div[.//img][1]")
    n = await items.count()
    if n == 0:
        items = page.locator("div:has-text('回复'):has(img)")
        n = await items.count()
    return items, min(n, 60)

async def _scroll_comment_panel(page, px: int = 1200) -> None:
    """
    在评论面板打开时，向下滚动以加载更多评论。
    不依赖具体容器，优先用鼠标滚轮做“通用兜底”。
    """
    try:
        await page.mouse.wheel(0, int(px))
    except Exception:
        pass
    await page.wait_for_timeout(900)


async def _has_dm_entry(page) -> bool:
    """
    不点击，只判断“私信/发消息/聊天”入口是否在页面上可见。
    用于“候选收集/不发私信”模式。
    """
    try:
        dm_btn = page.get_by_role("button", name=re.compile(r"(私信|发消息|消息|聊天)")).first
        if await dm_btn.count():
            return True
    except Exception:
        pass
    try:
        dm_btn2 = page.get_by_text(re.compile(r"^(私信|发消息|消息|聊天)$")).first
        if await dm_btn2.count():
            return True
    except Exception:
        pass
    return False


async def _type_dm_text_without_sending(page, msg: str) -> bool:
    """
    只把文本输入到私信输入框，不按 Enter、不点击发送。
    """
    try:
        candidates = [
            page.locator("div[contenteditable='true'][data-slate-editor='true']").first,
            page.locator("div[contenteditable='true'][data-placeholder*='发送']").first,
            page.locator("div[contenteditable='true'][data-placeholder*='消息']").first,
            page.locator("textarea[placeholder*='消息'], textarea[placeholder*='发送']").first,
        ]
        editor = None
        for c in candidates:
            try:
                if await c.count():
                    editor = c
                    break
            except Exception:
                continue
        if editor is None:
            return False
        await editor.wait_for(state="visible", timeout=15000)
        await editor.scroll_into_view_if_needed(timeout=5000)
        await editor.click(timeout=5000, force=True)
        await editor.focus(timeout=5000)
        # slate editor 用键盘输入更稳，不发送
        await page.keyboard.type(msg, delay=25)
        return True
    except Exception:
        return False


def _copy_to_clipboard(text: str) -> None:
    """
    把文本复制到系统剪贴板（给你手机/电脑人工粘贴兜底）。
    """
    try:
        import subprocess
        # JSON 编码确保引号安全
        import json as _json
        v = _json.dumps(text, ensure_ascii=False)
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value {v}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        pass


async def _count_text_occurrences(page, text: str) -> int:
    """
    统计页面上与 text 完全匹配的节点数量（用于“发送后回显数量增加”的判断）。
    """
    try:
        if not text:
            return 0
        return await page.get_by_text(text).count()
    except Exception:
        return 0


async def _wait_for_dm_echo(page, msg: str, baseline_count: int, timeout_s: int = 120) -> bool:
    """
    等待“已发送后的回显”出现。用户手动点发送后，聊天窗口通常会渲染消息文本。
    """
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            now_count = await page.get_by_text(msg).count()
            # 只有当“回显节点数量”比我们打字后的基线更多，才认为你已经点了发送
            if now_count > (baseline_count or 0):
                return True
        except Exception:
            pass
        await page.wait_for_timeout(1000)
    return False


async def _wait_for_comment_echo(
    page,
    comment_text: str,
    timeout_s: int = 90,
    baseline_count: int = 0,
) -> bool:
    """
    等待评论回显：用户手动点击发布后，评论列表里“出现次数增加”。
    baseline_count 用于避免输入框里已存在同样文本导致的误判。
    """
    end = time.time() + max(0, timeout_s)
    warned = False
    comment_text = (comment_text or "").strip()
    if not comment_text:
        return False

    # 重要：manual 发布场景希望“直到你点发布才继续”，因此超时后不返回 False，
    # 而是继续等待直到回显次数增加（或页面异常导致抛错由外层处理）。
    while True:
        try:
            now_count = await page.get_by_text(comment_text).count()
            if now_count > (baseline_count or 0):
                return True
        except Exception:
            pass
        if not warned and time.time() > end:
            warned = True
            logger.warning(f"[Intercept][MANUAL] 评论回显仍未检测到（已超过 {timeout_s}s），继续等待你手动发布...")
        await page.wait_for_timeout(1000)


async def _ai_intent_decide(comment_text: str, keyword: str) -> str:
    """
    豆包二分类：只返回“是”或“不是”（不输出解释）。
    """
    prompt = PROMPT_INTENT_DECISION.read_text("utf-8", errors="ignore")
    filled = _fill_template(prompt, {"commentText": comment_text or "", "keyword": keyword or ""})
    out = await _doubao_with_timeout(
        [
            {"role": "system", "content": "你必须只输出一个字：是 或 不是。"},
            {"role": "user", "content": filled},
        ],
        temperature=0.0,
        timeout_s=20.0,
    )
    s = (out or "").strip()
    # 兜底解析：只要包含“是”就当是，否则当不是
    if "是" in s and "不是" not in s:
        return "是"
    if s == "是":
        return "是"
    if s == "不是":
        return "不是"
    return "不是"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", type=str, default="不锈钢门窗")
    parser.add_argument("--top-videos", type=int, default=5)
    parser.add_argument("--min-likes", type=int, default=20)
    parser.add_argument("--dm-daily-limit", type=int, default=10)
    parser.add_argument("--dm-per-video", type=int, default=1)
    parser.add_argument("--video-wait-seconds", type=int, default=20)
    parser.add_argument("--dedup-path", type=str, default=str(DEDUP_PATH_DEFAULT))
    parser.add_argument("--enable-dm", action="store_true", default=False,
                        help="是否真的执行私信发送（默认不发，只做候选收集）")
    parser.add_argument("--enable-comment", action="store_true", default=False,
                        help="是否真的在素材下发表评论（默认不发，只做候选收集）")
    parser.add_argument("--enable-ai-decision", action="store_true", default=False,
                        help="对意向评论做AI二分类（是/不是），仅用于候选筛选与记录")
    parser.add_argument("--open-approved-and-wait-sent", action="store_true", default=False,
                        help="AI判定为“是”后：仅打开聊天输入框并准备文案，等待你手动点击发送（不自动发送）")
    parser.add_argument("--manual-dm-text", type=str, default="你好呀！！",
                        help="等待你手动点击发送时，输入框预填的私信文本")
    parser.add_argument("--manual-wait-sent-timeout", type=int, default=120,
                        help="等待你手动发送成功的超时时间（秒）")
    parser.add_argument("--manual-comment-wait", action="store_true", default=False,
                        help="当需要发表评论时：只填入评论内容，不自动按 Enter/发布；等待你手动点击发布")
    parser.add_argument("--manual-comment-wait-timeout", type=int, default=90,
                        help="等待你手动发布评论成功的超时时间（秒）")
    parser.add_argument("--comment-only", action="store_true", default=False,
                        help="仅跑评论：不进行私信/意向客户扫描；打开评论区后直接填一句评论并等待你手动发布")
    parser.add_argument("--use-doubao", action="store_true", default=False)
    parser.add_argument("--fixed-dm", type=str, default="你好，对的")
    parser.add_argument("--fixed-comment", type=str, default="真精彩！")
    parser.add_argument("--prefer-click", action="store_true", default=True)
    parser.add_argument("--comment-rounds", type=int, default=4, help="每个视频评论区滚动加载轮数")
    parser.add_argument("--comment-scroll-px", type=int, default=1400, help="每轮滚动像素")
    args = parser.parse_args()

    # 安全约束：
    # - 禁止自动私信发送（enable_dm 永远只用于内部路径）
    # - 评论也禁止自动发布；仅允许 manual-comment-wait 这种“停在发布按钮前”的人工确认模式
    if args.enable_dm:
        logger.error("[Intercept] 已禁用自动私信发送：脚本仅支持候选筛选与人工发送。")
        return 2
    if args.enable_comment and not args.manual_comment_wait:
        logger.error("[Intercept] 已禁用自动发布评论：请使用 --manual-comment-wait 进入手动发布模式。")
        return 2

    # 启动标记文件：用于排查“脚本是否真正启动”（即便控制台输出被吞）
    try:
        mark = ART_DIR / f"STARTED_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        mark.write_text("started\n", "utf-8")
    except Exception:
        pass

    _setup_logging()

    dedup_path = Path(args.dedup_path)
    sent_map = _load_dedup(dedup_path)
    logger.info(f"[Intercept] 已私信去重记录数: {len(sent_map)}  path={dedup_path}")

    # 本次运行产物目录：用于把“发给谁”打印并落盘，方便你对照与排查
    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_BASE_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sent_users_path = run_dir / "sent_users.txt"
    dm_recs_path = run_dir / "dm_sent_records.jsonl"
    sent_users_path.write_text("", encoding="utf-8")
    dm_recs_path.write_text("", encoding="utf-8")
    candidates_path = run_dir / "dm_candidates_records.jsonl"
    candidates_path.write_text("", encoding="utf-8")
    approved_path = run_dir / "approved_dm_candidates.jsonl"
    approved_path.write_text("", encoding="utf-8")
    approved_count = 0
    logger.info(f"[Intercept] 本次运行目录: {run_dir}")

    page = await browser_manager.open_login_page("https://www.douyin.com/")
    await page.bring_to_front()
    await page.wait_for_timeout(2000)

    # 1) 搜索关键词（尽量不写死：用搜索框 placeholder/role 兜底）
    logger.info(f"[Intercept] 开始搜索关键词: {args.keyword!r}")
    # 强制进入搜索结果页（避免输入框定位不准导致跳到推荐流/其它页面）
    kw = (args.keyword or "").strip()
    if not kw:
        logger.warning("[Intercept] keyword 为空，退出")
        return 2
    search_url = f"https://www.douyin.com/search/{quote(kw)}"
    logger.info(f"[Intercept] goto 搜索页: {search_url}")
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(1200)
        await page.wait_for_url(re.compile(r".*/search/.*"), timeout=20000)
    except Exception as e:
        logger.warning(f"[Intercept] 进入搜索页失败: {e}  current_url={page.url!r}")
        await _dump(page, "search_goto_failed")
        return 2

    logger.info(f"[Intercept] 已进入搜索页 url={page.url!r}")
    await page.wait_for_timeout(1500)

    # 2) 找视频卡片
    # 抖音搜索/精选页的视频卡片不一定是 <a>，经常是带 href 属性的 div（见落盘HTML）
    # 测试阶段用“尽可能通用的选择器 + 尝试点击”方式。
    video_clicked = 0
    dm_sent = 0
    dm_candidates = 0

    # 候选卡片：
    # - 搜索页很多结果是 waterfall 布局：id="waterfall_item_<aweme_id>"，卡片本身未必有 href
    # - 精选/推荐页常见是带 href 或 data-aweme-id
    cards = page.locator("[id^='waterfall_item_']")
    if await cards.count() == 0:
        cards = page.locator("[data-aweme-id]")
    if await cards.count() == 0:
        cards = page.locator("[href*='/video/']")
    try:
        # 等首屏卡片渲染出来（避免刚进页面 count=0）
        await cards.first.wait_for(state="attached", timeout=15000)
    except Exception:
        pass
    total_cards = await cards.count()
    logger.info(f"[Intercept] 搜索结果候选视频链接数: {total_cards}")
    if total_cards == 0:
        await _dump(page, "no_video_cards")
        return 3

    idx = 0
    while idx < total_cards and video_clicked < args.top_videos:
        # 控制日私信上限
        if dm_sent >= args.dm_daily_limit:
            logger.info("[Intercept] 达到日私信上限，停止")
            break

        link = cards.nth(idx)
        logger.info(f"[Intercept] 处理卡片 idx={idx} / total={total_cards}")
        idx += 1

        href = None
        aweme_id = None
        card_id = None
        try:
            card_id = await link.get_attribute("id")
        except Exception:
            card_id = None

        # 0) 搜索页瀑布流：优先从 id 提取 aweme_id（最快、最稳）
        if card_id:
            m_id = re.search(r"waterfall_item_(\d{10,})", card_id)
            if m_id:
                aweme_id = m_id.group(1)

        # 1) 其他场景再尝试 href
        try:
            href = await link.get_attribute("href")
        except Exception:
            href = None

        if not href:
            pass

        if not href and not aweme_id:
            # 2) 子节点里可能有 <a href="//www.douyin.com/video/...">
            try:
                href = await link.locator("a[href*='/video/'], [href*='/video/']").first.get_attribute("href")
            except Exception:
                href = None

        if not href and aweme_id:
            href = f"https://www.douyin.com/video/{aweme_id}"

        if not href:
            continue

        # 搜索页瀑布流卡片：优先“点击进入”（和人一致，返回也更自然）；点击失败再 goto 兜底
        from_waterfall = bool(aweme_id) and bool(card_id) and ("waterfall_item_" in card_id)
        if from_waterfall:
            logger.info(f"[Intercept] 搜索卡片 aweme_id={aweme_id}，优先点击进入（失败再goto） url={href}")
            try:
                if args.prefer_click:
                    # 卡片本身通常不是 <a>，但内部有可点击区域：search-result-card/videoImage 等
                    click_target = link.locator(".search-result-card").first
                    if await click_target.count() == 0:
                        click_target = link.locator("[class*='videoImage'], [class*='VideoImage']").first
                    if await click_target.count() == 0:
                        click_target = link
                    await click_target.scroll_into_view_if_needed(timeout=8000)
                    await click_target.click(timeout=8000, force=True)
                    try:
                        await page.wait_for_url(re.compile(r".*/video/\\d+.*"), timeout=15000)
                    except Exception:
                        # 有时是弹层/同页播放器，不一定改 URL；继续往下走
                        pass
                else:
                    raise RuntimeError("prefer-click disabled")
            except Exception as e_click:
                logger.warning(f"[Intercept] 点击进入视频失败，改用goto兜底: {e_click}")
                try:
                    url = href
                    if url.startswith("//"):
                        url = "https:" + url
                    elif url.startswith("/"):
                        url = "https://www.douyin.com" + url
                    await page.goto(url, wait_until="domcontentloaded", timeout=90000)
                except Exception as e_goto:
                    logger.warning(f"[Intercept] goto 视频失败: {e_goto}")
                    await _dump(page, "goto_video_failed")
                    continue

            try:
                # 给播放器/右侧面板足够渲染时间（你要求 >20s）
                await page.wait_for_timeout(int(args.video_wait_seconds * 1000))
                video_clicked += 1
            except Exception as e:
                logger.warning(f"[Intercept] 进入视频后等待失败: {e}")

            # Debug：落盘一次视频详情页（便于后续精修评论/按钮定位）
            try:
                await _dump(page, f"video_detail_{video_clicked}")
            except Exception:
                pass

            # 3) 打开评论区（多策略），并记住是否确认打开
            opened = await _open_comment_panel(page)
            # 可能“opened=True 但输入框未可见”（旧逻辑误判），再强制点右侧评论气泡
            if not await _is_comment_input_visible(page):
                forced = await _force_open_comment_sidebar(page)
                opened = opened or forced
            logger.info(f"[Intercept] 评论区打开结果 opened={opened} input_visible={await _is_comment_input_visible(page)}")
            if not opened:
                await _dump(page, f"comment_panel_not_opened_{video_clicked}")
            await page.wait_for_timeout(1200)

            # comment-only：跳过意向扫描/私信，只在评论区里填一句评论并等待你手动发布
            if args.comment_only:
                # 尽量把评论区切到“全部评论”，确保输入框 DOM 已就绪
                try:
                    all_btn = page.get_by_text("全部评论").first
                    if await all_btn.count():
                        await all_btn.scroll_into_view_if_needed(timeout=5000)
                        await all_btn.click(timeout=6000, force=True)
                        await page.wait_for_timeout(1500)
                except Exception:
                    pass
                try:
                    await _scroll_comment_panel(page, px=int(getattr(args, "comment_scroll_px", 1400)))
                except Exception:
                    pass

                if not args.enable_comment:
                    logger.error("[Intercept][COMMENT_ONLY] comment-only 模式必须配合 --enable-comment --manual-comment-wait")
                    return 2

                # comment-only 不手动填输入框；让后续“素材评论”手动发布那段逻辑复用同一套定位/回显判断
                logger.info("[Intercept][COMMENT_ONLY] 已打开评论区，进入素材评论手动发布流程（跳过私信扫描）")

            # 4) 扫可见评论条目...
            intent_hits = 0
            video_dm_sent = 0
            seen_comment_snippets: set[str] = set()

            for r in range(max(1, int(args.comment_rounds))):
                # comment-only：不做意向扫描/私信，只尽量让评论面板完成一次渲染后直接进入“素材评论”手动发布流程
                if args.comment_only:
                    video_dm_sent = 1
                    try:
                        await _extract_visible_comment_items(page)
                        await _scroll_comment_panel(page, px=args.comment_scroll_px)
                    except Exception:
                        pass
                    break
                if dm_sent >= args.dm_daily_limit:
                    logger.info("[Intercept] 达到日私信上限，停止在该视频的评论处理")
                    break
                if video_dm_sent >= args.dm_per_video:
                    break

                items, take_n = await _extract_visible_comment_items(page)
                if take_n == 0:
                    logger.info(f"[Intercept] 第{r+1}轮：未找到可见评论条目")
                else:
                    logger.info(f"[Intercept] 第{r+1}轮：可见评论条目数(取样): {take_n}")
                    opened = True

                for ci in range(take_n):
                    if dm_sent >= args.dm_daily_limit:
                        break
                    if video_dm_sent >= args.dm_per_video:
                        break

                    item = items.nth(ci)
                    try:
                        txt = (await item.inner_text(timeout=800)) or ""
                    except Exception:
                        continue

                    if "下载抖音精选" in txt or "京ICP备" in txt or "2026 ©" in txt:
                        continue
                    if len(txt) > 500:
                        continue
                    if not _is_intent_comment(txt):
                        continue

                    # 去重同一轮/多轮里重复出现的评论容器
                    sig = (txt.strip()[:120] or "").replace("\n", " ")
                    if sig in seen_comment_snippets:
                        continue
                    seen_comment_snippets.add(sig)

                    intent_hits += 1
                    logger.info(f"[Intercept] 命中意向评论(片段): {txt[:60]!r}")
                    intent_comment_text = (txt or "").strip()[:400]

                    if args.use_doubao:
                        persona_vars = {
                            "userMessage": txt[:200],
                            "chatHistory": "",
                            "nickname": "",
                            "priceRange": "",
                            "wechatId": "",
                            "companyName": "",
                            "serviceRegion": "",
                            "targetAudience": "",
                            "companyAddress": "",
                            "businessYear": "",
                            "keyFeatures": "",
                            "relatedNotes": "",
                        }
                        dm_prompt = PROMPT_DM.read_text("utf-8", errors="ignore")
                        prompt_filled = _fill_template(dm_prompt, persona_vars)
                        logger.info("[Intercept] 调用豆包生成私信文案...")
                        dm_text = await _doubao_with_timeout(
                            [
                                {"role": "system", "content": "你是专业的私信客服。"},
                                {"role": "user", "content": prompt_filled},
                            ],
                            temperature=0.7,
                            timeout_s=20.0,
                        )
                        if not dm_text:
                            dm_text = args.fixed_dm
                        dm_text = (dm_text.splitlines()[0] or "").strip()
                    else:
                        dm_text = args.fixed_dm

                    new_page = await _open_user_card_from_comment(page, item)
                    if not new_page:
                        logger.warning("[Intercept] 点击评论头像失败（可能用户不存在/跳转失败），换下一个人")
                        continue
                    video_url_snapshot = page.url
                    page = new_page
                    await _human_pause(page, 0.8, 1.6)

                    user_id = ""
                    try:
                        user_id = page.url
                    except Exception:
                        user_id = f"USER_{video_clicked}_{r}_{ci}"

                    if user_id in sent_map:
                        logger.info("[Intercept] 该用户已私信过（去重），跳过")
                        try:
                            await page.keyboard.press("Escape")
                        except Exception:
                            pass
                        await _human_pause(page, 0.4, 0.9)
                        continue

                    if not args.enable_dm:
                        # 候选收集模式：不点击私信入口、不发送 DM
                        dm_visible = await _has_dm_entry(page)
                        logger.info(f"[Intercept][DRY_RUN] 候选 user_id={user_id} dm_visible={dm_visible}")
                        if dm_visible:
                            dm_candidates += 1
                            ai_decision = ""
                            if args.enable_ai_decision:
                                ai_decision = await _ai_intent_decide(intent_comment_text, args.keyword)
                                logger.info(f"[Intercept][AI] user_id={user_id} decision={ai_decision}")
                            cand = {
                                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "keyword": args.keyword,
                                "video_url": video_url_snapshot,
                                "user_id": user_id,
                                "intent_comment": intent_comment_text,
                                "dm_text": dm_text,
                                "status": "candidate",
                                "ai_decision": ai_decision,
                            }
                            try:
                                with open(candidates_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(cand, ensure_ascii=False) + "\n")
                            except Exception:
                                pass
                            if ai_decision == "是":
                                approved_count += 1
                                try:
                                    with open(approved_path, "a", encoding="utf-8") as f:
                                        f.write(json.dumps(cand, ensure_ascii=False) + "\n")
                                except Exception:
                                    pass
                            # 如果用户要求“走到手动发送前一步”，只对 AI=是 的候选执行
                            if args.open_approved_and_wait_sent and ai_decision == "是":
                                logger.info("[Intercept][MANUAL] 已触发手动发送准备：打开聊天并预填文案（不自动发送）")
                                _copy_to_clipboard(args.manual_dm_text)
                                dm_page = await _click_follow_and_dm(page)
                                if not dm_page:
                                    logger.warning("[Intercept][MANUAL] 未能打开聊天输入框，跳过该候选")
                                    try:
                                        await page.keyboard.press("Escape")
                                    except Exception:
                                        pass
                                    continue
                                page = dm_page
                                await page.wait_for_timeout(800)
                                ok_type = await _type_dm_text_without_sending(page, args.manual_dm_text)
                                if not ok_type:
                                    logger.warning("[Intercept][MANUAL] 未能定位输入框并输入文本，请手动在输入框粘贴/输入")
                                logger.info("[Intercept][MANUAL] 请你在抖音界面点击发送。脚本将等待回显确认…")
                                # 打字后先取一个 baseline：避免“聊天里之前就有同样文本”造成误判
                                baseline_count = await _count_text_occurrences(page, args.manual_dm_text)
                                sent_ok = await _wait_for_dm_echo(
                                    page,
                                    args.manual_dm_text,
                                    baseline_count=baseline_count,
                                    timeout_s=args.manual_wait_sent_timeout,
                                )
                                if sent_ok:
                                    dm_sent += 1
                                    video_dm_sent += 1
                                    rec = {
                                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                        "keyword": args.keyword,
                                        "video_url": video_url_snapshot,
                                        "user_id": user_id,
                                        "intent_comment": intent_comment_text,
                                        "dm_text": args.manual_dm_text,
                                        "status": "sent_manual",
                                    }
                                    _append_dedup(dedup_path, rec)
                                    sent_map[user_id] = rec
                                    try:
                                        with open(sent_users_path, "a", encoding="utf-8") as f:
                                            f.write(user_id + "\n")
                                        with open(dm_recs_path, "a", encoding="utf-8") as f:
                                            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                                    except Exception:
                                        pass
                                    logger.info(f"[Intercept][MANUAL] ✅ 检测到你已手动发送：dm_sent={dm_sent}")
                                    # 达到日上限就停止
                                    if dm_sent >= args.dm_daily_limit:
                                        logger.info("[Intercept] 达到日私信上限（手动发送后），停止")
                                        break
                                else:
                                    logger.warning("[Intercept][MANUAL] 未检测到回显（可能未发送），继续找下一个人")

                                # 发送后返回评论继续
                                try:
                                    await page.keyboard.press("Escape")
                                    await page.wait_for_timeout(400)
                                    await page.keyboard.press("Escape")
                                except Exception:
                                    pass
                                await _human_pause(page, 0.5, 1.2)
                                continue

                        # 关闭用户卡片/弹层，回到评论区
                        try:
                            await page.keyboard.press("Escape")
                            await page.wait_for_timeout(400)
                            await page.keyboard.press("Escape")
                        except Exception:
                            pass
                        await _human_pause(page, 0.5, 1.2)
                        continue

                    # 真发送模式
                    dm_page = await _click_follow_and_dm(page)
                    if not dm_page:
                        logger.warning("[Intercept] 未找到/未能点击私信入口，换下一个人")
                        await _dump(page, "dm_entry_failed")
                        try:
                            await page.keyboard.press("Escape")
                        except Exception:
                            pass
                        await _human_pause(page, 0.4, 0.9)
                        continue
                    page = dm_page

                    await _human_pause(page, 1.0, 2.2)

                    ok = await _send_dm_and_verify(page, dm_text)
                    if ok:
                        dm_sent += 1
                        video_dm_sent += 1
                        rec = {
                            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "keyword": args.keyword,
                            "video_url": page.url,
                            "user_id": user_id,
                            "intent_comment": intent_comment_text,
                            "dm_text": dm_text,
                            "status": "sent",
                        }
                        _append_dedup(dedup_path, rec)
                        sent_map[user_id] = rec
                        logger.info(f"[Intercept] ✅ 私信成功并写入去重 dm_sent={dm_sent}")
                        try:
                            with open(sent_users_path, "a", encoding="utf-8") as f:
                                f.write(user_id + "\n")
                            with open(dm_recs_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        except Exception:
                            pass
                    else:
                        logger.warning("[Intercept] 私信发送或回显校验失败（未成功），换下一个人")

                    try:
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(500)
                        await page.keyboard.press("Escape")
                    except Exception:
                        pass
                    await _human_pause(page, 0.8, 1.8)

                if video_dm_sent >= args.dm_per_video or dm_sent >= args.dm_daily_limit:
                    break
                # 继续下拉加载更多评论，再“换人继续找”
                await _scroll_comment_panel(page, px=args.comment_scroll_px)

            logger.info(f"[Intercept] 本视频评论扫描完成：intent_hits={intent_hits} dm_sent_total={dm_sent}")

            # 6) 素材评论：仅在本视频至少发出一个私信后执行（默认不自动评论）
            if video_dm_sent > 0 and args.enable_comment:
                try:
                    # comment-only + 手动发布：即使自动没点开评论区也继续（先生成文案并复制，你再手动点评论气泡）
                    if not opened and not (args.comment_only and args.manual_comment_wait):
                        raise RuntimeError("comment panel not opened")
                    if not opened and args.comment_only and args.manual_comment_wait:
                        logger.warning(
                            "[Intercept][MANUAL] 未自动展开评论区：请你在视频页右侧手动点「评论」气泡打开；"
                            "脚本随后会把评论复制到剪贴板，你粘贴后点发布即可。"
                        )
                    if args.use_doubao:
                        vars2 = {
                            "videoTitle": "",
                            "videoDesc": "",
                            "keyword": args.keyword,
                            "priceRange": "",
                            "companyName": "",
                            "serviceRegion": "",
                            "targetAudience": "",
                            "businessYear": "",
                            "keyFeatures": "",
                            "relatedNotes": "",
                        }
                        c_prompt = PROMPT_COMMENT.read_text("utf-8", errors="ignore")
                        prompt_filled2 = _fill_template(c_prompt, vars2)
                        logger.info("[Intercept] 调用豆包生成素材评论...")
                        comment_text = await _doubao_with_timeout(
                            [
                                {"role": "system", "content": "你是评论区的懂行用户。"},
                                {"role": "user", "content": prompt_filled2},
                            ],
                            temperature=0.8,
                            timeout_s=20.0,
                        )
                        if not comment_text:
                            comment_text = args.fixed_comment
                        comment_text = (comment_text.splitlines()[0] or "").strip()[:30]
                    else:
                        comment_text = args.fixed_comment

                    # 先生成文案就立刻复制到剪贴板（即使后面 DOM 定位失败，你也能手动 Ctrl+V）
                    _copy_to_clipboard(comment_text)
                    logger.info(f"[Intercept][MANUAL] 评论文案已复制到系统剪贴板，你可手动粘贴: {comment_text!r}")

                    if not await _is_comment_input_visible(page):
                        await _force_open_comment_sidebar(page)

                    if not await _wait_until_comment_editable(page, 10000):
                        logger.warning(
                            "[Intercept] 超时未检测到可用评论输入框，若评论区未展开请先手动点开，脚本仍将尝试写入"
                        )

                    filled = False
                    # 1) 优先：在所有 frame 里定位输入框 + insert_text/DOM（你能看到「留下你的精彩评论吧」时最稳）
                    editor, is_textarea, _fr = await _find_comment_editor_any_frame(page)
                    if editor is not None:
                        try:
                            await _type_into_comment_editor(page, editor, is_textarea, comment_text)
                            filled = True
                        except Exception as e_editor:
                            logger.warning(
                                f"[Intercept] 定位到评论框但写入失败，将尝试 DOM 注入/坐标: {e_editor}"
                            )
                    else:
                        logger.warning("[Intercept] 未定位到评论输入框（含 iframe），将尝试 DOM 注入/坐标粘贴")

                    # 2) 多 frame DOM 注入兜底（不依赖读回校验）
                    if not filled and await _inject_comment_text_dom(page, comment_text):
                        filled = True

                    if not filled:
                        logger.warning("[Intercept] 素材评论输入框写入未成功，启用坐标点击后再 DOM 注入")
                        # 坐标兜底：评论输入通常在底部区域（固定位置点击，避免随机遍历）
                        try:
                            _copy_to_clipboard(comment_text)
                            vp = page.viewport_size or {}
                            w = int(vp.get("width") or 1280)
                            h = int(vp.get("height") or 720)
                            for (x, y) in [
                                (w // 2, int(h * 0.93)),
                                (w // 2, int(h * 0.88)),
                            ]:
                                try:
                                    await page.mouse.click(x, y, timeout=3000)
                                    await page.wait_for_timeout(400)
                                    if await _inject_comment_text_dom(page, comment_text):
                                        filled = True
                                        break
                                    await page.keyboard.down("Control")
                                    await page.keyboard.press("V")
                                    await page.keyboard.up("Control")
                                    await page.wait_for_timeout(500)
                                    if await _inject_comment_text_dom(page, comment_text):
                                        filled = True
                                        break
                                except Exception:
                                    continue
                            if not filled:
                                filled = await _inject_comment_text_dom(page, comment_text)
                        except Exception as e_paste:
                            logger.warning(f"[Intercept] 坐标粘贴失败: {e_paste}")
                    if not filled:
                        # 最后兜底：直接点「留下你的精彩评论吧」并键盘输入
                        try:
                            if await _force_type_comment_by_placeholder(page, comment_text, timeout_ms=12000):
                                filled = True
                        except Exception as e_force:
                            logger.warning(f"[Intercept] 占位文案强制键入失败: {e_force}")
                    if args.manual_comment_wait:
                        # 手动发送模式下，持续重试写入，避免评论框晚激活导致第一次没进文本
                        warmup_deadline = time.monotonic() + 25.0
                        while time.monotonic() < warmup_deadline:
                            if filled:
                                break
                            try:
                                if await _force_type_comment_by_placeholder(page, comment_text, timeout_ms=1800):
                                    filled = True
                                    logger.info("[Intercept][MANUAL] 轮询重试写入成功（可手动点发送）")
                                    break
                            except Exception:
                                pass
                            await page.wait_for_timeout(1200)
                        if filled:
                            logger.info(
                                f"[Intercept][MANUAL] 已尝试把素材写入评论框，请你在界面确认文字后手动点发送: "
                                f"{comment_text!r}"
                            )
                        else:
                            logger.warning(
                                f"[Intercept][MANUAL] 自动写入未成功，剪贴板已就绪，请手动粘贴后点发送: "
                                f"{comment_text!r}"
                            )
                        # 保险起见再复制一次，确保粘贴板是最新内容
                        _copy_to_clipboard(comment_text)
                        # baseline：避免“输入框里已存在同样文本/页面本来就有同文”造成误判
                        baseline_count = await _count_text_occurrences(page, comment_text)
                        sent_ok = await _wait_for_comment_echo(
                            page,
                            comment_text,
                            timeout_s=args.manual_comment_wait_timeout,
                            baseline_count=baseline_count,
                        )
                        if sent_ok:
                            logger.info("[Intercept][MANUAL] ✅ 检测到评论回显，认为已发布")
                        else:
                            logger.warning("[Intercept][MANUAL] 未检测到评论回显（可能发布失败/未即时渲染），请人工确认")
                    else:
                        if filled:
                            await page.keyboard.press("Enter")
                            logger.info(f"[Intercept] 已发送素材评论: {comment_text!r}")
                        else:
                            logger.warning("[Intercept] 未能确认填入素材评论，跳过 Enter 发送")
                except Exception as e:
                    logger.warning(f"[Intercept] 发送素材评论失败: {e}")
                    await _dump(page, "comment_send_failed")
            else:
                logger.info("[Intercept] 本视频未私信成功，跳过素材评论")

            await page.wait_for_timeout(int(_rand_sleep(1.2, 2.8) * 1000))

            # 返回搜索页继续
            try:
                # 优先 go_back（和点击进入对应），不行再 goto 搜索页
                await page.go_back(timeout=20000)
                await page.wait_for_timeout(2000)
                if "/search/" not in (page.url or ""):
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
                    await page.wait_for_timeout(2000)
            except Exception:
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass
            await page.wait_for_timeout(int(_rand_sleep(1.0, 2.5) * 1000))
            continue

        # 2.1) 尝试读取卡片附近的点赞数（不稳定，失败就先放过不筛）
        like_ok = True
        likes = None
        try:
            # 从链接往上找包含“赞”相关文本的区域（很粗糙，后续再用真实 DOM 精修）
            parent = link.locator("xpath=ancestor::div[1]")
            txt = (await parent.inner_text(timeout=1000)) or ""
            # 提取第一个可能的数字作为点赞候选
            m = re.search(r"(\d+(?:\.\d+)?\s*(?:w|万)?)", txt.lower())
            if m:
                likes = _parse_like_to_int(m.group(1).replace(" ", ""))
                if likes < args.min_likes:
                    like_ok = False
        except Exception:
            pass

        if not like_ok:
            logger.info(f"[Intercept] 跳过（点赞<{args.min_likes}） href={href} likes={likes}")
            continue

        logger.info(f"[Intercept] 进入视频 #{video_clicked+1} href={href} likes={likes}")

        # 打开新视频
        try:
            await link.scroll_into_view_if_needed(timeout=6000)
            await link.click(timeout=8000, force=True)
        except Exception as e:
            logger.warning(f"[Intercept] 点击视频失败，将直接跳转 URL: {e}")
            try:
                url = href
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    url = "https://www.douyin.com" + url
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception as e2:
                logger.warning(f"[Intercept] 直接跳转也失败: {e2}")
                await _dump(page, "goto_video_failed")
                continue

        await page.wait_for_timeout(2500)
        video_clicked += 1

        # Debug：落盘一次视频详情页（便于后续精修评论/按钮定位）
        try:
            await _dump(page, f"video_detail_{video_clicked}")
        except Exception:
            pass

        # 3) 打开评论区（多策略），并记住是否确认打开
        opened = await _open_comment_panel(page)
        if not await _is_comment_input_visible(page):
            forced = await _force_open_comment_sidebar(page)
            opened = opened or forced
        logger.info(f"[Intercept] 评论区打开结果 opened={opened} input_visible={await _is_comment_input_visible(page)}")
        if not opened:
            await _dump(page, f"comment_panel_not_opened_{video_clicked}")
        await page.wait_for_timeout(1200)

        # 4) 扫可见评论条目，按关键词做意向判定；命中则：点头像->关注->私信->发送并校验
        items, take_n = await _extract_visible_comment_items(page)
        if take_n == 0:
            logger.info("[Intercept] 未找到可见评论条目，准备给素材评论后返回下一个视频")
        else:
            logger.info(f"[Intercept] 可见评论条目数(取样): {take_n}")

        intent_hits = 0
        video_dm_sent = 0
        for ci in range(take_n):
            if dm_sent >= args.dm_daily_limit:
                logger.info("[Intercept] 达到日私信上限，停止在该视频的评论处理")
                break

            item = items.nth(ci)
            try:
                txt = (await item.inner_text(timeout=800)) or ""
            except Exception:
                continue

            # 过滤明显不是评论内容的大块文本（页脚/导航/下载提示等）
            if "下载抖音精选" in txt or "京ICP备" in txt or "2026 ©" in txt:
                continue
            # 文本太长往往说明抓到了容器，不是单条评论
            if len(txt) > 500:
                continue

            # 意向判定：先规则
            if not _is_intent_comment(txt):
                continue
            intent_hits += 1

            logger.info(f"[Intercept] 命中意向评论(片段): {txt[:60]!r}")

            # 生成私信文案（固定或豆包）
            if args.use_doubao:
                persona_vars = {
                    "userMessage": txt[:200],
                    "chatHistory": "",
                    "nickname": "",
                    "priceRange": "",
                    "wechatId": "",
                    "companyName": "",
                    "serviceRegion": "",
                    "targetAudience": "",
                    "companyAddress": "",
                    "businessYear": "",
                    "keyFeatures": "",
                    "relatedNotes": "",
                }
                dm_prompt = PROMPT_DM.read_text("utf-8", errors="ignore")
                prompt_filled = _fill_template(dm_prompt, persona_vars)
                logger.info("[Intercept] 调用豆包生成私信文案...")
                dm_text = await _doubao_with_timeout(
                    [
                        {"role": "system", "content": "你是专业的私信客服。"},
                        {"role": "user", "content": prompt_filled},
                    ],
                    temperature=0.7,
                    timeout_s=20.0,
                )
                if not dm_text:
                    dm_text = args.fixed_dm
                dm_text = (dm_text.splitlines()[0] or "").strip()
            else:
                dm_text = args.fixed_dm

            # 点头像进入用户卡片/弹层
            if not await _open_user_card_from_comment(page, item):
                logger.warning("[Intercept] 点击评论头像失败，跳过该条")
                continue
            await _human_pause(page, 0.8, 1.6)

            # 获取一个可用的 user_id 做去重：优先取当前 URL（进入用户页/弹层后可能变化）
            user_id = ""
            try:
                user_id = _normalize_user_id(page.url) or page.url
            except Exception:
                user_id = f"USER_{video_clicked}_{ci}"

            if user_id in sent_map:
                logger.info("[Intercept] 该用户已私信过（去重），跳过")
                # 关闭弹层：尝试 ESC
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                await _human_pause(page, 0.4, 0.9)
                continue

            # 关注 + 私信入口
            if not await _click_follow_and_dm(page):
                logger.warning("[Intercept] 未找到/未能点击私信入口，跳过该用户")
                await _dump(page, "dm_entry_failed")
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                continue

            await _human_pause(page, 1.0, 2.2)

            ok = await _send_dm_and_verify(page, dm_text)
            if ok:
                dm_sent += 1
                rec = {
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "keyword": args.keyword,
                    "video_url": page.url,
                    "user_id": user_id,
                    "dm_text": dm_text,
                    "status": "sent",
                }
                _append_dedup(dedup_path, rec)
                sent_map[user_id] = rec
                logger.info(f"[Intercept] ✅ 私信成功并写入去重 dm_sent={dm_sent}")
            else:
                logger.warning("[Intercept] 私信发送或回显校验失败（已落盘），跳过该用户")

            # 关闭私信/弹层，回到视频评论区继续
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
                await page.keyboard.press("Escape")
            except Exception:
                pass
            await _human_pause(page, 0.8, 1.8)

        logger.info(f"[Intercept] 本视频评论扫描完成：scan={take_n} intent_hits={intent_hits} dm_sent_total={dm_sent}")

        # 6) 最后发一条素材评论（一句话）- 测试阶段先固定或豆包生成
        try:
            if not args.enable_comment:
                raise RuntimeError("auto-comment disabled")
            if not opened:
                raise RuntimeError("comment panel not opened")

            if args.use_doubao:
                vars2 = {
                    "videoTitle": "",
                    "videoDesc": "",
                    "keyword": args.keyword,
                    "priceRange": "",
                    "companyName": "",
                    "serviceRegion": "",
                    "targetAudience": "",
                    "businessYear": "",
                    "keyFeatures": "",
                    "relatedNotes": "",
                }
                c_prompt = PROMPT_COMMENT.read_text("utf-8", errors="ignore")
                prompt_filled2 = _fill_template(c_prompt, vars2)
                logger.info("[Intercept] 调用豆包生成素材评论...")
                comment_text = await _doubao_with_timeout(
                    [
                        {"role": "system", "content": "你是评论区的懂行用户。"},
                        {"role": "user", "content": prompt_filled2},
                    ],
                    temperature=0.8,
                    timeout_s=20.0,
                )
                if not comment_text:
                    comment_text = args.fixed_comment
                comment_text = (comment_text.splitlines()[0] or "").strip()[:30]
            else:
                comment_text = args.fixed_comment

            _copy_to_clipboard(comment_text)
            logger.info(f"[Intercept][MANUAL] 评论文案已复制到系统剪贴板: {comment_text!r}")
            if not await _is_comment_input_visible(page):
                await _force_open_comment_sidebar(page)

            editor, is_textarea, _fr = await _find_comment_editor_any_frame(page)
            if editor is None:
                raise RuntimeError("comment editor not found")
            await _type_into_comment_editor(page, editor, is_textarea, comment_text)
            await page.keyboard.press("Enter")
            logger.info(f"[Intercept] 已发送素材评论: {comment_text!r}")
        except Exception as e:
            logger.warning(f"[Intercept] 发送素材评论失败: {e}")
            await _dump(page, "comment_send_failed")

        await page.wait_for_timeout(int(_rand_sleep(1.2, 2.8) * 1000))

        # 7) 返回搜索结果继续
        try:
            await page.go_back(timeout=15000)
            await page.wait_for_timeout(2500)
        except Exception:
            try:
                await page.goto("https://www.douyin.com/search/" + args.keyword, wait_until="domcontentloaded", timeout=90000)
            except Exception:
                pass
        await page.wait_for_timeout(int(_rand_sleep(1.0, 2.5) * 1000))

    logger.info(
        f"[Intercept] 完成：处理视频数={video_clicked} dm_sent(真实发送)={dm_sent} "
        f"dm_candidates(候选)={dm_candidates} approved_ai_candidates(是)={approved_count} run_dir={run_dir}"
    )
    try:
        sent_users = [x.strip() for x in sent_users_path.read_text(encoding="utf-8", errors="ignore").splitlines() if x.strip()]
        logger.info(f"[Intercept] 本次实际写入用户数={len(sent_users)}（见 {sent_users_path}）")
        for i, uid in enumerate(sent_users[:50], 1):
            logger.info(f"[Intercept] [{i}] {uid}")
    except Exception as e:
        logger.warning(f"[Intercept] 读取本次 sent_users 列表失败: {e}")

    # 候选收集（不会写入去重文件，不会影响后续真实发送逻辑）
    try:
        cand_lines = [ln.strip() for ln in candidates_path.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
        logger.info(f"[Intercept] 本次候选收集记录数={len(cand_lines)}（见 {candidates_path}）")
        # 打印前 20 条候选的 user_id，方便你对照评论原文
        for i, ln in enumerate(cand_lines[:20], 1):
            try:
                obj = json.loads(ln)
                logger.info(
                    f"[Intercept][Cand] [{i}] user_id={obj.get('user_id','')} "
                    f"ai_decision={obj.get('ai_decision','')} intent_comment={(obj.get('intent_comment','') or '')[:60]!r}"
                )
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[Intercept] 读取 candidates_path 失败: {e}")

    # 打印 approved 列表（AI判定为“是”）
    try:
        ap_lines = [ln.strip() for ln in approved_path.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()]
        logger.info(f"[Intercept] 本次 AI 通过候选记录数={len(ap_lines)}（见 {approved_path}）")
        for i, ln in enumerate(ap_lines[:15], 1):
            try:
                obj = json.loads(ln)
                logger.info(f"[Intercept][Approved] [{i}] user_id={obj.get('user_id','')} intent_comment={(obj.get('intent_comment','') or '')[:60]!r}")
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[Intercept] 读取 approved_path 失败: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))


