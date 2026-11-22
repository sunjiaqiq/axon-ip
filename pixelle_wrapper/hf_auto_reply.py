import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path
import os
import re

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import douyin_publish_mcp
from ai_pipeline.doubao_client import doubao_chat_completion
import yaml


BASE_DIR = THIS_DIR
LOG_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
REPLY_RECORD_PATH = OUTPUT_DIR / "dm_reply_records.jsonl"
# 与私信记录、其它状态分离：仅本脚本「今日/累计回复」统计（自然日，本地时区）
REPLY_STATS_PATH = OUTPUT_DIR / "hf_dm_reply_stats.json"
DEBUG_DIR = BASE_DIR / "debug_artifacts_selenium"


logger = logging.getLogger("douyin_dm_selenium")

# 未配置自定义提示词时使用（占位符与 _load_persona_from_config 返回的键一致）
DEFAULT_DM_AI_SYSTEM_PROMPT_ZH = """你是抖音商家侧客服助手。请根据客户发来的最新一条私信，写一条可直接发送的中文回复。
要求：简短、口语化、合规；只输出回复正文，不要引号或标题。

【平台话术规范（必须遵守）】
- 回复中禁止出现「微信」「微信号」「加微信」「加微」「VX」「vx」「薇信」等字样及变体。
- 如需引导加好友或留联系方式，只允许使用：
  1）「地球号」代替第三方聊天工具名称（例如：地球号 ${wechatId}，若 ${wechatId} 为空则不要编造号码）；或
  2）「+我们」式简短引导（例如：+我们了解详情、+我们给您发资料），不要写具体外链或敏感词。
- 若人设里没有有效联系方式，只用「+我们xxx」类话术承接，不要虚构号码。

【我方信息】（请自然融入，不要生硬罗列整段）
- 公司/团队：${companyName}
- 对外联系号（仅允许以「地球号」或「+我们」话术使用，禁止说微信）：${wechatId}
- 服务区域：${serviceRegion}
- 目标客户：${targetAudience}
- 公司地址：${companyAddress}
- 经营年限：${businessYear}
- 产品/服务要点：${keyFeatures}
- 其他说明：${relatedNotes}
"""

AI_ENABLED = True
AI_PERSONA_PROMPT_TEMPLATE = ""
AI_KB_VARS: dict[str, str] = {}
# 将来由主程序 UI 传入的人设补充，与文件/环境变量中的提示词合并后一并给豆包
AI_UI_PERSONA_EXTRA: str = ""


DM_ENTRY_XPATHS = [
    "//*[@id='douyin-navigation']//*[@data-e2e='something-button'][.//p[normalize-space()='私信']]",
    "//*[@id='douyin-navigation']//p[normalize-space()='私信']",
    "//*[@id='island_b69f5']/div/ul[2]/div/li/div/div",
    "//*[@id='island_b69f5']/div/ul[2]/div/li/div/div/div[1]/p",
    "//p[normalize-space()='私信']",
]
DM_UNREAD_BADGE_GLOBAL_XPATH = "//*[@x-semi-prop='count' and normalize-space(text())!='']"
CONVERSATION_ITEM_XPATH = "//div[@data-e2e='conversation-item']"
UNREAD_CONVERSATION_ITEM_XPATH = "//div[@data-e2e='conversation-item'][.//*[@x-semi-prop='count']]"
UNREAD_BADGE_XPATH = ".//*[@x-semi-prop='count']"
STRANGER_ROW_XPATHS = [
    "//div[contains(@class,'componentsLeftPanelboxList')]//div[contains(@class,'conversationStrangerBoxwrapper')]",
    "//div[contains(@class,'componentsLeftPanelboxList')]//div[contains(@class,'conversationStrangerBoxtitle') and normalize-space()='陌生人消息']",
    "//*[contains(normalize-space(.), '陌生人消息')]",
    "//div[contains(@class,'conversationStrangerBoxwrapper')]",
    "//div[contains(@class,'conversationStrangerBoxtitle') and normalize-space()='陌生人消息']",
    "//p[contains(@class,'conversationStrangerConversationListtitle') and normalize-space()='陌生人消息']",
    "//div[contains(normalize-space(.), '陌生人') and not(@data-e2e='conversation-item')]",
]
INPUT_XPATHS = [
    "//*[@contenteditable='true' and @role='textbox']",
    "//*[@contenteditable='true' and contains(@class,'DraftEditor-content')]",
    "//*[@contenteditable='true' and @data-slate-editor='true']",
    "//div[@contenteditable='true']",
    "//textarea",
]
SEND_BTN_XPATH = "//button[.//*[name()='path' and @fill='#FE2C55']]"
CHAT_PAGE_URL = "https://www.douyin.com/chat?isPopup=1"
MAIN_LIST_WRAPPER_XPATH = "//div[contains(@class,'componentsLeftPanelboxList')]"
STRANGER_LIST_WRAPPER_XPATH = "//div[contains(@class,'conversationStrangerConversationListtransition') or .//p[contains(@class,'conversationStrangerConversationListtitle') and normalize-space()='陌生人消息']]"
STRANGER_LIST_WRAPPER_XPATH = (
    "//div[contains(@class,'conversationStrangerConversationListtransition') "
    "or contains(@class,'conversationStrangerConversationListlistWrapper') "
    "or .//p[contains(@class,'conversationStrangerConversationListtitle') and normalize-space()='陌生人消息']]"
)
STRANGER_PANEL_TITLE_XPATH = "//p[contains(@class,'conversationStrangerConversationListtitle') and normalize-space()='陌生人消息']"
STRANGER_BACK_XPATHS = [
    "//p[contains(@class,'conversationStrangerConversationListtitle') and normalize-space()='陌生人消息']/preceding-sibling::*[1]",
    "//div[contains(@class,'conversationStrangerConversationListhead')]//*[name()='svg']",
]


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"douyin_dm_selenium_{ts}.log"
    fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.info("日志文件: %s", log_path)


