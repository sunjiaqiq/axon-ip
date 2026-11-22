# -*- coding: utf-8 -*-
"""
快手创作者平台 — 视频发布（Selenium）

与抖音 / 小红书共用：`douyin_publish_mcp.ensure_browser()`（Profile 3 + browser_data）。

步骤间隔：主要 UI 步骤之间用 step_gap（随机 5～15 秒，经 dpm.human_sleep）；
上传/发布结果轮询内为固定短 sleep；多行描述在每次换行后用较短随机停顿（0.4～1.5s）。

页面依据桌面抓取：
- 发布页: cp.kuaishou.com 视频发布
- 作品描述: #work-description-edit（contenteditable）
- 底部主按钮「发布」（含 _button-primary_ 类名的容器 + 内层 div 文案「发布」）

视频：优先直接向 input[type=file] 传绝对路径，避免点「上传」弹系统文件框。
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

PUBLISH_URL = (
    "https://cp.kuaishou.com/article/publish/video"
    "?origin=www.kuaishou.com&source=NewReco"
)


def _setup_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="[%(levelname)s] [KS] %(message)s",
        )


def step_gap(*, reason: str = "") -> float:
    return dpm.human_sleep(5.0, 15.0, reason=reason or "快手发布步骤间隔")


def _output_roots() -> List[Path]:
    base = Path(__file__).resolve().parent
    roots: List[Path] = []
    for name in ("output", "outputs"):
        p = base / name
        if p.is_dir():
            roots.append(p)
    return roots


def find_latest_video_and_meta() -> Tuple[Optional[str], str, str]:
    """与小红书脚本一致：最新 mp4 + 同目录 json 中的 title/description。"""
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
    for jname in ("publish_meta.json", "content.json", "xhs_publish_meta.json"):
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
        title = (stem[:30] if stem else "作品分享") or "作品分享"
    if not description:
        description = "记录生活，分享美好瞬间。"
    return str(video_path.resolve()), title, description


def _find_video_file_input(driver):
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


def _wait_kuaishou_upload_done(driver, timeout: float = 240.0) -> None:
    """等到作品描述区可用或页面出现上传完成类提示。"""
    end = time.time() + timeout
    while time.time() < end:
        dpm._dismiss_shepherd_if_present(driver)
        try:
            for xp in (
                "//*[contains(text(),'上传成功')]",
                "//*[contains(text(),'上传完成')]",
                "//*[contains(text(),'转码')]",
            ):
                for e in driver.find_elements(By.XPATH, xp):
                    try:
                        if e.is_displayed():
                            logger.info("检测到上传相关提示: %s", (e.text or "")[:50])
                            return
                    except Exception:
                        continue
        except Exception:
            pass
        try:
            el = driver.find_element(By.CSS_SELECTOR, "#work-description-edit")
            if el.is_displayed():
                logger.info("作品描述区已出现，视为上传阶段可继续")
                return
        except Exception:
            pass
        time.sleep(2.5)
    logger.warning("未在超时内确认上传结束，仍尝试填写描述")


def _wait_kuaishou_publish_success(driver, timeout: float = 120.0) -> bool:
    markers = (
        "发布成功",
        "发布完成",
        "提交成功",
        "已发布",
        "审核中",
        "作品已发布",
        "已成功",
    )
    end = time.time() + timeout
    while time.time() < end:
        dpm._dismiss_shepherd_if_present(driver)
        try:
            body = (driver.find_element(By.TAG_NAME, "body").text or "")[:8000]
            for m in markers:
                if m in body:
                    logger.info("检测到快手发布结果提示: %s", m)
                    return True
        except Exception:
            pass
        time.sleep(2.0)
    return False


def _close_shared_browser() -> None:
    try:
        if dpm.driver:
            dpm.driver.quit()
            logger.info("已关闭浏览器（快手发布流程结束）")
    except Exception as e:
        logger.warning("关闭浏览器: %s", e)
    dpm.driver = None


def _find_kuaishou_publish_control(driver):
    """
    抓取结构：外层含 _button-primary_，内层 div 文案为「发布」。
    兼容类名哈希变化：用 contains(@class,'button-primary') 与文案。
    """
    xpaths = (
        "//*[contains(@class,'_button-primary_')][.//div[normalize-space()='发布']]",
        "//*[contains(@class,'button-primary')][.//*[normalize-space()='发布']]",
        "//div[normalize-space()='发布'][ancestor::*[contains(@class,'button')]]",
    )
    for xp in xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    continue
        except Exception:
            continue
    # 兜底：任意可见且文字仅为「发布」的按钮状元素
    try:
        for el in driver.find_elements(By.XPATH, "//*[normalize-space()='发布']"):
            try:
                if not el.is_displayed():
                    continue
                tag = (el.tag_name or "").lower()
                if tag in ("button", "div", "span"):
                    parent = el
                    if tag != "button":
                        try:
                            parent = el.find_element(By.XPATH, "./ancestor::button[1]")
                        except Exception:
                            parent = el.find_element(
                                By.XPATH, "./ancestor::div[contains(@class,'button')][1]"
                            )
                    if parent.is_displayed() and parent.is_enabled():
                        return parent
            except Exception:
                continue
    except Exception:
        pass
    return None


def publish_kuaishou_video(
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
        logger.error("浏览器未就绪")
        return False

    driver = dpm.driver
    wait = WebDriverWait(driver, 40)

    # 快手发布页无独立「标题」输入框，仅作品描述一处可编辑；title 参数保留兼容接口，不写入页面。
    def _compose_work_text() -> str:
        d = (description or "").strip()
        if d:
            return d
        return "分享作品"

    try:
        step_gap(reason="启动后缓冲")
        logger.info("打开快手发布页: %s", PUBLISH_URL)
        driver.get(PUBLISH_URL)
        step_gap(reason="发布页加载后")

        dpm._dismiss_shepherd_if_present(driver)
        step_gap(reason="关闭引导后")

        try:
            WebDriverWait(driver, 45).until(
                lambda d: _find_video_file_input(d) is not None
            )
            step_gap(reason="file input 已出现后")
        except Exception:
            logger.warning("等待 file input 超时，仍尝试查找")

        file_in = _find_video_file_input(driver)
        if not file_in:
            logger.error("未找到文件上传 input")
            try:
                driver.save_screenshot(
                    str(Path(__file__).parent / "ks_no_file_input.png")
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
        step_gap(reason="准备传视频前")
        file_in.send_keys(video_path)
        logger.info("已向 file input 传入视频路径")
        step_gap(reason="开始上传后")

        _wait_kuaishou_upload_done(driver)
        step_gap(reason="上传后间隔")

        dpm._dismiss_shepherd_if_present(driver)
        step_gap(reason="填写作品描述前")

        desc_el = None
        try:
            desc_el = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "#work-description-edit")
                )
            )
        except Exception:
            try:
                desc_el = wait.until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            "[contenteditable='true'][id='work-description-edit']",
                        )
                    )
                )
            except Exception as e:
                logger.error("未找到作品描述编辑区: %s", e)
                try:
                    driver.save_screenshot(
                        str(Path(__file__).parent / "ks_no_description.png")
                    )
                except Exception:
                    pass
                return False

        step_gap(reason="定位到作品描述区后")
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", desc_el
        )
        step_gap(reason="滚动到描述框后")
        try:
            desc_el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", desc_el)
        step_gap(reason="点击作品描述框后")
        try:
            desc_el.send_keys(Keys.CONTROL, "a")
            desc_el.send_keys(Keys.BACKSPACE)
        except Exception:
            pass

        step_gap(reason="清空描述框后")
        work_text = _compose_work_text()
        lines = work_text.split("\n")
        for i, line in enumerate(lines):
            desc_el.send_keys(line)
            if i < len(lines) - 1:
                desc_el.send_keys(Keys.ENTER)
                # 换行用较短随机停顿，避免多行时逐步叠加 5～15s
                dpm.human_sleep(0.4, 1.5, reason="描述换行节奏")
        if (title or "").strip():
            logger.info(
                "快手无标题栏，已忽略 title（仅记录）: %s",
                (title or "").strip()[:80],
            )
        logger.info("已填写作品描述（长度 %d）", len(work_text))
        step_gap(reason="填写描述后")

        dpm._dismiss_shepherd_if_present(driver)
        step_gap(reason="滚到底部前")

        driver.execute_script(
            "window.scrollTo(0, Math.max(document.body.scrollHeight,"
            " document.documentElement.scrollHeight));"
        )
        step_gap(reason="滚到底部后")

        step_gap(reason="查找发布按钮前")
        publish_el = None
        try:
            publish_el = WebDriverWait(driver, 120).until(
                lambda d: _find_kuaishou_publish_control(d)
            )
        except Exception:
            publish_el = _find_kuaishou_publish_control(driver)

        if not publish_el:
            logger.error("未找到「发布」按钮")
            try:
                driver.save_screenshot(
                    str(Path(__file__).parent / "ks_no_publish_btn.png")
                )
            except Exception:
                pass
            return False

        step_gap(reason="发布按钮已出现后")
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'end'});", publish_el
        )
        step_gap(reason="点击发布前")
        try:
            publish_el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", publish_el)

        logger.info("已点击「发布」，等待成功提示…")
        step_gap(reason="发布后等待响应")

        if _wait_kuaishou_publish_success(driver, timeout=120.0):
            step_gap(reason="检测到发布成功后关浏览器前")
            _close_shared_browser()
        else:
            logger.warning("未在超时内检测到明确成功文案，浏览器保持打开")

        return True
    except Exception as e:
        logger.exception("快手发布异常: %s", e)
        try:
            driver.save_screenshot(
                str(Path(__file__).parent / "ks_publish_error.png")
            )
        except Exception:
            pass
        return False


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="快手 Selenium 发布")
    parser.add_argument("--video", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    args = parser.parse_args()

    v, t, d = args.video.strip(), args.title.strip(), args.description.strip()
    if not v:
        v, t2, d2 = find_latest_video_and_meta()
        t = t or t2
        d = d or d2
    if not v:
        logger.error("未找到视频，请指定 --video")
        return 1

    ok = publish_kuaishou_video(v, t, d)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
