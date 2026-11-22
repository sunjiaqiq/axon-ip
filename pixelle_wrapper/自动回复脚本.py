"""
自动回复脚本（Playwright）

功能：
- 抖音主页检测未读红点/数字 → 进入私信 → 挨个点开未读会话 → 发送回复并验证回显
- 主页连续无未读超过阈值（默认10秒）自动退出

运行（PowerShell）：
& "F:\\shuziren\\dist\\Axon_Program\\runtime_env\\python\\python.exe" "F:\\shuziren\\pixelle_wrapper\\自动回复脚本.py" --max-minutes 60 --poll-seconds 5 --wait-seconds 4 --idle-close-seconds 10 --keep-browser --message "auto-reply-ok"

参数（也可用环境变量兜底）：
- --wait-seconds / DOUYIN_TEST_WAIT_SECONDS: 3~5
- --poll-seconds / DOUYIN_POLL_SECONDS
- --max-minutes / DOUYIN_MAX_MINUTES
- --idle-close-seconds / DOUYIN_IDLE_CLOSE_SECONDS
- --message / DOUYIN_TEST_MESSAGE
- --keep-browser / DOUYIN_TEST_KEEP_BROWSER
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import os
import sys
import re
import time
import logging
from pathlib import Path


logger = logging.getLogger(__name__)
NO_MOUSE_ACTIONS = False


THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))


from ai_pipeline.browser_manager import browser_manager  # noqa: E402
from ai_pipeline.doubao_client import doubao_chat_completion  # noqa: E402


DOUYIN_HOME_URL = "https://www.douyin.com/"
REPLY_RECORD_PATH = THIS_DIR / "output" / "dm_reply_records.jsonl"

# ---------------------------
# AI 用于辅助提取 chat_key
# ---------------------------
_AI_CHAT_KEY_CACHE: dict[str, str] = {}

_AI_EXTRACT_SYSTEM_PROMPT = (
    "你是一个抖音私信自动化脚本的助手。"
    "给你一段“未读会话行”或“会话标题/区域”的原始文本。"
    "你的任务是从中提取稳定的聊天对象标识 chat_key。"
    "chat_key 需要尽量简短、稳定，用于去重与确认当前会话对象。"
    "输出必须是 JSON，且只包含字段：{\"chat_key\": \"...\"}。"
    "chat_key 优先返回数字型用户id（形如 用户123456789 或 长数字），其次返回简短昵称（例如以 '.' 结尾的短名）。"
    "如果无法可靠提取，返回空字符串 \"\"。"
)


def _safe_json_extract_chat_key(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    # 尝试直接 JSON parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and isinstance(obj.get("chat_key"), str):
            return obj["chat_key"].strip()
    except Exception:
        pass

    # 尝试提取第一个 {...} 段再 parse
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            obj2 = json.loads(text[start : end + 1])
            if isinstance(obj2, dict) and isinstance(obj2.get("chat_key"), str):
                return obj2["chat_key"].strip()
    except Exception:
        pass
    return ""


async def _ai_extract_chat_key(raw: str) -> str:
    """
    AI 兜底：当正则提取失败或结果异常时，用豆包从 raw 中提取 chat_key。
    提取失败则返回 ""，由调用方 fallback 到写死提取逻辑。
    """
    raw = (raw or "").strip()
    if not raw:
        return ""

    cache_key = str(hash(raw))
    if cache_key in _AI_CHAT_KEY_CACHE:
        return _AI_CHAT_KEY_CACHE[cache_key]

    # 截断，避免传入过长 inner_text
    raw_cut = raw[:900]

    messages = [
        {"role": "system", "content": _AI_EXTRACT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"raw_text:\n{raw_cut}\n\n请输出 JSON: {{\"chat_key\":\"...\"}}",
        },
    ]

    try:
        # 在独立线程执行同步请求，避免阻塞事件循环
        assistant_text = await asyncio.to_thread(
            doubao_chat_completion,
            messages,
            temperature=0.2,
            timeout_s=35,
        )
        ck = _safe_json_extract_chat_key(assistant_text)
        _AI_CHAT_KEY_CACHE[cache_key] = ck
        return ck
    except Exception as e:
        logger.warning(f"[AI] chat_key 提取失败，fallback 到正则：{e}")
        _AI_CHAT_KEY_CACHE[cache_key] = ""
        return ""


async def _reuse_existing_page():
    """
    在不做任何 goto 跳转的前提下，复用当前 Playwright 持久化上下文里的页面。
    用于：你已经手动停在私信页，脚本只负责点击会话/发送消息。
    """
    await browser_manager.initialize()
    ctx = getattr(browser_manager, "_context", None)
    if ctx and getattr(ctx, "pages", None):
        pages = ctx.pages
        if pages:
            # 优先选择真正的私信路由页：/message
            page = pages[0]
            try:
                for p in pages:
                    u = (getattr(p, "url", "") or "").lower()
                    if "douyin.com/message" in u:
                        page = p
                        break
            except Exception:
                pass
            try:
                await page.bring_to_front()
            except Exception:
                pass
            # 保护：skip-entry-click 模式下绝不能落到空白页
            try:
                current_url = (page.url or "").strip().lower()
                if "about:blank" in current_url or current_url == "chrome://new-tab-page/":
                    raise RuntimeError(f"复用到的页面是空白页（{page.url}），请先手动停在私信页后再启动 --skip-entry-click。")
            except Exception as e:
                raise
            return page
    # 没有可复用的页面时，不要创建新 tab（否则会停在 about:blank / 新白页）。
    raise RuntimeError("未找到可复用的浏览器页面。请先用浏览器主程序打开到私信页/会话页再启动该脚本（使用 --skip-entry-click）。")


def _debug_dir() -> Path:
    p = THIS_DIR / "debug_artifacts_pw"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _setup_logging() -> Path:
    log_dir = THIS_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"douyin_dm_watch_{_ts()}.log"

    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s")

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"[PW] 日志文件: {log_path}")
    return log_path


async def _dump(page, step: str) -> None:
    base = _debug_dir() / f"{_ts()}_{step}"
    try:
        await page.screenshot(path=str(base) + ".png", full_page=True)
        logger.info(f"[PW][Debug] 截图: {base}.png")
    except Exception as e:
        logger.warning(f"[PW][Debug] 截图失败: {e}")
    try:
        html = await page.content()
        with open(str(base) + ".html", "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"[PW][Debug] HTML: {base}.html")
    except Exception as e:
        logger.warning(f"[PW][Debug] HTML保存失败: {e}")


async def _human_pause(page, a: float = 3.0, b: float = 5.0) -> None:
    await page.wait_for_timeout(int(random.uniform(a, b) * 1000))


async def _human_prepare_click(page, locator) -> None:
    """
    点击前增加一些人类化动作，减少“机械点击”导致的误触发。
    """
    await locator.scroll_into_view_if_needed(timeout=2500)
    if NO_MOUSE_ACTIONS:
        # 重要：--no-mouse-actions 只禁止 mouse.move，不禁止 hover。
        # 抖音私信/半浮层很多依赖 hover 来渲染未读计数与列表项。
        try:
            await locator.hover(timeout=1200)
        except Exception:
            pass
        await _human_pause(page)
        return
    box = await locator.bounding_box()
    if box:
        x = box["x"] + min(max(random.uniform(0.28, 0.72) * box["width"], 2), max(box["width"] - 2, 2))
        y = box["y"] + min(max(random.uniform(0.28, 0.72) * box["height"], 2), max(box["height"] - 2, 2))
        try:
            await page.mouse.move(x, y, steps=random.randint(8, 20))
            await _human_pause(page)
        except Exception:
            pass
    try:
        await locator.hover(timeout=1200)
    except Exception:
        pass
    await _human_pause(page)

async def _prime_dm_panel_hover(page) -> None:
    """
    skip-entry-click 模式下：页面已在私信页，但 Semi 面板/未读 badge 可能仍未完全展开。
    通过 hover 一下关键入口/页签，让 DOM 更稳定，再去读未读与点击会话。
    """
    candidates = [
        page.locator("#douyin-navigation a[href*='/message']").first,
        page.get_by_text("私信", exact=True).first,
        page.locator("[role='tab']:has-text('陌生人')").first,
        page.get_by_text("陌生人", exact=True).first,
    ]
    for loc in candidates:
        try:
            if await loc.count() > 0:
                await _human_prepare_click(page, loc)
                return
        except Exception:
            continue

async def _find_and_click_dm_entry(page) -> bool:
    # 仅在“有未读数字/红点”时，点击“私信”这个入口一次。
    badge = page.locator("span.semi-badge-count, span[class*='semi-badge-count']").first
    if await badge.count() == 0:
        badge = page.locator("span.semi-badge-dot, span[class*='semi-badge-dot']").first
    if await badge.count() == 0:
        return False

    entry = page.locator("#douyin-navigation a[href*='/message'], #douyin-navigation a[href*='//www.douyin.com/message']").first
    if await entry.count() == 0:
        entry = page.locator("#douyin-navigation :text('私信')").first
    if await entry.count() == 0:
        entry = page.get_by_text("私信", exact=True).first
    if await entry.count() == 0:
        logger.warning("[PW] 检测到未读，但未找到私信入口节点")
        return False

    try:
        await entry.wait_for(state="visible", timeout=4000)
        await entry.scroll_into_view_if_needed(timeout=2500)
        # 关键步骤：先 hover 私信入口，让下拉/列表区域稳定出现。
        try:
            await entry.hover(timeout=2000)
            await _human_pause(page)
        except Exception:
            pass
        await _human_pause(page)
        # 私信入口使用精确点击，避免随机偏移误触到相邻导航。
        await entry.click(timeout=3500)
        await _human_pause(page)
        if not await _dm_panel_ready(page):
            # 再次通过导航容器内 /message 链接做一次“定点点击”。
            try:
                clicked = await page.evaluate(
                    """
                    () => {
                      const nav = document.querySelector('#douyin-navigation');
                      if (!nav) return false;
                      const a = nav.querySelector("a[href*='/message'], a[href*='//www.douyin.com/message']");
                      if (!a) return false;
                      a.click();
                      return true;
                    }
                    """
                )
                if clicked:
                    await _human_pause(page)
            except Exception:
                pass
        logger.info("[PW] 已点击私信入口（单路径）")
        return True
    except Exception as e:
        logger.warning(f"[PW] 点击私信入口失败: {e}")
        return False


async def _chat_opened(page) -> bool:
    # 强约束：只有“疑似私信会话页”时，才允许认为聊天输入已打开。
    # 否则页面上别的 contenteditable 也可能误命中，导致误发/取错聊天对象。
    if not await _dm_panel_ready(page):
        return False

    placeholder = page.get_by_text("发送消息").first
    try:
        await placeholder.wait_for(state="visible", timeout=1500)
        return True
    except Exception:
        pass

    editable = page.locator("div[contenteditable='true'][data-placeholder]").first
    if await editable.count():
        try:
            await editable.wait_for(state="visible", timeout=1500)
            return True
        except Exception:
            pass

    return False


async def _switch_to_stranger_tab(page) -> bool:
    """
    进入私信页后，优先切到“陌生人”页签再处理未读。
    """
    # 陌生人 tab 切换时，发送框/输入框有时异步渲染很慢。

    async def _tab_is_selected(tab_locator) -> bool:
        try:
            aria_selected = await tab_locator.get_attribute("aria-selected")
            if aria_selected and aria_selected.lower() == "true":
                return True
        except Exception:
            pass
        try:
            # className/role 可能不是固定命名，这里做包含式兜底判断
            cls = await tab_locator.get_attribute("class") or ""
            cls = cls.lower()
            return ("active" in cls) or ("selected" in cls) or ("is-active" in cls)
        except Exception:
            return False

    candidates = [
        page.locator("[role='tab'][aria-controls]:has-text('陌生人')").first,
        page.locator("[role='tab']:has-text('陌生人')").first,
    ]

    for i, tab in enumerate(candidates):
        try:
            if await tab.count() == 0:
                continue
            await tab.wait_for(state="visible", timeout=2500)

            await _human_prepare_click(page, tab)
            try:
                await tab.click(timeout=3000)
            except Exception:
                await _human_pause(page)
                await tab.click(timeout=3000, force=True)

            # 等 tab 状态稳定：确认该 tab 被选中，且仍停留在 /message 路由
            ok = False
            deadline = time.time() + 6.0
            while time.time() < deadline:
                try:
                    current_url = (page.url or "").lower()
                    if ("douyin.com/message" in current_url) and await _tab_is_selected(tab):
                        ok = True
                        break
                except Exception:
                    pass
                await page.wait_for_timeout(400)

            if ok:
                logger.info(f"[PW] 已切换到“陌生人”页签（候选#{i+1}）")
                return True
            logger.warning(f"[PW] 点击陌生人页签后未确认选中态（候选#{i+1}），跳过该候选")
        except Exception:
            continue

    logger.warning("[PW] 未能切换到“陌生人”页签，保持当前页签处理")
    return False


async def _switch_to_default_dm_tab(page) -> bool:
    """
    切回私信默认会话页签（与“陌生人”对应的主会话列表）。
    """
    candidates = [
        page.get_by_text("全部", exact=True).first,
        page.get_by_text("消息", exact=True).first,
        page.get_by_text("私信", exact=True).first,
        page.locator("[role='tab']").first,
    ]
    for i, tab in enumerate(candidates):
        try:
            if await tab.count() == 0:
                continue
            await tab.wait_for(state="visible", timeout=2500)
            await tab.scroll_into_view_if_needed(timeout=2000)
            await tab.click(timeout=3000)
            await page.wait_for_timeout(800)
            logger.info(f"[PW] 已切回默认私信列表（候选#{i+1}）")
            return True
        except Exception:
            continue
    logger.warning("[PW] 未能明确切回默认私信列表，继续当前页签处理")
    return False


def _extract_chat_key_from_raw_text(raw: str) -> str:
    """
    从“列表行文本/标题文本”等原始文本中提取更像聊天对象标识的短字符串。
    返回 "" 表示无法提取。
    """
    raw = (raw or "").strip()
    if not raw:
        return ""

    lines = [l.strip() for l in raw.replace("\r", "\n").split("\n") if l.strip()]
    blacklist = [
        "搜索",
        "充钻石",
        "客户端",
        "壁纸",
        "通知",
        "私信",
        "投稿",
        "关闭会话",
        "关注",
        "刚刚",
        "昨天",
        "前天",
    ]
    lines = [l for l in lines if not any(b in l for b in blacklist)]
    if not lines:
        return ""

    # 用户标识（你的截图通常是用户数字）
    for l in lines:
        if re.search(r"用户\d{5,}", l) or re.search(r"\d{10,}", l):
            return l

    # 短昵称（常见以 '.' 结尾）
    for l in lines:
        if l.endswith(".") and 2 <= len(l) <= 40:
            return l

    # 最后：短文本兜底
    short = [l for l in lines if 1 <= len(l) <= 40]
    if short:
        return short[0]
    return lines[0][:80]


async def _current_chat_key(page) -> str:
    """
    提取当前会话的稳定标识，用于防止同一会话重复回复。
    """
    # 有些渲染是异步的：点击进入会话后，header 文案可能需要一点时间才会落到 DOM。
    # 因此这里做轻量重试，提高 chat_key 可识别率。
    last_txt: str = ""
    last_raw_for_ai: str = ""
    for _ in range(3):
        parts: list[str] = []
        try:
            for sel in [
                "[data-e2e='chat-user-name']",
                "[data-e2e*='chat'][data-e2e*='name']",
                "header [class*='name']",
                "[class*='conversation'][class*='active']",
                "[class*='title']",
            ]:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                txt = (await loc.inner_text()).strip()
                if txt:
                    norm = _extract_chat_key_from_raw_text(txt)
                    if norm:
                        parts.append(norm)
                        last_txt = norm
                        break
                    # 保存一份原始文本，供 AI 兜底
                    last_raw_for_ai = txt
        except Exception:
            pass

        key = " | ".join(parts).strip()
        if key:
            return key

        # 等待 DOM 渲染落地后再重试
        await page.wait_for_timeout(600)

    norm = last_txt.strip()
    if not norm or norm == "__unknown_chat__":
        try:
            if last_raw_for_ai:
                ai_key = await _ai_extract_chat_key(last_raw_for_ai)
                if ai_key:
                    return ai_key
        except Exception:
            pass
    return norm or "__unknown_chat__"


async def _open_first_unread_conversation(page) -> tuple[bool, str]:
    # 1) 优先处理“私信入口悬浮下拉列表”中的未读项（你说的鼠标移到私信后弹出的列表）
    popup_selectors = [
        ".semi-dropdown-content li:has([x-semi-prop='count'])",
        ".semi-dropdown-content li:has(span.semi-badge-count), .semi-dropdown-content li:has(span[class*='semi-badge-count'])",
        ".semi-dropdown-content li:has(span.semi-badge-dot), .semi-dropdown-content li:has(span[class*='semi-badge-dot'])",
    ]
    for p_idx, p_sel in enumerate(popup_selectors):
        rows = page.locator(p_sel)
        p_count = await rows.count()
        if p_count <= 0:
            continue
        logger.info(f"[PW] 命中悬浮私信未读列表#{p_idx+1}，候选数量: {p_count}")
        for i in range(min(p_count, 6)):
            row = rows.nth(i)
            hint_key = ""
            try:
                raw_hint = (await row.inner_text()) or ""
                hint_key = _extract_chat_key_from_raw_text(raw_hint)
                # 正则兜底：失败或过长时用 AI 提取稳定 chat_key
                if not hint_key or len(hint_key) > 80:
                    ai_key = await _ai_extract_chat_key(raw_hint)
                    if ai_key:
                        hint_key = ai_key
            except Exception:
                pass
            try:
                click_targets = [
                    row.locator("a").first,
                    row.locator("[role='menuitem']").first,
                    row,
                ]
                clicked = False
                for ct in click_targets:
                    try:
                        if await ct.count() == 0:
                            continue
                        await _human_prepare_click(page, ct)
                        await ct.click(timeout=2500)
                        clicked = True
                        break
                    except Exception:
                        continue
                if not clicked:
                    continue
                await _human_pause(page)
                if await _chat_opened(page) or await _dm_panel_ready(page):
                    logger.info(f"[PW] 已从悬浮私信列表进入会话（popup#{p_idx+1} / row#{i+1}）")
                    return True, hint_key
            except Exception:
                continue

    # 2) 处理私信页会话列表中的未读项
    unread_row_selectors = [
        "li:has([x-semi-prop='count'])",
        "[role='listitem']:has([x-semi-prop='count'])",
        "li:has(span.semi-badge-count), li:has(span[class*='semi-badge-count'])",
        "li:has(span.semi-badge-dot), li:has(span[class*='semi-badge-dot'])",
        "[role='listitem']:has(span.semi-badge-count), [role='listitem']:has(span[class*='semi-badge-count'])",
        "[role='listitem']:has(span.semi-badge-dot), [role='listitem']:has(span[class*='semi-badge-dot'])",
        "div[class*='conversation']:has([x-semi-prop='count'])",
        "div[class*='session']:has([x-semi-prop='count'])",
    ]

    for sel_idx, sel in enumerate(unread_row_selectors):
        rows = page.locator(sel)
        count = await rows.count()
        if count <= 0:
            continue
        logger.info(f"[PW] 命中未读会话选择器#{sel_idx+1}，候选数量: {count}")
        for idx in range(min(count, 8)):
            t = rows.nth(idx)
            hint_key = ""
            try:
                raw_hint = (await t.inner_text()) or ""
                hint_key = _extract_chat_key_from_raw_text(raw_hint)
                if not hint_key or len(hint_key) > 80:
                    ai_key = await _ai_extract_chat_key(raw_hint)
                    if ai_key:
                        hint_key = ai_key
            except Exception:
                pass
            try:
                await _human_prepare_click(page, t)
                # 会话行本身有时点不到真正进入对话的区域，优先点内部可点击元素。
                click_candidates = [
                    t.locator("a").first,
                    t.locator("[role='button']").first,
                    t.locator("button").first,
                    t,
                ]
                clicked = False
                for c_i, c in enumerate(click_candidates):
                    try:
                        if await c.count() == 0:
                            continue
                        await _human_prepare_click(page, c)
                        await c.click(timeout=2500)
                        clicked = True
                        break
                    except Exception:
                        continue
                if not clicked:
                    # force 作为最后兜底
                    try:
                        await t.click(timeout=2500, force=True)
                    except Exception:
                        pass
                await _human_pause(page)
                if await _chat_opened(page):
                    logger.info(f"[PW] 已进入聊天面板（selector#{sel_idx+1} / row#{idx+1}）")
                    return True, hint_key
                try:
                    await t.focus(timeout=800)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(600)
                    if await _chat_opened(page):
                        logger.info(f"[PW] 已进入聊天面板（selector#{sel_idx+1} / row#{idx+1} / enter）")
                        return True, hint_key
                except Exception:
                    pass
            except Exception:
                continue

    await _dump(page, "open_unread_conversation_failed")
    logger.error("[PW] 未能进入聊天面板（尝试点击未读会话失败）")
    return False, ""


async def _count_unread_badges(page) -> int:
    url = (page.url or "").lower()
    if "douyin.com/message" not in url:
        # 半浮层模式下 url 可能仍在首页；但我们用“未读行候选存在性”来决定是否统计，
        # 避免在普通首页误计数。
        evidence = page.locator(
            ".semi-dropdown-content li:has([x-semi-prop='count']), "
            "li:has([x-semi-prop='count']), "
            "[role='listitem']:has([x-semi-prop='count']), "
            ".semi-dropdown-content li:has(span.semi-badge-count)"
        )
        try:
            ev_n = await evidence.count()
        except Exception:
            ev_n = 0
        if ev_n <= 0:
            return 0
    badges = page.locator("[x-semi-prop='count']")
    n = await badges.count()
    if n:
        return n
    badges = page.locator("span.semi-badge-dot, span[class*='semi-badge-dot']")
    n = await badges.count()
    if n:
        return n
    badges = page.locator("span.semi-badge-count, span[class*='semi-badge-count']")
    return await badges.count()


async def _dm_panel_ready(page) -> bool:
    """
    只在真正进入私信会话页后，才允许继续处理未读。
    """
    # URL 兜底判定（不是强制跳转，只用于识别是否已进入私信页）
    url = (page.url or "").lower()
    if "douyin.com/message" in url:
        return True

    checks = [
        page.locator("div[contenteditable='true'][data-placeholder]").first,
        page.locator("div[contenteditable='true'][data-slate-editor='true']").first,
        page.get_by_text("发送消息").first,
    ]
    for c in checks:
        try:
            if await c.count() > 0:
                return True
        except Exception:
            continue
    return False


async def _wait_dm_panel_ready(page, timeout_s: float = 8.0) -> bool:
    """
    Semi 面板/输入框是异步渲染的：点击“私信入口”后，给一点重试时间避免误判。
    """
    deadline = time.time() + max(1.0, timeout_s)
    while time.time() < deadline:
        try:
            if await _dm_panel_ready(page):
                return True
        except Exception:
            pass
        await page.wait_for_timeout(500)
    return False


def _append_reply_record(chat_key: str, msg: str) -> None:
    REPLY_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chat_key": chat_key,
        "message": msg,
    }
    with open(REPLY_RECORD_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


async def _send_and_verify(page, msg: str) -> bool:
    editable = page.locator("div[contenteditable='true'][data-placeholder]").first
    if await editable.count() == 0:
        editable = page.locator("div[contenteditable='true'][data-slate-editor='true']").first
    if await editable.count() == 0:
        ph = page.get_by_text("发送消息").first
        if await ph.count():
            root = ph.locator("xpath=ancestor::*[@contenteditable='true'][1]")
            if await root.count():
                editable = root.first

    if await editable.count() == 0:
        await _dump(page, "input_not_found")
        logger.error("[PW] 未找到输入框")
        return False

    try:
        await editable.wait_for(state="visible", timeout=15000)
        await editable.scroll_into_view_if_needed(timeout=5000)
        await editable.click(timeout=5000, force=True)
        await editable.focus(timeout=5000)
        await page.keyboard.type(msg, delay=20)
        await page.keyboard.press("Enter")
    except Exception as e:
        await _dump(page, "send_failed")
        logger.error(f"[PW] 输入/回车发送失败: {e}")
        return False

    try:
        await page.get_by_text(msg).last.wait_for(state="visible", timeout=6000)
        logger.info(f"[PW] 已发送并验证回显成功: {msg!r}")
        return True
    except Exception:
        await _dump(page, "sent_no_echo")
        logger.error("[PW] 已尝试发送，但未验证到消息回显")
        return False


async def _reply_current_chat_if_open(
    page,
    msg: str,
    replied_chat_keys: set[str],
) -> int:
    """
    如果当前已在聊天输入框页面，直接回复当前会话（不依赖左侧未读 badge）。
    返回：本次实际回复 0/1。
    """
    if not await _chat_opened(page):
        return 0
    chat_key = await _current_chat_key(page)
    if chat_key == "__unknown_chat__":
        logger.warning("[PW] 当前会话无法识别到明确聊天对象，跳过发送")
        await _dump(page, "skip_send_unknown_chat_current")
        return 0
    if chat_key in replied_chat_keys:
        logger.info(f"[PW] 当前会话已回复过，跳过：{chat_key}")
        return 0
    if await _send_and_verify(page, msg):
        replied_chat_keys.add(chat_key)
        try:
            _append_reply_record(chat_key=chat_key, msg=msg)
            logger.info(f"[PW] 已记录当前会话回复成功: {REPLY_RECORD_PATH}")
        except Exception:
            pass
        return 1
    return 0


async def _reply_all_unread_in_dm(page, msg: str, replied_chat_keys: set[str], max_replies: int = 30) -> int:
    # max_replies=1 是你的“每个来源只回一条”策略。
    # 在平台半浮层出现但 badge 计数不稳定时，依赖 _count_unread_badges 可能导致直接跳过。
    # 因此：max_replies==1 时直接尝试 _open_first_unread_conversation()，能打开就走发送/回显链路。
    if max_replies == 1:
        ok, chat_key_hint = await _open_first_unread_conversation(page)
        if not ok:
            return 0

        await page.wait_for_timeout(600)

        current_key_for_check = await _current_chat_key(page)
        if chat_key_hint and current_key_for_check and current_key_for_check != "__unknown_chat__":
            if not (chat_key_hint in current_key_for_check or current_key_for_check in chat_key_hint):
                logger.warning(
                    f"[PW] 会话对象不匹配，跳过发送（hint={chat_key_hint!r}, current={current_key_for_check!r}）"
                )
                await _dump(page, "skip_send_chat_mismatch")
                await page.wait_for_timeout(800)
                return 0

        chat_key = chat_key_hint or current_key_for_check or await _current_chat_key(page)
        if chat_key == "__unknown_chat__":
            logger.warning("[PW] 未识别到明确聊天对象，跳过发送，避免点错人")
            await _dump(page, "skip_send_unknown_chat")
            await page.wait_for_timeout(800)
            return 0
        if chat_key in replied_chat_keys:
            logger.info(f"[PW] 会话已在本次运行中回复过，跳过重复发送: {chat_key}")
            await page.wait_for_timeout(800)
            return 0

        if await _send_and_verify(page, msg):
            replied_chat_keys.add(chat_key)
            try:
                _append_reply_record(chat_key=chat_key, msg=msg)
                logger.info(f"[PW] 已记录回复成功: {REPLY_RECORD_PATH}")
            except Exception as e:
                logger.warning(f"[PW] 记录回复成功失败（不影响主流程）: {e}")
            await page.wait_for_timeout(1200)
            return 1

        logger.warning("[PW] 进入会话但发送/回显失败")
        return 0

    # 其它 max_replies 保持原逻辑（依赖 badge 计数）
    replied = 0
    for _ in range(max_replies):
        unread_now = await _count_unread_badges(page)
        if unread_now <= 0:
            break

        logger.info(f"[PW] 当前未读标识数量: {unread_now}，开始回复下一条")
        ok, chat_key_hint = await _open_first_unread_conversation(page)
        if not ok:
            logger.warning("[PW] 未读存在但进入会话失败，停止本轮批量回复")
            break

        await page.wait_for_timeout(600)

        current_key_for_check = await _current_chat_key(page)
        if chat_key_hint and current_key_for_check and current_key_for_check != "__unknown_chat__":
            if not (chat_key_hint in current_key_for_check or current_key_for_check in chat_key_hint):
                logger.warning(
                    f"[PW] 会话对象不匹配，跳过发送（hint={chat_key_hint!r}, current={current_key_for_check!r}）"
                )
                await _dump(page, "skip_send_chat_mismatch")
                await page.wait_for_timeout(800)
                continue

        chat_key = chat_key_hint or current_key_for_check or await _current_chat_key(page)
        if chat_key == "__unknown_chat__":
            logger.warning("[PW] 未识别到明确聊天对象，跳过发送，避免点错人")
            await _dump(page, "skip_send_unknown_chat")
            await page.wait_for_timeout(800)
            continue
        if chat_key in replied_chat_keys:
            logger.info(f"[PW] 会话已在本次运行中回复过，跳过重复发送: {chat_key}")
            await page.wait_for_timeout(800)
            continue

        if await _send_and_verify(page, msg):
            replied_chat_keys.add(chat_key)
            try:
                _append_reply_record(chat_key=chat_key, msg=msg)
                logger.info(f"[PW] 已记录回复成功: {REPLY_RECORD_PATH}")
            except Exception as e:
                logger.warning(f"[PW] 记录回复成功失败（不影响主流程）: {e}")
            replied += 1
        else:
            logger.warning("[PW] 进入会话但发送/回显失败，继续下一条")

        await page.wait_for_timeout(1200)
    return replied


async def _reply_both_dm_sources(page, msg: str, replied_chat_keys: set[str]) -> int:
    """
    私信一体化处理：
    1) 默认私信列表未读
    2) 陌生人列表未读
    """
    total = 0
    # 先在当前停留页签处理，避免误切页签导致离开正确会话区域。
    # 安全起见：每个来源只处理 1 个未读会话，避免误点导致连续发错/发出不想要的内容。
    total += await _reply_all_unread_in_dm(page, msg=msg, replied_chat_keys=replied_chat_keys, max_replies=1)

    if await _switch_to_stranger_tab(page):
        total += await _reply_all_unread_in_dm(page, msg=msg, replied_chat_keys=replied_chat_keys, max_replies=1)
    return total


async def _one_watch_iteration(page, wait_s: float, msg: str, replied_chat_keys: set[str], skip_entry_click: bool = False) -> bool:
    await page.wait_for_timeout(wait_s * 1000)

    if skip_entry_click:
        logger.info("[PW] 跳过私信入口点击，直接处理当前私信界面未读")
        # 关键：skip 模式下仍需激活“未读列表”相关半浮层 DOM。
        try:
            await _prime_dm_panel_hover(page)
        except Exception:
            pass
        # 强约束：未真正进入私信会话页，就不要继续点/发，避免误操作视频流/主页内容。
        # skip 模式复用的是“你手动停留的页面”，其路由/异步渲染可能略慢
        # （尤其是你刚从快捷方式打开后），所以这里给更长一点判定窗口。
        if not await _wait_dm_panel_ready(page, timeout_s=8.0):
            logger.warning("[PW] skip 模式下当前页面未识别为私信会话页，跳过本轮")
            return False
        replied = 0
        # 兜底：如果当前已经打开了某个聊天输入框，先回复当前会话。
        try:
            replied += await _reply_current_chat_if_open(page, msg=msg, replied_chat_keys=replied_chat_keys)
        except Exception as e:
            logger.warning(f"[PW] 当前会话兜底回复失败: {e}")
        # 再继续处理左侧列表的未读（如果列表可见）。
        if replied <= 0:
            replied = await _reply_both_dm_sources(page, msg=msg, replied_chat_keys=replied_chat_keys)
        if replied > 0:
            logger.info(f"[PW] ✅ 本轮已回复 {replied} 个未读会话")
            return True
        return False

    in_message_page = ("douyin.com/message" in (page.url or "")) or (await _dm_panel_ready(page))
    if not in_message_page:
        clicked_dm = await _find_and_click_dm_entry(page)
        if not clicked_dm:
            logger.info("[PW] 本轮未检测到主页未读（红点/数字），继续监听")
            return False
        await page.wait_for_timeout(800)

        # 关键：必须等到真正进入 /message 路由，否则后面计数/切陌生人都会误判。
        def _has_message_url() -> bool:
            return "douyin.com/message" in ((page.url or "").lower())

        deadline = time.time() + 10.0
        while time.time() < deadline:
            try:
                if _has_message_url():
                    break
            except Exception:
                pass
            await page.wait_for_timeout(500)

        if not _has_message_url():
            # 兜底：再次对导航栏的 /message 做一次定点点击，部分情况下初次点击不会触发路由切换
            logger.warning("[PW] 点击私信入口后仍未进入 /message 路由，尝试兜底定点点击后重试")
            try:
                clicked = await page.evaluate(
                    """
                    () => {
                      const nav = document.querySelector('#douyin-navigation');
                      if (!nav) return false;
                      const a = nav.querySelector("a[href*='/message'], a[href*='//www.douyin.com/message']");
                      if (!a) return false;
                      a.click();
                      return true;
                    }
                    """
                )
                if clicked:
                    await page.wait_for_timeout(1200)
                    deadline2 = time.time() + 10.0
                    while time.time() < deadline2:
                        if _has_message_url():
                            break
                        await page.wait_for_timeout(500)
            except Exception as e:
                logger.warning(f"[PW] /message 兜底点击失败: {e}")

        if not _has_message_url():
            logger.warning("[PW] 点击私信入口后仍未进入 /message 路由，停止本轮重试")
            try:
                await _dump(page, "dm_entry_message_route_failed")
            except Exception:
                pass
            # 不 return：半浮层可能已经就绪，只是 URL 没切换到 /message。

        if not await _wait_dm_panel_ready(page, timeout_s=8.0):
            logger.warning("[PW] 点击私信入口后未明确识别到会话页（判定不稳定），仍继续本轮尝试回复")
    else:
        logger.info("[PW] 当前已在私信会话界面，本轮不重复点击私信入口")
    replied = await _reply_both_dm_sources(page, msg=msg, replied_chat_keys=replied_chat_keys)
    if replied > 0:
        logger.info(f"[PW] ✅ 本轮已回复 {replied} 个未读会话")
        return True
    return False


async def main() -> int:
    global NO_MOUSE_ACTIONS
    parser = argparse.ArgumentParser(description="Douyin DM auto reply watcher (Playwright).")
    parser.add_argument("--wait-seconds", type=float, default=float(os.environ.get("DOUYIN_TEST_WAIT_SECONDS", "4")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("DOUYIN_POLL_SECONDS", "5")))
    parser.add_argument("--max-minutes", type=float, default=float(os.environ.get("DOUYIN_MAX_MINUTES", "60")))
    parser.add_argument("--idle-close-seconds", type=float, default=float(os.environ.get("DOUYIN_IDLE_CLOSE_SECONDS", "10")))
    parser.add_argument("--message", type=str, default=os.environ.get("DOUYIN_TEST_MESSAGE", "测试消息"))
    parser.add_argument("--keep-browser", action="store_true", default=(os.environ.get("DOUYIN_TEST_KEEP_BROWSER", "0") == "1"))
    parser.add_argument("--skip-entry-click", action="store_true", default=(os.environ.get("DOUYIN_SKIP_ENTRY_CLICK", "0") == "1"))
    parser.add_argument("--no-mouse-actions", action="store_true", default=(os.environ.get("DOUYIN_NO_MOUSE_ACTIONS", "0") == "1"))
    args = parser.parse_args()

    _setup_logging()

    wait_s = max(3.0, min(5.0, float(args.wait_seconds)))
    poll_s = max(2.0, float(args.poll_seconds))
    max_minutes = max(1.0, float(args.max_minutes))
    idle_close_s = max(5.0, float(args.idle_close_seconds))
    msg = args.message
    keep = bool(args.keep_browser)
    skip_entry_click = bool(args.skip_entry_click)
    NO_MOUSE_ACTIONS = bool(args.no_mouse_actions)
    # 跳过入口点击是为了不“切走页面”，但一旦复用失败必须兜底到正常导航。
    skip_entry_click_effective = skip_entry_click

    try:
        if skip_entry_click_effective:
            # 复用你手动停留的页面（不做 goto），避免把私信页切走。
            try:
                page = await _reuse_existing_page()
            except Exception as e:
                logger.warning(f"[PW] skip-entry-click 复用失败，改为正常导航恢复: {e}")
                skip_entry_click_effective = False
                page = await browser_manager.open_login_page(DOUYIN_HOME_URL)
                try:
                    await page.bring_to_front()
                except Exception:
                    pass
        else:
            page = await browser_manager.open_login_page(DOUYIN_HOME_URL)
            await page.bring_to_front()
            # 强制回到抖音主页，避免停留在素材/创作者页面导致流程跑偏。
            try:
                if not (page.url or "").startswith("https://www.douyin.com/"):
                    await page.goto(DOUYIN_HOME_URL, wait_until="domcontentloaded", timeout=90000)
                    await page.wait_for_timeout(1200)
                    logger.info("[PW] 已强制回到抖音主页")
            except Exception as e:
                logger.warning(f"[PW] 回到抖音主页失败（继续）: {e}")

        logger.info(f"[PW] 开始监听未读私信：轮询间隔={poll_s:.1f}s，最长={max_minutes:.1f}min")
        logger.info(f"[PW] 空闲关闭阈值: {idle_close_s:.1f}s（主页连续无未读则退出）")
        logger.info(f"[PW] 单轮等待: {wait_s:.1f}s")
        logger.info(f"[PW] 回复内容: {msg!r}")

        deadline = time.time() + max_minutes * 60
        last_unread_ts = time.time()
        replied_chat_keys: set[str] = set()
        round_idx = 0
        while time.time() < deadline:
            round_idx += 1
            logger.info(f"[PW] ---------- 轮询 #{round_idx} ----------")
            try:
                if page.is_closed():
                    logger.warning("[PW] 检测到页面已关闭，自动重新打开抖音页继续监听")
                    if skip_entry_click_effective:
                        try:
                            page = await _reuse_existing_page()
                        except Exception as e:
                            logger.warning(f"[PW] 复用私信页失败，改为正常导航恢复: {e}")
                            skip_entry_click_effective = False
                            page = await browser_manager.open_login_page(DOUYIN_HOME_URL)
                            try:
                                await page.bring_to_front()
                            except Exception:
                                pass
                    else:
                        page = await browser_manager.open_login_page(DOUYIN_HOME_URL)
                    try:
                        await page.bring_to_front()
                    except Exception:
                        pass
                ok = await _one_watch_iteration(
                    page,
                    wait_s=wait_s,
                    msg=msg,
                    replied_chat_keys=replied_chat_keys,
                    skip_entry_click=skip_entry_click_effective,
                )
                if ok:
                    last_unread_ts = time.time()
            except Exception as e:
                logger.warning(f"[PW] 本轮异常: {e}")
                try:
                    await _dump(page, f"watch_iteration_error_{round_idx}")
                except Exception:
                    pass

            if time.time() - last_unread_ts >= idle_close_s:
                logger.info("[PW] 主页已连续无未读超过阈值，自动关闭并退出")
                return 0

            try:
                await page.wait_for_timeout(poll_s * 1000)
            except Exception as e:
                logger.warning(f"[PW] 轮询等待失败，尝试恢复页面: {e}")
                if skip_entry_click_effective:
                    try:
                        page = await _reuse_existing_page()
                    except Exception as e2:
                        logger.warning(f"[PW] 复用私信页失败，改为正常导航恢复: {e2}")
                        skip_entry_click_effective = False
                        page = await browser_manager.open_login_page(DOUYIN_HOME_URL)
                        try:
                            await page.bring_to_front()
                        except Exception:
                            pass
                else:
                    page = await browser_manager.open_login_page(DOUYIN_HOME_URL)
                try:
                    await page.bring_to_front()
                except Exception:
                    pass

        logger.error("[PW] 超时退出：未在最大监听时间内完成回复")
        return 5
    finally:
        if not keep:
            try:
                await browser_manager.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))