def human_pause(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


def human_step_pause(min_s: float, max_s: float) -> None:
    # 用户要求：每个关键操作都要 3-5 秒随机停留
    human_pause(max(3.0, min_s), max(5.0, max_s))


def append_reply_record(chat_key: str, msg: str, source: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chat_key": chat_key,
        "message": msg,
        "source": source,
    }
    with REPLY_RECORD_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def bump_hf_reply_stats(success_count: int) -> None:
    """按自然日（本地日历）累计今日与总回复数，写入独立 JSON。"""
    if success_count <= 0:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    data: dict = {}
    if REPLY_STATS_PATH.exists():
        try:
            data = json.loads(REPLY_STATS_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    cal = str(data.get("calendar_date", "") or "")
    if cal != today:
        data["calendar_date"] = today
        data["today_replies"] = 0
    data["today_replies"] = int(data.get("today_replies", 0) or 0) + success_count
    data["total_replies"] = int(data.get("total_replies", 0) or 0) + success_count
    try:
        REPLY_STATS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("统计已写入 %s today=%s +%d", REPLY_STATS_PATH, today, success_count)
    except Exception as e:
        logger.warning("写入回复统计失败（忽略）: %s", e)


def extract_row_latest_preview(row) -> str:
    # 左侧会话行中的预览文本就是“最新一条消息摘要”
    xps = [
        ".//pre[contains(@class,'ConversationItemHinttextBox')]",
        ".//pre",
    ]
    for xp in xps:
        try:
            elems = row.find_elements(By.XPATH, xp)
            for e in elems:
                txt = (e.text or "").strip()
                if txt:
                    return txt
        except Exception:
            continue
    return ""


def build_reply_message(base_message: str, latest_text: str) -> str:
    if not AI_ENABLED or not AI_PERSONA_PROMPT_TEMPLATE.strip():
        return base_message
    try:
        system_prompt = _render_prompt_template(AI_PERSONA_PROMPT_TEMPLATE, AI_KB_VARS)
        extra = (AI_UI_PERSONA_EXTRA or "").strip()
        if extra:
            system_prompt = (system_prompt.rstrip() + "\n\n【客户自定义人设补充】\n" + extra).strip()
        contact_id = str(AI_KB_VARS.get("wechatId") or "").strip()
        user_prompt = (
            "请根据下面客户最新一句私信，输出一条可直接发送的回复。\n"
            "要求：简短、拟人、合规；禁止出现「微信」「加微」「VX」等字样；"
            "留联系方式仅用「地球号」或「+我们」后接对外联系号；只输出纯文本。\n"
            f"客户最新一句：{latest_text or '（空）'}"
        )
        if contact_id:
            # 模型常改成「搜…工作号xxx」，与用户要求的「+我们+号码」不一致，这里写死硬性句式
            user_prompt += (
                f"\n【硬性要求】对外联系号必须原样出现在回复正文中：{contact_id}。"
                f"请使用「+我们{contact_id}」或「地球号{contact_id}」其一（推荐前者），"
                "不要用「搜」「查找」「工作号」等替代表述。"
            )
        reply = doubao_chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            timeout_s=60,
        )
        reply = (reply or "").strip()
        if not reply:
            return base_message
        reply = _sanitize_for_dm_input(reply)
        if not reply:
            return _sanitize_for_dm_input(base_message) or base_message
        # 仍漏号时兜底（区分「没进 KB」与「模型不听话」）
        if contact_id and contact_id not in reply:
            logger.info(
                "DM 回复未包含对外联系号，已追加 +我们 兜底（KB 已配置，长度=%d）",
                len(contact_id),
            )
            reply = _sanitize_for_dm_input(f"{reply.rstrip()} +我们{contact_id}")
        if not reply:
            return _sanitize_for_dm_input(base_message) or base_message
        return reply
    except Exception as e:
        logger.warning("AI 生成失败，回退固定文案: %s", e)
        return _sanitize_for_dm_input(base_message) or base_message


def _render_prompt_template(tpl: str, vars_map: dict[str, str]) -> str:
    def repl(m):
        key = m.group(1)
        return str(vars_map.get(key, ""))

    return re.sub(r"\$\{([A-Za-z0-9_]+)\}", repl, tpl)


def _load_persona_from_config() -> dict[str, str]:
    cfg_path = BASE_DIR / "config.yaml"
    data = {}
    try:
        if cfg_path.exists():
            with cfg_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
    except Exception:
        data = {}

    persona = data.get("persona", {}) if isinstance(data, dict) else {}
    llm = data.get("llm", {}) if isinstance(data, dict) else {}
    return {
        "priceRange": str(persona.get("price_range", "")),
        "wechatId": str(persona.get("wechat_id", "") or ""),
        "companyName": str(persona.get("company_name", "")),
        "serviceRegion": str(persona.get("service_region", "")),
        "targetAudience": str(persona.get("target_audience", "")),
        "companyAddress": str(persona.get("company_address", "")),
        "businessYear": str(persona.get("business_year", "")),
        "keyFeatures": str(persona.get("key_features", "")),
        "relatedNotes": str(persona.get("related_notes", "")),
        "llmModel": str(llm.get("model", "")),
    }


def reply_one_pending_in_stranger_list(
    driver,
    msg: str,
    replied_keys: set[str],
    min_s: float,
    max_s: float,
) -> tuple[int, str]:
    if not _inside_stranger_mode(driver):
        return 0, ""
    scope = find_first_visible(driver, [STRANGER_LIST_WRAPPER_XPATH], timeout=5)
    if not scope:
        return 0, ""
    rows = [r for r in scope.find_elements(By.XPATH, ".//div[@data-e2e='conversation-item']") if r.is_displayed()]
    if not rows:
        return 0, ""

    for row in rows:
        try:
            in_stranger = row.find_elements(
                By.XPATH,
                "./ancestor::*[contains(@class,'conversationStrangerConversationListtransition') or contains(@class,'conversationStrangerConversationListlistWrapper')]",
            )
            if not in_stranger:
                continue
        except Exception:
            continue
        key = get_row_chat_key(row)
        dedupe_key = get_row_dedupe_key(row, source="stranger")
        if dedupe_key in replied_keys:
            continue
        latest_preview = extract_row_latest_preview(row)
        # 若预览就是我们固定回复，认为已回过；否则视为“未回候选”
        if latest_preview and msg in latest_preview:
            continue

        if not click_conversation_row(driver, row):
            continue
        human_step_pause(min_s, max_s)
        if not wait_chat_input_ready(driver, timeout=8.0):
            continue
        final_msg = build_reply_message(msg, latest_preview)
        if send_and_verify(driver, final_msg, min_s, max_s):
            replied_keys.add(dedupe_key)
            append_reply_record(key, final_msg, "stranger")
            logger.info("✅ stranger 来源补回成功(未回): %s | latest=%r", key, latest_preview)
            return 1, key
    return 0, ""


def dump_debug(driver, tag: str) -> None:
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        png = DEBUG_DIR / f"{ts}_{tag}.png"
        html = DEBUG_DIR / f"{ts}_{tag}.html"
        driver.save_screenshot(str(png))
        with html.open("w", encoding="utf-8") as f:
            f.write(driver.page_source or "")
        logger.info("调试截图: %s", png)
        logger.info("调试HTML: %s", html)
    except Exception as e:
        logger.warning("调试文件保存失败: %s", e)


def ensure_driver():
    if not douyin_publish_mcp.ensure_browser():
        raise RuntimeError("Selenium 浏览器启动失败")
    driver = douyin_publish_mcp.driver
    if not driver:
        raise RuntimeError("Selenium driver 为空")
    return driver


def find_first_visible(driver, xpaths: list[str], timeout: float = 8):
    end = time.time() + timeout
    while time.time() < end:
        for xp in xpaths:
            try:
                elems = driver.find_elements(By.XPATH, xp)
                for e in elems:
                    if e.is_displayed():
                        return e
            except Exception:
                continue
        time.sleep(0.2)
    return None


def hover_dm_entry(driver, min_s: float, max_s: float) -> bool:
    dm = find_first_visible(driver, DM_ENTRY_XPATHS, timeout=6)
    if not dm:
        logger.warning("未找到私信入口")
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dm)
    except Exception:
        pass
    # 优先点可点击容器，避免只点到文字节点。
    clickable = dm
    try:
        clickable = dm.find_element(
            By.XPATH,
            "./ancestor::*[@data-e2e='something-button' or @role='button' or self::a][1]",
        )
    except Exception:
        clickable = dm

    ActionChains(driver).move_to_element(clickable).pause(random.uniform(0.6, 1.2)).perform()
    human_step_pause(min_s, max_s)
    # 悬停后再点击一次“私信”，让会话区更稳定地展开/停留。
    click_elem(driver, clickable)
    human_step_pause(min_s, max_s)
    return True


