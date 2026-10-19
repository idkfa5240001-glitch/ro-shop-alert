import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COOKIE_STR = os.environ.get("RO_COOKIE", "")
SNAPSHOT_FILE = "last_snapshot.json"

print("=== 啟動檢查 ===")
print(f"Webhook 狀態: {'已設定' if WEBHOOK_URL else '❌ 未讀取到'}")
print(f"Cookie 狀態: {'已設定' if COOKIE_STR else '未設定'}")

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
    return f"{text[:max_len]}.." if len(text) > max_len else text

def post_discord(payload, item_name):
    if not WEBHOOK_URL:
        print(f"❌ 無法推播 [{item_name}]：WEBHOOK 為空")
        return
    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
        print(f"📡 Discord 回傳 [{item_name}]: HTTP {resp.status_code}")
        if resp.status_code not in [200, 204]:
            print(f"   ❌ 錯誤訊息: {resp.text}")
    except Exception as e:
        print(f"❌ 請求異常 [{item_name}]: {e}")

def send_summary_alert(matched_items, target_config, new_items_count, removed_items_count):
    item_name = target_config["itemName"]
    is_card = item_name.endswith("卡片")
    min_price = target_config.get("minPrice", 0)

    diff_texts = []
    if new_items_count > 0:
        diff_texts.append(f"🟢 新增: {new_items_count} 筆")
    if removed_items_count > 0:
        diff_texts.append(f"🔴 售出/下架: {removed_items_count} 筆")
    diff_summary = " | ".join(diff_texts) if diff_texts else "⚪ 架上狀況: 價格與數量持平"

    fields = [
        {
            "name": "🔔 本次異動備註",
            "value": diff_summary,
            "inline": False
        }
    ]

    title = f"🃏 【卡片行情】{item_name}" if is_card else f"🛡️ 【裝備行情】{item_name}"
    desc_extra = f"（門檻: ≥ {min_price // 100000000}億 Z）" if min_price >= 100000000 else ""

    if matched_items:
        matched_items.sort(key=lambda x: x.get("itemPrice", 0))
        lowest_item = matched_items[0]
        highest_item = matched_items[-1]

        lines = []
        for i, it in enumerate(matched_items[:10], 1):
