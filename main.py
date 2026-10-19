import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COOKIE_STR = os.environ.get("RO_COOKIE", "")
SNAPSHOT_FILE = "last_snapshot.json"

print("=== 啟動檢查 ===")
print(f"Webhook: {'已設定' if WEBHOOK_URL else '❌ 未設定'}")
print(f"Cookie: {'已設定' if COOKIE_STR else '未設定'}")

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

def send_material_buy_sell_alert(sell_items, buy_items, target_config, new_count, removed_count):
    item_name = target_config["itemName"]
    fields = []

    diff_texts = []
    if new_count > 0:
        diff_texts.append(f"🟢 新增: {new_count} 筆")
    if removed_count > 0:
        diff_texts.append(f"🔴 售出/下架: {removed_count} 筆")
    diff_summary = " | ".join(diff_texts) if diff_texts else "⚪ 架上狀況: 價格與數量持平"

    fields.append({
        "name": "🔔 本次異動備註",
        "value": diff_summary,
        "inline": False
    })

    # 1. 露天收購（置頂在最上方）
    if buy_items:
        buy_items.sort(key=lambda x: x.get("itemPrice", 0), reverse=True)
        highest_buy = buy_items[0].get("itemPrice", 0)
        lowest_buy = buy_items[-1].get("itemPrice", 0)

        lines = [f"📈 最高收購: `{highest_buy:,} Z` ｜ 📉 最低收購: `{lowest_buy:,} Z`"]
        for i, it in enumerate(buy_items[:10], 1):
            p = it.get("itemPrice", 0)
            s = truncate_text(it.get("storeName", "未知攤位"), 6)
            c = it.get("itemCNT", 1)
            lines.append(f"**{i}.** `{p:,} Z` (x{c}) ｜ *{s}*")

        if len(buy_items) > 10:
            lines.append(f"... 尚有 {len(buy_items) - 10} 筆較低價格")

        fields.append({
            "name": f"💰 【露天收購】（共 {len(buy_items)} 筆）",
            "value": "\n".join(lines),
            "inline": False
        })
    else:
        fields.append({
            "name": "💰 【露天收購】",
            "value": "*目前無任何收購店家*",
            "inline": False
        })

    # 2. 露天販售（放在下方）
    if sell_items:
        sell_items.sort(key=lambda x: x.get("