def js_open_dm_panel(driver) -> bool:
    script = """
    () => {
      const norm = (s) => (s || '').replace(/\\s+/g, '').trim();
      const nodes = Array.from(document.querySelectorAll('p,span,div,a'))
        .filter(n => norm(n.textContent) === '私信');
      for (const n of nodes) {
        const btn = n.closest("[data-e2e='something-button']") || n.closest("a,li,div");
        if (!btn) continue;
        try {
          btn.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true, cancelable: true, view: window}));
          btn.dispatchEvent(new MouseEvent('mouseover', {bubbles: true, cancelable: true, view: window}));
          btn.click();
          return true;
        } catch (e) {}
      }
      return false;
    }
    """
    try:
        ok = driver.execute_script(script)
        time.sleep(random.uniform(3.0, 5.0))
        return bool(ok)
    except Exception:
        return False


def js_open_stranger_panel(driver) -> bool:
    script = """
    () => {
      const candidates = [
        document.querySelector('.conversationStrangerBoxwrapper'),
        document.querySelector('.conversationStrangerBoxtitle'),
      ].filter(Boolean);
      for (const el of candidates) {
        try {
          el.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true, cancelable: true, view: window}));
          el.click();
          return true;
        } catch (e) {}
      }
      return false;
    }
    """
    try:
        ok = driver.execute_script(script)
        time.sleep(random.uniform(3.0, 5.0))
        return bool(ok)
    except Exception:
        return False


