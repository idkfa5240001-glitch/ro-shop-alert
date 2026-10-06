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

def truncate_text(text, max_len=5):
    """通用字串截斷函數"""
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
    """專門處理材料/消耗品之 販售與收購 雙向 10 筆列表排版"""
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

    # 1. 販售區塊（由低到高排序）
    if sell_items:
        sell_items.sort(key=lambda x: x.get("itemPrice", 0))
        lowest_sell = sell_items[0].get("itemPrice", 0)
        highest_sell = sell_items[-1].get("itemPrice", 0)

        sell_lines = [f"📉 最低: `{lowest_sell:,} Z` ｜ 📈 最高: `{highest_sell:,} Z`"]
        for i, it in enumerate(sell_items[:10], 1):
            p = it.get("itemPrice", 0)
            s = truncate_text(it.get("storeName", "未知攤位"), 5)
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

    # 2. 收購區塊（由高到低排序，收購出價最高者排前面）
    if buy_items:
        buy_items.sort(key=lambda x: x.get("itemPrice", 0), reverse=True)
        highest_buy = buy_items[0].get("itemPrice", 0)
        lowest_buy = buy_items[-1].get("itemPrice", 0)

        buy_lines = [f"📈 最高收購: `{highest_buy:,} Z` ｜ 📉 最低收購: `{lowest_buy:,} Z`"]
        for i, it in enumerate(buy_items[:10], 1):
            p = it.get("itemPrice", 0)
            s = truncate_text(it.get("storeName", "未知攤位"), 5)
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
        "color": 0x2ECC71 if (new_count > 0 or removed_count > 0) else 0x3498DB,
        "fields": fields,
        "footer": {
            "text": "RO 露天拍賣比價監控 • 30分鐘定期推播"
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)

def send_summary_alert(matched_items, target_config, new_items_count, removed_items_count):
    if not WEBHOOK_URL:
        return

    item_name = target_config["itemName"]
    is_card = item_name.endswith("卡片")
    min_r = target_config.get("minRefine", 0)
    max_r = target_config.get("maxRefine", 10)

    is_multi_refine = (not is_card) and (max_r > min_r) and (max_r > 0)

    diff_texts = []
    if new_items_count > 0:
        diff_texts.append(f"🟢 **新增上架**: {new_items_count} 筆")
    if removed_items_count > 0:
        diff_texts.append(f"🔴 **已售出/下架**: {removed_items_count} 筆")
    diff_summary = " | ".join(diff_texts) if diff_texts else "⚪ **架上狀況**: 價格與數量無變動（持平）"

    fields = [
        {
            "name": "🔔 本次異動備註",
            "value": diff_summary,
            "inline": False
        }
    ]

    DIVIDER_LINE = "──────────────────"

    if is_card:
        title = f"🃏 【卡片行情】{item_name}"
        if matched_items:
            matched_items.sort(key=lambda x: x.get("itemPrice", 0))
            lowest_item = matched_items[0]
            highest_item = matched_items[-1]

            lines = []
            for i, it in enumerate(matched_items[:10], 1):
                p = it.get("itemPrice", 0)
                s = truncate_text(it.get("storeName", "未知攤位"), 5)
                c = it.get("itemCNT", 1)
                lines.append(f"**{i}.** `{p:,} Z` (x{c}) ｜ *{s}*")

            if len(matched_items) > 10:
                lines.append(f"... 尚有 {len(matched_items) - 10} 筆較高價格未顯示")

            fields.append({"name": "📉 架上最低價", "value": f"**{lowest_item.get('itemPrice', 0):,} Z**", "inline": True})
            fields.append({"name": "📈 架上最高價", "value": f"**{highest_item.get('itemPrice', 0):,} Z**", "inline": True})
            fields.append({"name": "📋 架上販售列表（由低至高）", "value": "\n".join(lines), "inline": False})
        else:
            fields.append({"name": "🏪 架上狀況", "value": "*目前架上無任何販售*", "inline": False})

    elif not is_multi_refine:
        refine_tag = f"+{min_r} " if (min_r > 0 and not item_name.startswith("+")) else ""
        title = f"🛡️ 【裝備行情】{refine_tag}{item_name}"
        if matched_items:
            matched_items.sort(key=lambda x: x.get("itemPrice", 0))
            lowest_item = matched_items[0]
            highest_item = matched_items[-1]

            lines = []
            for i, it in enumerate(matched_items[:10], 1):
                p = it.get("itemPrice", 0)
                r = it.get("itemRefining", 0)
                s = truncate_text(it.get("storeName", "未知攤位
