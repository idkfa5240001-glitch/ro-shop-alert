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
    for item in cookie_string.split(";"):
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
    text = str(text or "").strip()
    return f"{text[:max_len]}.." if len(text) > max_len else text

def post_discord(payload, item_name):
    if not WEBHOOK_URL:
        print(f"❌ 無法推播 [{item_name}]：WEBHOOK 為空")
        return
    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
        print(f"📡 Discord 回傳 [{item_name}]: HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌ 請求異常 [{item_name}]: {e}")

def send_summary_alert(matched_items, target_config, new_items_count, removed_items_count):
    item_name = target_config["itemName"]
    is_card = "卡片" in item_name

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

    if matched_items:
        matched_items.sort(key=lambda x: x.get("itemPrice", 0))
        lowest_item = matched_items[0]
        highest_item = matched_items[-1]

        lines = []
        for i, it in enumerate(matched_items[:10], 1):
            p = it.get("itemPrice", 0)
            r = it.get("itemRefining", 0)
            base_name = it.get("itemName", item_name)
            enchants = it.get("enchants", [])
            s = truncate_text(it.get("storeName", "未知攤位"), 6)
            c = it.get("itemCNT", 1)

            r_str = f"`+{r}` " if r > 0 else ""
            enchant_str = f" (`{', '.join(enchants)}`)" if enchants else ""
            lines.append(f"**{i}.** {r_str}`{p:,} Z` (x{c}) ｜ {base_name}{enchant_str} ｜ *{s}*")

        if len(matched_items) > 10:
            lines.append(f"... 尚有 {len(matched_items) - 10} 筆較高價格未顯示")

        fields.append({"name": "📉 架上最低價", "value": f"**{lowest_item.get('itemPrice', 0):,} Z**", "inline": True})
        fields.append({"name": "📈 架上最高價", "value": f"**{highest_item.get('itemPrice', 0):,} Z**", "inline": True})
        fields.append({"