def has_dm_unread_on_home(driver) -> bool:
    # 保留函数仅做日志参考，不作为强阻断条件。
    try:
        badges = driver.find_elements(By.XPATH, DM_UNREAD_BADGE_GLOBAL_XPATH)
        return any(b.is_displayed() for b in badges)
    except Exception:
        return False


def wait_list_ready(driver, timeout: float = 6) -> bool:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, CONVERSATION_ITEM_XPATH))
        )
        return True
    except TimeoutException:
        return False


def ensure_dm_list_ready(driver, timeout: float = 10.0) -> bool:
    # 仅基于主页私信入口展开会话列表，不使用 /message 路由（已废弃）。
    if wait_list_ready(driver, timeout=timeout):
        return True
    # DOM 半浮层没挂上时，尝试用 JS 再触发一次入口。
    js_open_dm_panel(driver)
    return wait_list_ready(driver, timeout=timeout)


def wait_main_list_wrapper_ready(driver, timeout: float = 10.0) -> bool:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, MAIN_LIST_WRAPPER_XPATH))
        )
        return True
    except TimeoutException:
        return False


def wait_stranger_list_wrapper_ready(driver, timeout: float = 8.0) -> bool:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, STRANGER_LIST_WRAPPER_XPATH))
        )
        return True
    except TimeoutException:
        return False


def _inside_stranger_mode(driver) -> bool:
    try:
        titles = [e for e in driver.find_elements(By.XPATH, STRANGER_PANEL_TITLE_XPATH) if e.is_displayed()]
        if titles:
            return True
        wrappers = [e for e in driver.find_elements(By.XPATH, STRANGER_LIST_WRAPPER_XPATH) if e.is_displayed()]
        return len(wrappers) > 0
    except Exception:
        return False


def _stranger_row_has_unread_hint(row) -> bool:
    # 陌生人入口在主列表常见的是红点（无数字），也视为未读。
    checks = [
        ".//*[contains(@class,'ConversationItemUnReadCountmutedUnreadBadge')]",
        ".//*[contains(@class,'ConversationItemUnReadCountmutedUnreadBadge')]",
        ".//*[contains(@class,'ConversationItemUnReadCountdigitsNumberPop')]",
        ".//*[@x-semi-prop='count']",
    ]
    for xp in checks:
        try:
            elems = row.find_elements(By.XPATH, xp)
            for e in elems:
                if e.is_displayed():
                    return True
        except Exception:
            continue
    return False


