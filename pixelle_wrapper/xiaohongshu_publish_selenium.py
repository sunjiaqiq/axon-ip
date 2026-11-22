# -*- coding: utf-8 -*-
"""
小红书创作者中心 — 视频发布（Selenium）

与抖音发布共用同一套浏览器：`douyin_publish_mcp.ensure_browser()`（Profile 3 + browser_data）。

步骤间隔：流程中每一步之间随机等待 5～15 秒（含发布后等待成功检测前的一段）。

元素依据桌面抓取的创作者中心结构；视频不经「上传视频」按钮，直接向 input[type=file] 传路径，再填标题、正文、点发布。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import douyin_publish_mcp as dpm

logger = logging.getLogger(__name__)

PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?from=menu"


def _setup_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="[%(levelname)s] [XHS] %(message)s",
        )


def step_gap(*, reason: str = "") -> float:
    """流程中相邻步骤之间的 5～15 秒随机停顿。"""
    return dpm.human_sleep(5.0, 15.0, reason=reason or "小红书发布步骤间隔")


def _output_roots() -> List[Path]:
    base = Path(__file__).resolve().parent
    roots: List[Path] = []
    for name in ("output", "outputs"):
        p = base / name
        if p.is_dir():
            roots.append(p)
    return roots


def find_latest_video_and_copy() -> Tuple[Optional[str], str, str]:
    """
    在 pixelle_wrapper/output(s) 下找最新 mp4；
    同目录尝试读取 xhs_publish_meta.json / publish_meta.json / content.json 中的 title、description。
    """
    best: Optional[Tuple[float, Path]] = None
    for root in _output_roots():
        try:
            for mp4 in root.rglob("*.mp4"):
                try:
                    m = mp4.stat().st_mtime
                except OSError:
                    continue
                if best is None or m > best[0]:
                    best = (m, mp4)
        except OSError:
            continue
    if not best:
        return None, "", ""
    video_path = best[1]
    folder = video_path.parent
    title, description = "", ""
    for jname in ("xhs_publish_meta.json", "publish_meta.json", "content.json"):
        jf = folder / jname
        if not jf.is_file():
            continue
        try:
            data: Dict[str, Any] = json.loads(jf.read_text(encoding="utf-8"))
            title = str(data.get("title") or "").strip()
            description = str(
                data.get("description") or data.get("desc") or ""
            ).strip()
            if title or description:
                break
        except Exception:
            continue
    if not title:
        stem = video_path.stem
        title = (stem[:20] if stem else "作品分享") or "作品分享"
    if not description:
        description = "记录生活，分享美好瞬间。"
    return str(video_path.resolve()), title, description


def _wait_video_upload_done(driver, timeout: float = 240.0) -> None:
    """上传后轮询：成功文案 / 视频信息 / 标题框可点，任一满足即继续。"""
    end = time.time() + timeout
    while time.time() < end:
        dpm._dismiss_shepherd_if_present(driver)
        try:
            for xp in (
                "//*[contains(text(),'上传成功') or contains(text(),'上传完成')]",
                "//*[contains(text(),'视频时长') or contains(text(),'视频大小')]",
            ):
                for e in driver.find_elements(By.XPATH, xp):
                    try:
                        if e.is_displayed():
                            logger.info("检测到上传阶段完成/视频信息: %s", (e.text or "")[:40])
                            return
                    except Exception:
                        continue
        except Exception:
            pass
        try:
            for sel in (
                "input[placeholder*='填写标题']",
                "input.d-text[placeholder*='填写标题']",
            ):
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for inp in els:
                    try:
                        if inp.is_displayed() and inp.is_enabled():
                            logger.info("标题框已可用，视为可继续填写")
                            return
                    except Exception:
                        continue
        except Exception:
            pass
        time.sleep(2.5)
    logger.warning("未在超时内明确检测到上传结束，仍尝试填写标题与正文")


def _switch_to_video_tab_if_present(driver) -> bool:
    """
    点击顶部/区域「上传视频」选项卡（.creator-tab），不是「上传视频」按钮。
    用于挂载视频上传区里的 file input；不会弹出系统文件框。
    """
    try:
        tabs = driver.find_elements(By.CSS_SELECTOR, ".creator-tab")
        if not tabs:
            tabs = driver.find_elements(
                By.XPATH,
                "//*[contains(@class,'tab')]"
                "[contains(normalize-space(),'上传视频')]"
                "[not(contains(normalize-space(),'上传图文'))]",
            )
        for tab in tabs:
            try:
                if not tab.is_displayed():
                    continue
                txt = (tab.text or "").strip().replace(" ", "")
                if "上传视频" in txt and "上传图文" not in txt:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", tab
                    )
                    try:
                        tab.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", tab)
                    logger.info("已切换到「上传视频」选项卡")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _find_video_file_input(driver):
    """优先选接受视频的 file input；否则第一个 file input。"""
    best = None
    for el in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
        try:
            accept = (el.get_attribute("accept") or "").lower()
            if "video" in accept or accept == "" or "*" in accept:
                return el
            if best is None:
                best = el
        except Exception:
            continue
    return best


def _wait_xhs_publish_success(driver, timeout: float = 120.0) -> bool:
    """
    点击发布后轮询页面：出现成功/审核/已提交等文案即视为可关浏览器。
    """
    markers = (
        "发布成功",
        "发布完成",
        "笔记发布",
        "提交成功",
        "已提交",
        "审核中",
        "审核通过",
        "处理中",
        "已成功",
        "前往笔记",
        "笔记已发布",
    )
    end = time.time() + timeout
    while time.time() < end:
        dpm._dismiss_shepherd_if_present(driver)
        try:
            body = (driver.find_element(By.TAG_NAME, "body").text or "")[:8000]
            for m in markers:
                if m in body:
                    logger.info("检测到发布结果提示: %s", m)
                    return True
        except Exception:
            pass
        time.sleep(2.0)
    return False


def _close_shared_browser() -> None:
    """关闭与抖音共用的全局 Chrome，并重置 douyin_publish_mcp.driver。"""
    try:
        if dpm.driver:
            dpm.driver.quit()
            logger.info("已关闭浏览器（发布流程结束）")
    except Exception as e:
        logger.warning("关闭浏览器时异常（可忽略）: %s", e)
    dpm.driver = None


def _try_sidebar_publish_note(driver) -> None:
    """侧栏「发布笔记」：仅用于进入发布流；已带 publish 的 URL 上可能不必点。"""
    try:
        spans = driver.find_elements(
            By.XPATH,
            "//span[contains(@class,'btn-text')][contains(normalize-space(),'发布笔记')]",
        )
        for sp in spans:
            if sp.is_displayed():
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", sp
                    )
                    sp.click()
                    logger.info("已点击侧栏「发布笔记」")
                    return
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", sp)
                        logger.info("已点击侧栏「发布笔记」(JS)")
                        return
                    except Exception:
                        continue
    except Exception:
        pass


def publish_xiaohongshu_video(
    video_path: str,
    title: str,
    description: str,
) -> bool:
    _setup_logging()
    video_path = str(Path(video_path).resolve())
    if not os.path.isfile(video_path):
        logger.error("视频文件不存在: %s", video_path)
        return False

    if not dpm.ensure_browser():
        logger.error("浏览器未就绪（请关闭冲突 Chrome 或按抖音发布说明处理）")
        return False

    driver = dpm.driver
    wait = WebDriverWait(driver, 35)

    try:
        step_gap(reason="启动后缓冲")
        logger.info("打开发布页: %s", PUBLISH_URL)
        driver.get(PUBLISH_URL)
        step_gap(reason="发布页加载后")

        dpm._dismiss_shepherd_if_present(driver)
        step_gap(reason="关闭引导/遮罩后")

        # 先切到「上传视频」选项卡，否则常常没有 file input（不点「上传视频」按钮，不弹系统文件框）
        _switch_to_video_tab_if_present(driver)
        step_gap(reason="切换上传视频选项卡后")

        # 仍无 file input 时再尝试侧栏「发布笔记」
        if not driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
            logger.info("当前页无 file input，尝试侧栏「发布笔记」")
            _try_sidebar_publish_note(driver)
            step_gap(reason="点击发布笔记后")
            _switch_to_video_tab_if_present(driver)
            step_gap(reason="发布笔记后再次切换上传视频选项卡")

        # 不点击「上传视频」按钮；直接向隐藏 input[type=file] 传入绝对路径
        try:
            WebDriverWait(driver, 45).until(
                lambda d: _find_video_file_input(d) is not None
            )
        except Exception:
            logger.warning("等待 file input 超时，仍尝试查找")

        file_in = _find_video_file_input(driver)
        if not file_in:
            logger.error("未找到文件上传 input（请确认已登录且当前为视频发布页）")
            try:
                driver.save_screenshot(
                    str(Path(__file__).parent / "xhs_no_file_input.png")
                )
            except Exception:
                pass
            return False

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", file_in
            )
        except Exception:
            pass
        step_gap(reason="准备传入视频路径前")
        file_in.send_keys(video_path)
        logger.info("已向 file input 直接传入视频路径（未点「上传视频」）")
        step_gap(reason="开始上传视频后")

        _wait_video_upload_done(driver)
        step_gap(reason="上传处理后的间隔")

        dpm._dismiss_shepherd_if_present(driver)
        step_gap(reason="填写标题前")

        # 标题：input.d-text placeholder 填写标题会有更多赞哦
        title_el = None
        for sel in (
            "input.d-text[placeholder*='填写标题']",
            "input[placeholder*='填写标题']",
            "input.d-text[type='text']",
        ):
            try:
                title_el = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                if title_el.is_displayed():
                    logger.info("定位标题: %s", sel)
                    break
            except Exception:
                title_el = None
        if not title_el:
            logger.error("未找到标题输入框")
            return False

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", title_el
        )
        try:
            title_el.click()
        except Exception:
            pass
        try:
            title_el.clear()
        except Exception:
            title_el.send_keys(Keys.CONTROL, "a")
            title_el.send_keys(Keys.BACKSPACE)
        title_text = (title or "")[:50]
        title_el.send_keys(title_text)
        logger.info("已填写标题: %s", title_text)
        step_gap(reason="填写标题后")

        # 描述：p[data-placeholder*='输入正文描述']（ProseMirror）
        desc_el = None
        try:
            desc_el = wait.until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "p[data-placeholder*='输入正文描述']",
                    )
                )
            )
        except Exception:
            try:
                desc_el = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "p[data-placeholder*='正文']")
                    )
                )
            except Exception as e:
                logger.error("未找到正文描述编辑区: %s", e)
                return False

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", desc_el
        )
        try:
            desc_el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", desc_el)
        try:
            desc_el.send_keys(Keys.CONTROL, "a")
            desc_el.send_keys(Keys.BACKSPACE)
        except Exception:
            pass
        desc_text = description or ""
        lines = desc_text.split("\n")
        for i, line in enumerate(lines):
            desc_el.send_keys(line)
            if i < len(lines) - 1:
                desc_el.send_keys(Keys.ENTER)
        logger.info("已填写正文描述（长度 %d）", len(desc_text))
        step_gap(reason="填写描述后")

        dpm._dismiss_shepherd_if_present(driver)
        step_gap(reason="查找发布按钮前")

        # 最终「发布」：文案精确为「发布」的按钮，等待可点击（上传未完成时常 disabled）
        publish_btn = None
        try:
            publish_btn = WebDriverWait(driver, 120).until(
                lambda d: next(
                    (
                        b
                        for b in d.find_elements(
                            By.XPATH,
                            "//button[contains(@class,'d-button')]"
                            "[.//span[contains(@class,'d-text')]"
                            "[normalize-space()='发布']]",
                        )
                        if b.is_displayed()
                        and b.is_enabled()
                        and "发布笔记" not in (b.text or "")
                    ),
                    None,
                )
            )
        except Exception:
            publish_btn = None
        if not publish_btn:
            candidates = driver.find_elements(
                By.XPATH,
                "//button[.//span[contains(@class,'d-text')][normalize-space()='发布']]",
            )
            for b in candidates:
                try:
                    if (
                        b.is_displayed()
                        and b.is_enabled()
                        and "发布笔记" not in (b.text or "")
                    ):
                        publish_btn = b
                        break
                except Exception:
                    continue
        if not publish_btn:
            logger.error("未找到可点击的最终「发布」按钮（可能仍在上传中）")
            try:
                driver.save_screenshot(
                    str(Path(__file__).parent / "xhs_no_publish_btn.png")
                )
            except Exception:
                pass
            return False

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", publish_btn
        )
        step_gap(reason="点击发布按钮前")
        try:
            publish_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", publish_btn)
        logger.info("已点击「发布」，等待页面出现「发布成功」等提示…")
        step_gap(reason="发布后等待服务端响应")

        if _wait_xhs_publish_success(driver, timeout=120.0):
            _close_shared_browser()
        else:
            logger.warning(
                "120s 内未检测到明确成功文案，浏览器保持打开，请人工确认是否已发布"
            )

        return True
    except Exception as e:
        logger.exception("小红书发布异常: %s", e)
        try:
            driver.save_screenshot(str(Path(__file__).parent / "xhs_publish_error.png"))
        except Exception:
            pass
        return False


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="小红书 Selenium 发布测试")
    parser.add_argument("--video", default="", help="视频绝对或相对路径")
    parser.add_argument("--title", default="", help="标题")
    parser.add_argument("--description", default="", help="正文描述")
    args = parser.parse_args()

    v, t, d = args.video.strip(), args.title.strip(), args.description.strip()
    if not v:
        v, t2, d2 = find_latest_video_and_copy()
        t = t or t2
        d = d or d2
    if not v:
        logger.error("未找到视频：请指定 --video 或先在 output 目录生成 mp4")
        return 1

    ok = publish_xiaohongshu_video(v, t, d)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
