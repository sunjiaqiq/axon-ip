"""
兼容入口（已改名）：

该脚本已更名为：`pixelle_wrapper/自动回复脚本.py`
请后续在系统内接入新文件名。
"""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> int:
    target = Path(__file__).resolve().parent / "自动回复脚本.py"
    # 直接执行新脚本的 __main__，让命令行参数保持一致
    runpy.run_path(str(target), run_name="__main__")
    return 0


def _clamp_wait() -> float:
    s = float(os.environ.get("DOUYIN_TEST_WAIT_SECONDS", "4"))
    return max(3.0, min(5.0, s))


def _debug_dir() -> Path:
    p = THIS_DIR / "debug_artifacts_pw"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _setup_logging() -> Path:
    """
    同时输出到控制台 + 文件，方便你后台随时监控日志。
    """
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
        (str(base) + ".html")
        with open(str(base) + ".html", "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"[PW][Debug] HTML: {base}.html")
    except Exception as e:
        logger.warning(f"[PW][Debug] HTML保存失败: {e}")


async def _find_and_click_dm_entry(page) -> bool:
    """
    主页私信入口：优先找红点/数字 badge，再向上找可点击祖先。
    """
    # 常见 badge class
    badge = page.locator("span.semi-badge-count").first
    if await badge.count() == 0:
        badge = page.locator("span[class*='semi-badge-count']").first

    if await badge.count() == 0:
        return False

    try:
        await badge.wait_for(state="visible", timeout=5000)
    except Exception:
        return False

    # 从 badge 往上找可点祖先：a/button/[role=button]/可点击div
    candidates = [
        badge.locator("xpath=ancestor::a[1]"),
        badge.locator("xpath=ancestor::button[1]"),
        badge.locator("xpath=ancestor::*[@role='button'][1]"),
        badge.locator("xpath=ancestor::div[1]"),
        badge,
    ]
    for i, c in enumerate(candidates):
        try:
            if await c.count() == 0:
                continue
            target = c.first
            await target.scroll_into_view_if_needed(timeout=2000)
            await target.click(timeout=3000, force=True)
            logger.info(f"[PW] 已点击主页私信入口候选 #{i+1}")
            return True
        except Exception as e:
            logger.info(f"[PW] 点击主页私信入口候选 #{i+1} 失败: {e}")
            continue
    return False


async def _chat_opened(page) -> bool:
    # 输入框常见：contenteditable（抖音新版是 slate editor，带 data-placeholder="发送消息"）
    editable = page.locator("div[contenteditable='true'][data-placeholder]")
    if await editable.count():
        try:
            await editable.first.wait_for(state="visible", timeout=1500)
            return True
        except Exception:
            pass

    editable = page.locator("div[contenteditable='true'][data-slate-editor='true']")
    if await editable.count():
        try:
            await editable.first.wait_for(state="visible", timeout=1500)
            return True
        except Exception:
            pass

    # 占位文本兜底
    placeholder = page.get_by_text("发送消息")
    try:
        await placeholder.first.wait_for(state="visible", timeout=800)
        return True
    except Exception:
        return False


async def _open_first_unread_conversation(page) -> bool:
    """
    私信列表：找未读 badge，逐个尝试点击其祖先，直到聊天输入框出现。
    """
    # 未读标识可能是数字（semi-badge-count）也可能是小红点（semi-badge-dot）
    badges = page.locator("[x-semi-prop='count']")
    if await badges.count() == 0:
        badges = page.locator("span.semi-badge-dot, span[class*='semi-badge-dot']")
    if await badges.count() == 0:
        badges = page.locator("span.semi-badge-count, span[class*='semi-badge-count']")

    n = await badges.count()
    if n == 0:
        logger.info("[PW] 未检测到会话未读 badge，退出")
        return False

    logger.info(f"[PW] 检测到未读 badge 数量: {n}，开始逐个尝试点击进入会话")
    for idx in range(min(n, 10)):  # 防止无限点
        b = badges.nth(idx)
        try:
            await b.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

        # 由里向外逐层找可点祖先
        anc_list = [
            b.locator("xpath=ancestor::a[1]"),
            b.locator("xpath=ancestor::*[@role='link'][1]"),
            b.locator("xpath=ancestor::*[@role='button'][1]"),
            b.locator("xpath=ancestor::div[contains(@class,'conversation')][1]"),
            b.locator("xpath=ancestor::div[1]"),
            b,
        ]
        for j, anc in enumerate(anc_list):
            try:
                if await anc.count() == 0:
                    continue
                t = anc.first
                await t.scroll_into_view_if_needed(timeout=2000)
                await t.click(timeout=2500, force=True)
                await page.wait_for_timeout(600)
                if await _chat_opened(page):
                    logger.info(f"[PW] 已进入聊天面板（badge#{idx+1} / anc#{j+1}）")
                    return True
            except Exception:
                continue

    await _dump(page, "open_unread_conversation_failed")
    logger.error("[PW] 未能进入聊天面板（尝试点击未读会话失败）")
    return False


async def _send_and_verify(page, msg: str) -> bool:
    # 找输入框
    editable = page.locator("div[contenteditable='true'][data-placeholder]").first
    if await editable.count() == 0:
        editable = page.locator("div[contenteditable='true'][data-slate-editor='true']").first
    if await editable.count() == 0:
        # 通过“发送消息”占位文本向上找
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
        # contenteditable 容易被遮挡/点击不生效，先强制点击，再用键盘输入更稳
        await editable.click(timeout=5000, force=True)
        await editable.focus(timeout=5000)
        await page.keyboard.type(msg, delay=20)
        await page.keyboard.press("Enter")
    except Exception as e:
        await _dump(page, "send_failed")
        logger.error(f"[PW] 输入/回车发送失败: {e}")
        return False

    # 验证回显：聊天区域出现该文本
    try:
        await page.get_by_text(msg).last.wait_for(state="visible", timeout=6000)
        logger.info(f"[PW] 已发送并验证回显成功: {msg!r}")
        return True
    except Exception:
        await _dump(page, "sent_no_echo")
        logger.error("[PW] 已尝试发送，但未验证到消息回显")
        return False


async def _count_unread_badges(page) -> int:
    """
    统计当前页面上的未读标识数量（dot/count 都算）。
    """
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


async def _reply_all_unread_in_dm(page, msg: str, max_replies: int = 30) -> int:
    """
    在私信界面尽可能把未读挨个回复完。
    返回：本次实际回复的会话数量。
    """
    replied = 0
    for _ in range(max_replies):
        unread_now = await _count_unread_badges(page)
        if unread_now <= 0:
            break

        logger.info(f"[PW] 当前未读标识数量: {unread_now}，开始回复下一条")

        # 点开一条未读会话（多策略）
        if not await _open_first_unread_conversation(page):
            logger.warning("[PW] 未读存在但进入会话失败，停止本轮批量回复（已落盘 debug_artifacts_pw）")
            break

        await page.wait_for_timeout(600)

        # 回复并验证
        if await _send_and_verify(page, msg):
            replied += 1
        else:
            logger.warning("[PW] 进入会话但发送/回显失败（已落盘 debug_artifacts_pw），继续尝试下一条未读")

        # 给 UI 一点时间刷新未读标记
        await page.wait_for_timeout(1200)

    return replied


async def _one_watch_iteration(page, wait_s: float, msg: str) -> bool:
    """
    单次轮询：
    - 回到抖音首页（或刷新）
    - 等待 3~5 秒
    - 若有未读入口则进入私信、点未读会话、发送并校验回显
    """
    try:
        if not page.url.startswith("https://www.douyin.com"):
            await page.goto(DOUYIN_HOME_URL, wait_until="domcontentloaded", timeout=90000)
        else:
            await page.reload(wait_until="domcontentloaded", timeout=90000)
    except Exception as e:
        logger.warning(f"[PW] 刷新/回到主页失败（继续本轮）: {e}")

    await page.wait_for_timeout(wait_s * 1000)

    clicked_dm = await _find_and_click_dm_entry(page)
    if not clicked_dm:
        logger.info("[PW] 本轮未检测到主页未读（红点/数字），继续监听")
        return False

    await page.wait_for_timeout(1200)

    # 批量清空未读：挨个回复，直到没有未读
    replied = await _reply_all_unread_in_dm(page, msg=msg, max_replies=30)
    if replied > 0:
        logger.info(f"[PW] ✅ 本轮已回复 {replied} 个未读会话")
        return True

    logger.warning("[PW] 进入私信了但未能完成任何一次“发送并验证回显”的回复（继续下一轮）")
    return False


async def main() -> int:
    parser = argparse.ArgumentParser(description="Douyin DM unread watcher (Playwright).")
    parser.add_argument("--wait-seconds", type=float, default=float(os.environ.get("DOUYIN_TEST_WAIT_SECONDS", "4")))
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("DOUYIN_POLL_SECONDS", "5")))
    parser.add_argument("--max-minutes", type=float, default=float(os.environ.get("DOUYIN_MAX_MINUTES", "60")))
    parser.add_argument("--idle-close-seconds", type=float, default=float(os.environ.get("DOUYIN_IDLE_CLOSE_SECONDS", "10")))
    parser.add_argument("--message", type=str, default=os.environ.get("DOUYIN_TEST_MESSAGE", "测试消息"))
    parser.add_argument("--keep-browser", action="store_true", default=(os.environ.get("DOUYIN_TEST_KEEP_BROWSER", "0") == "1"))
    args = parser.parse_args()

    _setup_logging()
    wait_s = max(3.0, min(5.0, float(args.wait_seconds)))
    poll_s = max(2.0, float(args.poll_seconds))
    max_minutes = max(1.0, float(args.max_minutes))
    idle_close_s = max(5.0, float(args.idle_close_seconds))
    msg = args.message
    keep = bool(args.keep_browser)

    try:
        page = await browser_manager.open_login_page(DOUYIN_HOME_URL)
        await page.bring_to_front()

        logger.info(f"[PW] 开始监听未读私信：轮询间隔={poll_s:.1f}s，最长={max_minutes:.1f}min")
        logger.info(f"[PW] 空闲关闭阈值: {idle_close_s:.1f}s（主页连续无红点/未读则退出）")
        logger.info(f"[PW] 单轮等待（主页加载后等待）: {wait_s:.1f}s")
        logger.info(f"[PW] 回复内容: {msg!r}")

        deadline = time.time() + max_minutes * 60
        round_idx = 0
        last_unread_ts = time.time()
        while time.time() < deadline:
            round_idx += 1
            logger.info(f"[PW] ---------- 轮询 #{round_idx} ----------")
            try:
                ok = await _one_watch_iteration(page, wait_s=wait_s, msg=msg)
                if ok:
                    last_unread_ts = time.time()
            except Exception as e:
                logger.warning(f"[PW] 本轮异常: {e}")
                try:
                    await _dump(page, f"watch_iteration_error_{round_idx}")
                except Exception:
                    pass

            # 如果持续空闲（没有红点/未读）超过阈值，就自动关闭退出
            if time.time() - last_unread_ts >= idle_close_s:
                logger.info("[PW] 主页已连续无未读超过阈值，自动关闭并退出")
                return 0
            await page.wait_for_timeout(poll_s * 1000)

        logger.error("[PW] 超时：在最大监听时间内未完成“收到未读并回复成功”的闭环")
        return 5
    finally:
        # 不关闭浏览器可能会导致 asyncio 子进程清理时报警；默认关闭以保持日志干净
        if not keep:
            try:
                await browser_manager.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())