def _back_to_main_list(driver, min_s: float, max_s: float) -> None:
    btn = find_first_visible(driver, STRANGER_BACK_XPATHS, timeout=3)
    if btn:
        click_elem(driver, btn)
        human_step_pause(min_s, max_s)


def _row_has_unread_badge(row) -> bool:
    try:
        badges = row.find_elements(By.XPATH, UNREAD_BADGE_XPATH)
    except Exception:
        return False
    for b in badges:
        try:
            if not b.is_displayed():
                continue
            txt = (b.text or "").strip()
            if txt.isdigit() and int(txt) > 0:
                return True
        except Exception:
            continue
    return False


def click_elem(driver, elem) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
    except Exception:
        pass
    try:
        elem.click()
        return True
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", elem)
        return True
    except Exception:
        return False


def get_row_chat_key(row) -> str:
    txt = (row.text or "").strip()
    if not txt:
        return "__unknown_chat__"
    first = txt.splitlines()[0].strip()
    return first or "__unknown_chat__"


def get_row_dedupe_key(row, source: str) -> str:
    name = get_row_chat_key(row)
    avatar_src = ""
    try:
        imgs = row.find_elements(By.XPATH, ".//img")
        if imgs:
            avatar_src = (imgs[0].get_attribute("src") or "").strip()
    except Exception:
        avatar_src = ""
    avatar_fingerprint = avatar_src[-48:] if avatar_src else ""
    return f"{source}|{name}|{avatar_fingerprint}"


def _page_inner_text_contains(driver, fragment: str) -> bool:
    """用 JS 在页面可见文本中查找，避免把整段 AI 回复塞进 XPath（引号/换行会破坏表达式）。"""
    if not fragment or len(fragment.strip()) < 1:
        return False
    try:
        return bool(
            driver.execute_script(
                "var t = arguments[0];"
                "if(!document.body||!document.body.innerText)return false;"
                "return document.body.innerText.indexOf(t) >= 0;",
                fragment,
            )
        )
    except Exception:
        return False


