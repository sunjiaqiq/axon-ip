#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信视频号一键发布：从激活主窗口到发表桌面 aaa.mp4（短标题 6 字），并关闭窗口。
本目录可整体复制到其他电脑运行，依赖见 requirements.txt。
"""

import os
import sys
import time
import random
import types
import importlib.util

from pywinauto import Desktop  # type: ignore
from pywinauto.keyboard import send_keys  # type: ignore


LOG_PREFIX = "[视频号自动脚本]"


def log(msg: str) -> None:
    print(f"{LOG_PREFIX} {msg}", flush=True)


def timeout_wait(fn, timeout_sec: float, step_name: str):
    start = time.time()
    last_err = None
    while time.time() - start < timeout_sec:
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.5)
    raise RuntimeError(f"{step_name} 超时({timeout_sec}s)，最后错误: {last_err}")


def slow_pause():
    delay = random.uniform(3.0, 6.0)
    log(f"[节奏] 随机等待 {delay:.1f} 秒...")
    time.sleep(delay)


def _import_pyweixin():
    # 独立发布包：pyweixin 在本目录 pyweixin-main 下
    base_dir = os.path.dirname(os.path.abspath(__file__))
    wx_project_path = os.path.join(base_dir, "pyweixin-main")
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
        wx_project_path = os.path.join(base_dir, "pyweixin-main")

    if not os.path.isdir(wx_project_path):
        raise RuntimeError(f"未找到 pyweixin 目录: {wx_project_path}，请确保 publish 文件夹完整复制。")

    if wx_project_path not in sys.path:
        sys.path.insert(0, wx_project_path)

    if "pyweixin" not in sys.modules:
        pyweixin_package = types.ModuleType("pyweixin")
        pyweixin_package.__path__ = [wx_project_path]
        sys.modules["pyweixin"] = pyweixin_package

        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore  # noqa:F401
            winsettings_spec = importlib.util.spec_from_file_location(
                "pyweixin.WinSettings",
                os.path.join(wx_project_path, "WinSettings.py"),
            )
            if winsettings_spec and winsettings_spec.loader:
                winsettings_module = importlib.util.module_from_spec(winsettings_spec)
                winsettings_module.__package__ = "pyweixin"
                sys.modules["pyweixin.WinSettings"] = winsettings_module
                winsettings_spec.loader.exec_module(winsettings_module)
        except ImportError:
            fake_winsettings = types.ModuleType("pyweixin.WinSettings")

            class FakeSystemSettings:
                @staticmethod
                def copy_text_to_windowsclipboard(text: str) -> None:
                    try:
                        import win32clipboard  # type: ignore
                        import win32con  # type: ignore
                        win32clipboard.OpenClipboard()
                        try:
                            win32clipboard.EmptyClipboard()
                            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, str(text))
                        finally:
                            win32clipboard.CloseClipboard()
                    except Exception as e:  # noqa: BLE001
                        print(f"复制到剪贴板失败: {e}")

            fake_winsettings.SystemSettings = FakeSystemSettings()
            sys.modules["pyweixin.WinSettings"] = fake_winsettings

        init_file = os.path.join(wx_project_path, "__init__.py")
        if os.path.exists(init_file):
            with open(init_file, "r", encoding="utf-8") as f:
                exec(f.read(), pyweixin_package.__dict__)

    from pyweixin.WeChatTools import Navigator, Tools  # type: ignore
    from pyweixin.Uielements import Independent_window  # type: ignore
    return Navigator, Tools, Independent_window


def get_channels_window(Independent_window):
    return Desktop(backend="uia").window(**Independent_window().ChannelsWindow).wrapper_object()


def step1_activate_wechat(Navigator, Tools):
    log("[步骤1] 激活微信主窗口...")
    if not Tools.is_weixin_running():
        raise RuntimeError("微信未运行")
    timeout_wait(lambda: Navigator.open_weixin(is_maximize=False), 15, "激活微信主窗口")
    log("[步骤1][成功] 微信主窗口已激活")


def step2_open_channels(Navigator):
    log("[步骤2] 点击视频号 logo，打开视频号主界面...")
    timeout_wait(
        lambda: Navigator.open_channels(is_maximize=False, close_weixin=False, window_maximize=False),
        15, "打开视频号主界面",
    )
    log("[步骤2][成功] 视频号主界面已打开")


def step3_click_avatar(channels_win):
    log("[步骤3] 在视频号主界面点击右上角小人头像...")
    def _do():
        rect = channels_win.rectangle()
        right_edge, top_edge = rect.right, rect.top
        candidates = []
        for ctrl in channels_win.descendants():
            try:
                ctype = ctrl.friendly_class_name()
                if ctype not in ("Image", "Button"):
                    continue
                r = ctrl.rectangle()
                if r.top <= top_edge + 40:
                    continue
                dist_r = right_edge - r.right
                dist_t = r.top - top_edge
                if dist_r < 0 or dist_r > 150 or dist_t > 200:
                    continue
                candidates.append((dist_r, dist_t, ctype, ctrl))
            except Exception:
                continue
        if not candidates:
            raise RuntimeError("未找到头像候选控件")
        candidates.sort(key=lambda it: (it[0] + (0 if it[2] == "Image" else 10), it[1]))
        target = candidates[0][3]
        target.click_input()
    timeout_wait(_do, 15, "点击头像")
    log("[步骤3][成功] 已点击右上角头像")


def step4_goto_my_channel_from_like(Independent_window):
    log("[步骤4] 在“点赞和收藏”界面点击左侧【我的视频号】...")
    win = get_channels_window(Independent_window)

    def _do():
        # 优先严格按文本匹配“我的视频号”，只有完全找不到时才退化为区域+类型猜测
        rect = win.rectangle()
        left_edge, top_edge = rect.left, rect.top
        right_edge = rect.right

        exact_matches = []
        fuzzy_candidates = []
        for c in win.descendants():
            try:
                r = c.rectangle()
                # 只看左侧 1/3 区域内、纵向在中上部的控件
                if r.left < left_edge or r.left > left_edge + (right_edge - left_edge) * 0.4:
                    continue
                if r.top < top_edge + 80 or r.top > top_edge + 400:
                    continue

                cls = c.friendly_class_name()
                text = (c.window_text() or "").strip()
                # 1）严格命中文本“我的视频号”的控件，优先级最高
                if text == "我的视频号":
                    exact_matches.append((r.top, c))
                    continue
                # 2）文本包含“我的视频号”的，也作为精确候选
                if "我的视频号" in text:
                    exact_matches.append((r.top, c))
                    continue
                # 3）退化为：左侧纵向菜单项（无文本或短文本），仅在完全找不到“我的视频号”时兜底使用
                if cls in ("TabItem", "ListItem", "Button"):
                    score = 10
                    if text:
                        score -= 2
                    fuzzy_candidates.append((score, r.top, text, c))
            except Exception:
                continue

        if exact_matches:
            # 按纵向位置排序，通常“我的视频号”在中间偏下，取最后一个
            exact_matches.sort(key=lambda it: it[0])
            target = exact_matches[-1][1]
            log(f"[步骤4] 命中文本为『我的视频号』的控件: {target.window_text()!r}")
            target.click_input()
            return

        if not fuzzy_candidates:
            raise RuntimeError("未在左侧找到任何【我的视频号】相关控件")

        # 完全兜底：在没有“我的视频号”文字时，从候选中选择最像菜单项的控件
        fuzzy_candidates.sort(key=lambda it: (it[0], it[1]))
        target = fuzzy_candidates[min(len(fuzzy_candidates) - 1, 2)][3]
        log(f"[步骤4] 未找到文本『我的视频号』，兜底点击候选控件: {target.window_text()!r}")
        target.click_input()

    timeout_wait(_do, 20, "点击我的视频号")
    log("[步骤4][成功] 已点击【我的视频号】")


def step5_click_publish_video(Independent_window):
    log("[步骤5] 在“我的视频号”界面点击【发表视频】...")
    win = get_channels_window(Independent_window)
    def _do():
        candidates = [(c.rectangle().top, c) for c in win.descendants()
                      if (c.window_text() or "").strip() and "发" in (c.window_text() or "") and "视频" in (c.window_text() or "")
                      and c.friendly_class_name() in ("Button", "TabItem")]
        if not candidates:
            raise RuntimeError("未找到【发表视频】")
        candidates.sort(key=lambda x: x[0])
        candidates[0][1].click_input()
    timeout_wait(_do, 15, "点击发表视频")
    log("[步骤5][成功] 已点击【发表视频】")


def step6_click_upload_plus(Independent_window):
    log("[步骤6] 在发表视频界面点击“+ 上传 8 小时以内视频”区域...")
    win = get_channels_window(Independent_window)
    def _do():
        rect = win.rectangle()
        right_edge, top_edge = rect.right, rect.top
        candidates = []
        for c in win.descendants():
            try:
                if c.friendly_class_name() not in ("Button", "Image", "Pane"):
                    continue
                r = c.rectangle()
                if not (top_edge + 150 <= r.top <= top_edge + 500 and r.right - r.left >= 60 and right_edge - r.right >= 200):
                    continue
                candidates.append((r.top, c))
            except Exception:
                continue
        if not candidates:
            raise RuntimeError("未找到上传 + 区域")
        candidates.sort(key=lambda x: x[0])
        candidates[0][1].click_input()
    timeout_wait(_do, 15, "点击上传 + 区域")
    log("[步骤6][成功] 已点击上传 + 区域")


def step7_type_path_and_enter(video_path: str | None = None):
    log("[步骤7] 在文件对话框中模拟输入视频路径并回车...")
    time.sleep(2.0)
    if video_path:
        path_to_type = video_path
    else:
        path_to_type = os.path.join(os.path.expanduser("~"), "Desktop", "aaa.mp4")
    log(f"[步骤7] 模拟输入: {path_to_type}")
    def _do():
        send_keys("^a{BACKSPACE}")
        time.sleep(0.3)
        send_keys(path_to_type, with_spaces=True)
        time.sleep(0.3)
        send_keys("{ENTER}")
    timeout_wait(_do, 15, "输入路径并回车")
    log("[步骤7][成功] 已输入路径并回车")


def step8_fill_short_title_and_publish(Independent_window, short_title: str | None = None):
    log("[步骤8] 上传完成后：先点右上角最大化全屏，再找描述与发表，填完等10秒后关闭窗口...")
    time.sleep(2.0)
    win = get_channels_window(Independent_window)

    def _do():
        r_win = win.rectangle()
        top_edge, right_edge = r_win.top, r_win.right

        title_buttons = [(c.rectangle().left, c) for c in win.descendants()
                         if c.friendly_class_name() == "Button" and top_edge <= c.rectangle().top <= top_edge + 50 and c.rectangle().right >= right_edge - 150]
        title_buttons.sort(key=lambda x: x[0])
        if len(title_buttons) >= 2:
            title_buttons[-2][1].click_input()
            time.sleep(1.5)

        cx, cy = (r_win.left + r_win.right) // 2, (r_win.top + r_win.bottom) // 2
        win.click_input(coords=(cx, cy))
        time.sleep(0.5)
        for _ in range(6):
            send_keys("{PGDN}")
            time.sleep(0.4)
        for _ in range(40):
            send_keys("{DOWN}")
            time.sleep(0.05)
        for _ in range(30):
            send_keys("{RIGHT}")
            time.sleep(0.05)

        descendants = win.descendants()
        edits = [(c.rectangle().top, c) for c in descendants if c.friendly_class_name() == "Edit" and c.rectangle().top >= 150]
        if not edits:
            raise RuntimeError("未找到短标题 Edit")
        edits.sort(key=lambda x: x[0])
        final_title = (short_title or "自动化测试标题").strip()
        edits[0][1].set_edit_text(final_title)
        log(f"[步骤8] 已填写短标题: {final_title}")

        candidates = [(c.rectangle().top, c) for c in descendants
                       if c.friendly_class_name() == "Button" and ("发表" in (c.window_text() or "") or "发布" in (c.window_text() or ""))]
        if not candidates:
            raise RuntimeError("未找到【发表】按钮")
        candidates.sort(key=lambda x: x[0], reverse=True)
        time.sleep(2.0)
        candidates[0][1].click_input()

        log("[步骤8] 发表完成，等待 10 秒...")
        time.sleep(10.0)

        log("[步骤8] 查找右上角关闭按钮并关闭窗口...")
        try:
            r_win_now = win.rectangle()
            top_now, right_now = r_win_now.top, r_win_now.right
        except Exception:
            top_now, right_now = top_edge, right_edge

        close_btn_found = None
        for c in win.descendants():
            try:
                if c.friendly_class_name() != "Button":
                    continue
                name = (c.window_text() or "").strip()
                if ("关" not in name and "闭" not in name) or c.rectangle().top < top_now or c.rectangle().top > top_now + 80 or c.rectangle().right < right_now - 150:
                    continue
                close_btn_found = c
                break
            except Exception:
                continue
        if close_btn_found:
            log("[步骤8] 点击关闭按钮")
            close_btn_found.click_input()
        else:
            try:
                for c in win.parent().descendants():
                    try:
                        if c.friendly_class_name() != "Button":
                            continue
                        name = (c.window_text() or "").strip()
                        if ("关" not in name and "闭" not in name) or c.rectangle().top < top_now or c.rectangle().top > top_now + 80 or c.rectangle().right < right_now - 150:
                            continue
                        close_btn_found = c
                        break
                    except Exception:
                        continue
                if close_btn_found:
                    log("[步骤8] 在父窗口点击关闭")
                    close_btn_found.click_input()
            except Exception:
                pass
        if not close_btn_found:
            log("[步骤8] 未找到关闭按钮，发送 Alt+F4...")
            send_keys("%{F4}")

    timeout_wait(_do, 25, "全屏+填描述+发表+等10秒+关闭")
    log("[步骤8][成功] 步骤8 完成")


def main(video_path: str | None = None, short_title: str | None = None) -> int:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    print("=" * 70)
    print("自动：微信视频号从主界面到发表视频（短标题自动填写）")
    print("=" * 70)

    Navigator, Tools, Independent_window = _import_pyweixin()

    try:
        step1_activate_wechat(Navigator, Tools)
        slow_pause()
        step2_open_channels(Navigator)
        slow_pause()
        channels_win = get_channels_window(Independent_window)
        step3_click_avatar(channels_win)
        slow_pause()
        step4_goto_my_channel_from_like(Independent_window)
        slow_pause()
        step5_click_publish_video(Independent_window)
        slow_pause()
        step6_click_upload_plus(Independent_window)
        slow_pause()
        step7_type_path_and_enter(video_path)
        slow_pause()
        step8_fill_short_title_and_publish(Independent_window, short_title)

        log("全部步骤执行完毕（是否成功以微信界面为准）")
        print("=" * 70)
        return 0
    except Exception as e:  # noqa: BLE001
        log(f"[错误] 流程中断: {e}")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    input_path = None
    input_title = None
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]
    if len(sys.argv) >= 3:
        input_title = sys.argv[2]
    sys.exit(main(input_path, input_title))
