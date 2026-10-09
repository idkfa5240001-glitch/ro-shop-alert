import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COOKIE_STR = os.environ.get("RO_COOKIE", "")
SNAPSHOT_FILE = "last_snapshot.json"

def parse_cookies(cookie_string):
    cookies = []
    items = cookie_string.split(";")
    for item in items:
        if "=" in item:
            name, value = item.strip().split("=", 1)
            cookies.append({
                "name": name,
                "value": value,
                "domain": "event.gnjoy.com.tw",
                "path": "/"
            })
    return cookies

def load_last_snapshot():
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_snapshot(snapshot_dict):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot_dict, f, ensure_ascii=False, indent=2)

def truncate_text(text, max_len=6):
    if not text:
        return ""
    text = str(text).strip()
    if len(text) > max_len:
        return f"{text[:max_len]}.."
    return text

def send_login_alert():
    if not WEBHOOK_URL:
        return
    embed = {
        "title": "⚠️ RO 拍賣監控：登入憑證失效！",
        "description": "系統抓取不到拍賣數據，請前往網頁重新登入一次以延長 Session。",
        "color": 0xE74C3C,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)

def send_material_buy_sell_alert(sell_items, buy_items, target_config, new_count, removed_count):
    """材料/消耗品專用：販售與收購 雙向各10筆排版"""
    if not WEBHOOK_URL:
        return

    item_name = target_config["itemName"]
    fields = []

    # 異動備註
    diff_texts = []
    if new_count > 0:
        diff_texts.append(f"🟢 **新增上架/收購**: {new_count} 筆")
    if removed_count > 0:
        diff_texts.append(f"🔴 **已售出/下架**: {removed_count} 筆")
    diff_summary = " | ".join(diff_texts) if diff_texts else "⚪ **架上狀況**: 價格與數量無變動（持平）"

    fields.append({
        "name": "🔔 本次異動備註",
        "value": diff_summary,
        "inline": False
    })

    # 1. 露天販售區塊（由低到高排序）
    if sell_items:
        sell_items.sort(key=lambda x: x.get("itemPrice", 0))
        lowest_sell = sell_items[0].get("itemPrice", 0)
        highest_sell = sell_items[-1].get("itemPrice", 0)

        sell_lines = [f"📉 最低: `{lowest_sell:,} Z` ｜ 📈 最高: `{highest_sell:,} Z`"]
        for i, it in enumerate(sell_items[:10], 1):
            p = it.get("itemPrice", 0)
            s = truncate_text(it.get("storeName", "未知攤位"), 6)
            c