def _sanitize_for_dm_input(text: str) -> str:
    """抖音私信输入框对多行、零宽字符、Markdown 壳子敏感，易导致 send_keys 无效果或只打进一半。"""
    if not text:
        return ""
    t = str(text).replace("\x00", "").replace("\u200b", "").replace("\ufeff", "").strip()
    t = re.sub(r"^#{1,6}\s*", "", t)
    t = t.replace("**", "").replace("__", "")
    t = re.sub(r"[\r\n\v\f]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 800:
        t = t[:800].rstrip()
    return t


def _fill_chat_input(driver, box, text: str, min_s: float, max_s: float) -> bool:
    """先聚焦并清空，再 send_keys；失败则用 JS 写 contenteditable（兼容 AI 特殊符号）。"""
    if not text:
        return False
    try:
        click_elem(driver, box)
        human_step_pause(min_s, max_s)
        try:
            box.send_keys(Keys.CONTROL, "a")
            human_step_pause(min_s * 0.25, max_s * 0.25)
            box.send_keys(Keys.BACKSPACE)
            human_step_pause(min_s * 0.25, max_s * 0.25)
        except Exception:
            pass
        box.send_keys(text)
        return True
    except Exception as e:
        logger.warning("send_keys 写入失败，尝试 JS 写入输入框: %s", e)
        try:
            driver.execute_script(
                """
                var el = arguments[0], t = arguments[1];
                el.focus();
                try {
                  if (el.isContentEditable || el.contentEditable === 'true') {
                    el.innerText = '';
                    el.innerText = t;
                  } else {
                    el.value = t;
                  }
                } catch (e2) {}
                ['input','change','keyup'].forEach(function(ev) {
                  try { el.dispatchEvent(new Event(ev, { bubbles: true })); } catch (e3) {}
                });
                """,
                box,
                text,
            )
            return True
        except Exception as e2:
            logger.warning("JS 写入输入框仍失败: %s", e2)
            return False


def send_and_verify(driver, msg: str, min_s: float, max_s: float) -> bool:
    box = find_first_visible(driver, INPUT_XPATHS, timeout=10)
    if not box:
        logger.warning("未找到输入框")
        return False

    safe = _sanitize_for_dm_input(msg)
    if not safe:
        logger.warning("回复净化后为空，跳过发送（原文长度=%d）", len(msg or ""))
        return False

    if not _fill_chat_input(driver, box, safe, min_s, max_s):
        logger.warning("未能写入私信输入框")
        return False

    human_step_pause(min_s, max_s)
    try:
        box.send_keys(Keys.ENTER)
    except Exception:
        try:
            send_btn = driver.find_element(By.XPATH, SEND_BTN_XPATH)
            click_elem(driver, send_btn)
        except Exception:
            logger.warning("发送失败（Enter/按钮均失败）")
            return False

    # 回显验证以实际写入的 safe 为准
    needle = safe
    if not needle:
        logger.warning("回复内容为空，视为未发送")
        return False
    candidates = [needle]
    if len(needle) > 200:
        candidates.append(needle[:200].rstrip())
    if len(needle) > 80:
        candidates.append(needle[:80].rstrip())
    if len(needle) > 40:
        candidates.append(needle[:40].rstrip())
    last_err = None
    for i, piece in enumerate(candidates):
        if len(piece) < 2:
            continue
        wait_s = 10.0 if i == 0 else 5.0
        try:
            WebDriverWait(driver, wait_s).until(lambda d, p=piece: _page_inner_text_contains(d, p))
            return True
        except Exception as e:
            last_err = e
            continue
    logger.warning("发送后未验证到回显（已尝试截断匹配），长度=%d err=%s", len(needle), last_err)
    return False


def wait_chat_input_ready(driver, timeout: float = 10.0) -> bool:
    return find_first_visible(driver, INPUT_XPATHS, timeout=timeout) is not None


def click_conversation_row(driver, row) -> bool:
    # 先点整行，再点内容主区域，最后 JS click 兜底。
    if click_elem(driver, row):
        return True
    try:
        body = row.find_element(By.XPATH, ".//div[contains(@class,'v3p3ob08')]")
        if click_elem(driver, body):
            return True
    except Exception:
        pass
    return False


def reply_one_unread_in_list(
    driver,
    msg: str,
    replied_keys: set[str],
    source: str,
    min_s: float,
    max_s: float,
    scope_xpath: str | None = None,
) -> tuple[int, str]:
    base = "."
    if scope_xpath:
        scope = find_first_visible(driver, [scope_xpath], timeout=5)
        if not scope:
            return 0, ""
        base = scope_xpath
    rows = driver.find_elements(By.XPATH, f"{base}//div[@data-e2e='conversation-item']")
    if not rows:
        return 0, ""

    candidates = []
    for r in rows:
        try:
            if not r.is_displayed():
                continue
            if not _row_has_unread_badge(r):
                continue
            key = get_row_chat_key(r)
            dedupe_key = get_row_dedupe_key(r, source=source)
            if dedupe_key in replied_keys:
                continue
            candidates.append((r, key, dedupe_key))
        except Exception:
            continue

    if not candidates:
        return 0, ""

    for target, target_key, dedupe_key in candidates[:5]:
        if not click_conversation_row(driver, target):
            logger.warning("点击未读会话失败: %s", target_key)
            continue

        human_step_pause(min_s, max_s)
        # 部分会话首点只会激活行，不会真正打开聊天框，再补点一次
        if not wait_chat_input_ready(driver, timeout=4.0):
            click_conversation_row(driver, target)
            human_step_pause(min_s, max_s)

        if not wait_chat_input_ready(driver, timeout=8.0):
            logger.warning("会话打开后仍未出现输入框: %s", target_key)
            continue

        human_step_pause(min_s, max_s)
        latest_preview = extract_row_latest_preview(target)
        final_msg = build_reply_message(msg, latest_preview)
        if send_and_verify(driver, final_msg, min_s, max_s):
            replied_keys.add(dedupe_key)
            append_reply_record(target_key, final_msg, source)
            logger.info("✅ %s 来源回复成功: %s | latest=%r", source, target_key, latest_preview)
            return 1, target_key
    return 0, ""


def reply_one_in_stranger(driver, msg: str, replied_keys: set[str], min_s: float, max_s: float) -> tuple[int, str]:
    row = find_first_visible(driver, STRANGER_ROW_XPATHS, timeout=10)
    if not row:
        logger.info("未找到“陌生人消息”入口")
        return 0, ""
    has_unread_hint = _stranger_row_has_unread_hint(row)
    if not has_unread_hint:
        logger.info("陌生人入口无未读标记，尝试进入后检查是否有“未回”")

    if not _inside_stranger_mode(driver):
        entered = False
        for _ in range(3):
            ok = click_elem(driver, row)
            if not ok:
                ok = js_open_stranger_panel(driver)
            if not ok:
                logger.warning("点击“陌生人消息”失败")
                row = find_first_visible(driver, STRANGER_ROW_XPATHS, timeout=3) or row
                continue
            human_step_pause(min_s, max_s)
            if wait_stranger_list_wrapper_ready(driver, timeout=10.0):
                entered = True
                break
            # 点击成功但还未切换时，再尝试 js 强制点击一次
            js_open_stranger_panel(driver)
            row = find_first_visible(driver, STRANGER_ROW_XPATHS, timeout=3) or row
        if not entered and not _inside_stranger_mode(driver):
            logger.warning("未识别到陌生人列表容器，跳过陌生人回复")
            return 0, ""

    # 进入陌生人后同样按未读会话处理
    replied = reply_one_unread_in_list(
        driver, msg, replied_keys, "stranger", min_s, max_s, scope_xpath=STRANGER_LIST_WRAPPER_XPATH
    )
    if replied[0] <= 0:
        replied = reply_one_pending_in_stranger_list(driver, msg, replied_keys, min_s, max_s)
    _back_to_main_list(driver, min_s, max_s)
    return replied


def run_once(
    driver,
    message: str,
    min_pause: float,
    max_pause: float,
) -> dict:
    replied_keys: set[str] = set()
    try:
        # 优先直接进入 chat 页面（用户提供的新入口），失败再走主页私信入口。
        # 聊天页可能要几秒才加载，先打开再给拟人等待
        driver.get(CHAT_PAGE_URL)
        human_step_pause(min_pause, max_pause)
        # 再给一次短重试窗口，避免首屏异步挂载慢导致误判
        if not wait_main_list_wrapper_ready(driver, timeout=8.0):
            time.sleep(random.uniform(3.0, 5.0))
        if not ensure_dm_list_ready(driver, timeout=8):
            if "douyin.com" not in (driver.current_url or ""):
                driver.get("https://www.douyin.com/")
                human_pause(min_pause, max_pause)
            if not hover_dm_entry(driver, min_pause, max_pause):
                if not js_open_dm_panel(driver):
                    logger.info("chat页与主页私信入口都未能打开会话列表，结束本次任务")
                    dump_debug(driver, "dm_entry_not_opened")
                    return {"total": 0, "default": 0, "stranger": 0, "people": []}
        has_unread_hint = has_dm_unread_on_home(driver)
        logger.info("会话页未读提示: %s", has_unread_hint)

        if not ensure_dm_list_ready(driver, timeout=10):
            logger.info("会话列表未就绪，结束本次任务")
            dump_debug(driver, "list_not_ready")
            return {"total": 0, "default": 0, "stranger": 0, "people": []}
        if not wait_main_list_wrapper_ready(driver, timeout=6.0):
            logger.info("主会话列表容器未就绪，结束本次任务")
            dump_debug(driver, "main_list_wrapper_not_ready")
            return {"total": 0, "default": 0, "stranger": 0, "people": []}

        # 清空默认未读
        replied_default = 0
        replied_stranger = 0
        replied_people: list[str] = []
        for _ in range(50):
            n, who = reply_one_unread_in_list(
                driver, message, replied_keys, "default", min_pause, max_pause, scope_xpath=MAIN_LIST_WRAPPER_XPATH
            )
            if n <= 0:
                break
            replied_default += n
            if who:
                replied_people.append(who)
            human_step_pause(min_pause, max_pause)

        # 清空陌生人未读
        for _ in range(50):
            n, who = reply_one_in_stranger(
                driver, message, replied_keys, min_pause, max_pause
            )
            if n <= 0:
                break
            replied_stranger += n
            if who:
                replied_people.append(who)
            human_step_pause(min_pause, max_pause)

        total = replied_default + replied_stranger
        logger.info("本次回复数量: %d（default=%d, stranger=%d）", total, replied_default, replied_stranger)
        logger.info("本次回复人数: %d | %s", len(set(replied_people)), list(dict.fromkeys(replied_people)))
        if total <= 0:
            dump_debug(driver, "no_reply_detected")
        return {
            "total": total,
            "default": replied_default,
            "stranger": replied_stranger,
            "people": list(dict.fromkeys(replied_people)),
        }
    except Exception as e:
        logger.warning("本次任务异常: %s", e)
        return {"total": 0, "default": 0, "stranger": 0, "people": []}


def _apply_hf_ai_globals(
    *,
    use_ai: bool = True,
    ai_prompt_file: str = "",
    persona_extra: str = "",
    persona_extra_file: str = "",
    persona_kb_override: dict[str, str] | None = None,
) -> None:
    """写入模块级 AI 配置（CLI 与 FastAPI 同进程调用共用）。"""
    global AI_ENABLED, AI_PERSONA_PROMPT_TEMPLATE, AI_KB_VARS, AI_UI_PERSONA_EXTRA
    AI_ENABLED = bool(use_ai)
    base_kb = _load_persona_from_config()
    if persona_kb_override:
        for k, v in persona_kb_override.items():
            if v is not None and str(v).strip():
                base_kb[str(k)] = str(v).strip()
    AI_KB_VARS = base_kb
    if ai_prompt_file:
        try:
            p = Path(ai_prompt_file)
            AI_PERSONA_PROMPT_TEMPLATE = p.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("读取 AI 提示词文件失败，回退固定文案: %s", e)
            AI_PERSONA_PROMPT_TEMPLATE = ""
    else:
        AI_PERSONA_PROMPT_TEMPLATE = os.environ.get("DOUYIN_DM_AI_PROMPT", "")

    if not (AI_PERSONA_PROMPT_TEMPLATE or "").strip():
        AI_PERSONA_PROMPT_TEMPLATE = DEFAULT_DM_AI_SYSTEM_PROMPT_ZH.strip()

    AI_UI_PERSONA_EXTRA = (persona_extra or "").strip()
    if not AI_UI_PERSONA_EXTRA and persona_extra_file:
        try:
            AI_UI_PERSONA_EXTRA = Path(persona_extra_file).read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("读取 persona-extra-file 失败: %s", e)
            AI_UI_PERSONA_EXTRA = ""
    if not AI_UI_PERSONA_EXTRA:
        AI_UI_PERSONA_EXTRA = (os.environ.get("DOUYIN_DM_UI_PERSONA", "") or "").strip()


def run_hf_dm_once_shared(
    *,
    message: str = "auto-reply-selenium",
    min_pause: float = 3.0,
    max_pause: float = 5.0,
    use_ai: bool = True,
    ai_prompt_file: str = "",
    persona_extra: str = "",
    persona_extra_file: str = "",
    persona_kb_override: dict[str, str] | None = None,
    quit_browser: bool = False,
    setup_log: bool = False,
) -> dict:
    """
    与 FastAPI / 口播发布 同进程调用：复用 douyin_publish_mcp 全局 driver，不另起 Chrome。
    默认不关闭浏览器，避免打断登录态与其它任务。
    """
    if setup_log:
        setup_logging()
    _apply_hf_ai_globals(
        use_ai=use_ai,
        ai_prompt_file=ai_prompt_file,
        persona_extra=persona_extra,
        persona_extra_file=persona_extra_file,
        persona_kb_override=persona_kb_override,
    )
    mp = max(0.5, float(min_pause))
    xp = max(mp, float(max_pause))
    logger.info(
        "HF 回复内容: %r | 停顿 %.1f~%.1fs | AI=%s | 提示词=%d 字 | 人设补充=%d 字 | quit_browser=%s",
        message,
        mp,
        xp,
        AI_ENABLED,
        len(AI_PERSONA_PROMPT_TEMPLATE or ""),
        len(AI_UI_PERSONA_EXTRA or ""),
        quit_browser,
    )
    driver = ensure_driver()
    try:
        stats = run_once(
            driver=driver,
            message=message,
            min_pause=mp,
            max_pause=xp,
        )
        logger.info(
            "HF 任务结束，总回复数: %d（default=%d, stranger=%d）",
            stats["total"],
            stats["default"],
            stats["stranger"],
        )
        logger.info("HF 统计(JSON): %s", json.dumps(stats, ensure_ascii=False))
        bump_hf_reply_stats(int(stats.get("total", 0) or 0))
        return stats
    finally:
        if quit_browser:
            try:
                driver.quit()
                logger.info("HF 已关闭浏览器（quit_browser=True）")
            except Exception as e:
                logger.warning("HF 关闭浏览器失败（忽略）: %s", e)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HF: Douyin DM auto reply (Selenium). 默认保持浏览器（与主系统共用 douyin_publish_mcp 单例）。"
    )
    parser.add_argument("--message", type=str, default="auto-reply-selenium")
    parser.add_argument("--min-pause", type=float, default=3.0)
    parser.add_argument("--max-pause", type=float, default=5.0)
    parser.add_argument("--use-ai", action="store_true", default=True)
    parser.add_argument("--ai-prompt-file", type=str, default="")
    parser.add_argument(
        "--persona-extra",
        type=str,
        default="",
        help="与 --ai-prompt-file / DOUYIN_DM_AI_PROMPT 合并，追加到 system 提示词（供 UI 人设）",
    )
    parser.add_argument(
        "--persona-extra-file",
        type=str,
        default="",
        help="从文件读取人设补充文本，优先级低于 --persona-extra（非空则仅用命令行）",
    )
    parser.add_argument(
        "--quit-browser",
        action="store_true",
        help="结束后关闭 Selenium 浏览器（会破坏与后端其它功能共用的会话，一般勿用）",
    )
    args = parser.parse_args()

    setup_logging()
    run_hf_dm_once_shared(
        message=args.message,
        min_pause=args.min_pause,
        max_pause=args.max_pause,
        use_ai=bool(args.use_ai),
        ai_prompt_file=args.ai_prompt_file or "",
        persona_extra=args.persona_extra or "",
        persona_extra_file=args.persona_extra_file or "",
        quit_browser=bool(args.quit_browser),
        setup_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
