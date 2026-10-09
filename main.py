import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COOKIE_STR = os.environ.get("RO_COOKIE", "")
SNAPSHOT_FILE = "last_snapshot.json"

print(f"=== 啟動檢查 ===")
print(f"Webhook 設定狀態: {'已設定' if WEBHOOK_URL else '❌ 未設定 (請檢查 GitHub Secrets)'}")
print(f"Cookie 設定狀態: {'已設定' if COOKIE_STR else '未設定'}")

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
        print("❌ WEBHOOK_URL 為空，無法發送 Discord 通知！")
        return

    item_name = target_config["itemName"]
    fields = []

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

    # 1. 露天販售
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

    # 2. 露天收購
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
        "color": 0x2ECC71 if (new_count > 0 or removed_count > 0) else 0x3498DB,
        "fields": fields,
        "footer": {
            "text": "RO 露天拍賣比價監控 • 30分鐘定期推播"
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    resp = requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=15)
    print(f"📡 Discord 推播狀態碼 [{item_name}]: {resp.status_code}")

def send_summary_alert(matched_items, target_config, new_items_count, removed_items_count):
    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL 為空，無法發送 Discord 通知！")
        return

    item_name = target_config["itemName"]
    is_card = item_name.endswith("卡片")
    min_r = target_config.get("minRefine", 0)

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

    if is_card:
        title = f"🃏 【卡片行情】{item_name}"
    else:
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
            s = truncate_text(it.get("storeName", "未知攤位"), 6)
            c = it.get("itemCNT", 1)

            slots = [it.get(f"slot_{k}") for k in range(1, 5) if it.get(f"slot_{k}")]
            slot_t = f" ({truncate_text('/'.join(slots), 12)})" if slots else ""

            r_str = f"`+{r}` " if r > 0 else ""
            lines.append(f"**{i}.** {r_str}`{p:,} Z` (x{c}) ｜ *{s}*{slot_t}")

        if len(matched_items) > 10:
            lines.append(f"... 尚有 {len(matched_items) - 10} 筆較高價格未顯示")

        fields.append({"name": "📉 架上最低價", "value": f"**{lowest_item.get('itemPrice', 0):,} Z**", "inline": True})
        fields.append({"name": "📈 架上最高價", "value": f"**{highest_item.get('itemPrice', 0):,} Z**", "inline": True})
        fields.append({"name": "📋 架上販售列表（由低至高）", "value": "\n".join(lines), "inline": False})
    else:
        fields.append({"name": "🏪 架上狀況", "value": "*目前架上無任何販售*", "inline": False})

    embed = {
        "title": title,
        "description": f"目前架上共 **{len(matched_items)}** 筆符合條件的商品（30 分鐘定時巡查）",
        "color": 0x2ECC71 if (new_items_count > 0 or removed_items_count > 0) else 0x3498DB,
        "fields": fields,
        "footer": {
            "text": "RO 露天拍賣比價監控 • 30分鐘定期推播"
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    resp = requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=15)
    print(f"📡 Discord 推播狀態碼 [{item_name}]: {resp.status_code}")

def search_item_with_pages(page, query_text):
    captured_items = []

    def handle_response(response):
        if "forAjax_shopDeal" in response.url:
            try:
                data = response.json()
                items = data.get("dt")
                if items:
                    captured_items.extend(items)
            except Exception:
                pass

    page.on("response", handle_response)

    page.fill("#txb_KeyWord", "")
    page.fill("#txb_KeyWord", query_text)
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(7000)

    # 翻頁 (2~5 頁)
    page_click_script = (
        "(pageNum) => {"
        "  const allNodes = Array.from(document.querySelectorAll('a, button, span, li'));"
        "  const pageNode = allNodes.find(el => el.children.length === 0 && el.textContent.trim() === String(pageNum));"
        "  if (pageNode) {"
        "    pageNode.scrollIntoView();"
        "    pageNode.click();"
        "    return true;"
        "  }"
        "  return false;"
        "}"
    )

    for p_num in range(2, 6):
        has_page = page.evaluate(page_click_script, p_num)
        if has_page:
            page.wait_for_timeout(6000)
        else:
            break

    page.remove_listener("response", handle_response)
    return captured_items

def is_buy_deal(item):
    for key in ["dealType", "DealType", "tradeType", "TradeType", "type", "deal_type"]:
        val = str(item.get(key, "")).strip()
        if "收" in val or val in ["1", "buy", "Buy"]:
            return True
        if "販" in val or val in ["2", "sell", "Sell"]:
            return False

    store = str(item.get("storeName", ""))
    if store.startswith("收") or "高收" in store or "收購" in store:
        return True

    return False

def main():
    if not os.path.exists("watchlist.json"):
        print("❌ 未找到 watchlist.json 設定檔")
        return

    with open("watchlist.json", "r", encoding="utf-8") as f:
        watchlist = json.load(f)

    active_targets = [t for t in watchlist if t.get("enabled", True)]
    print(f"📋 載入追蹤品項數量: {len(active_targets)}")
