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

def send_material_buy_sell_alert(sell_items, buy_items, target_config, new_count, removed_count):
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

    # 1. 販售區塊（由低到高）
    if sell_items:
        sell_items.sort(key=lambda x: x.get("itemPrice", 0))
        lowest_sell = sell_items[0].get("itemPrice", 0)
        highest_sell = sell_items[-1].get("itemPrice", 0)

        sell_lines = [f"📉 最低: `{lowest_sell:,} Z` ｜ 📈 最高: `{highest_sell:,} Z`"]
        for i, it in enumerate(sell_items[:10], 1):
            p = it.get("itemPrice", 0)
            s = truncate_text(it.get("storeName", "未知攤位"), 6)
            c = it.get("itemCNT", 1)
            sell_lines.append(f"**{i}.** `{p:,} Z` (x{c}) ｜ *{s}*")

        if len(sell_items) > 10:
            sell_lines.append(f"... 尚有 {len(sell_items) - 10} 筆較高販售價格")

        fields.append({
            "name": f"🛒 【露天販售】（共 {len(sell_items)} 筆）",
            "value": "\n".join(sell_lines),
            "inline": False
        })
    else:
        fields.append({
            "name": "🛒 【露天販售】",
            "value": "*目前架上無任何販售*",
            "inline": False
        })

    # 2. 收購區塊（由高到低，收購價高者優先）
    if buy_items:
        buy_items.sort(key=lambda x: x.get("itemPrice", 0), reverse=True)
        highest_buy = buy_items[0].get("itemPrice", 0)
        lowest_buy = buy_items[-1].get("itemPrice", 0)

        buy_lines = [f"📈 最高收購: `{highest_buy:,} Z` ｜ 📉 最低收購: `{lowest_buy:,} Z`"]
        for i, it in enumerate(buy_items[:10], 1):
            p = it.get("itemPrice", 0)
            s = truncate_text(it.get("storeName", "未知攤位"), 6)
            c = it.get("itemCNT", 1)
            buy_lines.append(f"**{i}.** `{p:,} Z` (x{c}) ｜ *{s}*")

        if len(buy_items) > 10:
            buy_lines.append(f"... 尚有 {len(buy_items) - 10} 筆較低收購價格")

        fields.append({
            "name": f"💰 【露天收購】（共 {len(buy_items)} 筆）",
            "value": "\n".join(buy_lines),
            "inline": False
        })
    else:
        fields.append({
            "name": "💰 【露天收購】",
            "value": "*目前無任何收購店家*",
            "inline": False
        })

    total_count = len(sell_items) + len(buy_items)
    embed = {
        "title": f"💎 【材料雙向行情】{item_name}",
        "description": f"目前市場共 **{total_count}** 筆交易資訊（販售 {len(sell_items)} / 收購 {len(buy_items)}）",
        "color":
