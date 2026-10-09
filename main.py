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
        if resp.status_code in [200, 204]:
            print(f"✅ Discord 推播成功 [{item_name}]")
        else:
            print(f"❌ Discord 推播失敗 [{item_name}] 狀態碼: {resp.status_code}")
            print(f"   原因: {resp.text}")
    except Exception as e:
        print(f"❌ Discord 請求異常 [{item_name}]: {e}")

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

    # 1. 露天販售
    if sell_items:
        sell_items.sort(key=lambda x: x.get("itemPrice", 0))
        lowest_sell = sell_items[0].get("itemPrice", 0)
        highest_sell = sell_items[-1].get("itemPrice", 0)

        lines = [f"📉 最低: `{lowest_sell:,} Z` ｜ 📈 最高: `{highest_sell:,} Z`"]
        for i, it in enumerate(sell_items[:10], 1):
            p = it.get("itemPrice", 0)
            s = truncate_text(it.get("storeName", "未知攤位"), 6)
            c = it.get("itemCNT", 1)
            lines.append(f"**{i}.** `{p:,} Z` (x{c}) ｜ *{s}*")

        if len(sell_items) > 10:
            lines.append(f"... 尚有 {len(sell_items) - 10} 筆較高價格")

        fields.append({
            "name": f"🛒 【露天販售】（共 {len(sell_items)} 筆）",
            "value": "\n".join(lines),
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

    total_count = len(sell_items) + len(buy_items)
    embed = {
        "title": f"💎 【材料雙向行情】{item_name}",
        "description": f"目前市場共 **{total_count}** 筆交易（販售 {len(sell_items)} / 收購 {len(buy_items)}）",
        "color": 0x2ECC71 if (new_count > 0 or removed_count > 0) else 0x3498DB,
        "fields": fields,
        "footer": {
            "text": "RO 露天拍賣比價監控 • 30分鐘定期推播"
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    post_discord({"embeds": [embed]}, item_name)

def send_summary_alert(matched_items, target_config, new_items_count, removed_items_count):
    item_name = target_config["itemName"]
    is_card = item_name.endswith("卡片")
    min_r = target_config.get("minRefine", 0)

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
        "description": f"目前架上共 **{len(matched_items)}** 筆符合條件商品",
        "color": 0x2ECC71 if (new_items_count > 0 or removed_items_count > 0) else 0x3498DB,
        "fields": fields,
        "footer": {
            "text": "RO 露天拍賣比價監控 • 30分鐘定期推播"
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    post_discord({"embeds": [embed]}, item_name)

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
    print(f"📋 追蹤清單已載入，共 {len(active_targets)} 個品項")
    if not active_targets:
        print("❌ 無啟用的追蹤品項")
        return

    last_data = load_last_snapshot()
    last_snapshots = last_data.get("snapshots", {})
    current_time = time.time()
    current_snapshots = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )

        if COOKIE_STR:
            context.add_cookies(parse_cookies(COOKIE_STR))

        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        print("🌐 連線至官方拍賣網頁...")
        page.goto("https://event.gnjoy.com.tw/RoZ/RoZ_ShopSearch", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(8000)

        for target in active_targets:
            item_name = target["itemName"]
            is_card = item_name.endswith("卡片")
            exact_query = target.get("exactQuery")
            track_buy_sell = target.get("trackBuyAndSell", False)

            query_text = exact_query if exact_query else (f'"{item_name}"' if is_card else item_name)
            max_price = target.get("maxPrice", 999999999)
            min_refine = target.get("minRefine", 0)
            max_refine = target.get("maxRefine", 10 if not is_card else 0)

            print(f"\n🔍 查詢: {item_name} (送出字串: {query_text})")
            captured_items = search_item_with_pages(page, query_text)
            print(f"📦 收到原始數據: {len(captured_items)} 筆")

            unique_items = []
            seen_ids = set()
            for it in captured_items:
                uid = str(it.get("SSI2")) if it.get("SSI2") else f"{it.get('storeName')}_{it.get('itemPrice')}_{it.get('itemRefining')}_{it.get('itemCNT')}"
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    unique_items.append(it)

            if track_buy_sell:
                sell_items = []
                buy_items = []
                for it in unique_items:
                    raw_name = it.get("itemName", "")
                    if raw_name == item_name:
                        if is_buy_deal(it):
                            buy_items.append(it)
                        else:
                            sell_items.append(it)

                all_tracked = sell_items + buy_items
                current_keys = {
                    f"{it.get('itemName')}_{it.get('itemPrice')}_{it.get('storeName')}"
                    for it in all_tracked
                }
                current_snapshots[item_name] = list(current_keys)

                last_keys = set(last_snapshots.get(item_name, []))
                new_items_count = len(current_keys - last_keys) if last_keys else 0
                removed_items_count = len(last_keys - current_keys) if last_keys else 0

                print(f"📊 分類結果: 販售 {len(sell_items)} 筆 / 收購 {len(buy_items)} 筆")
                send_material_buy_sell_alert(sell_items, buy_items, target, new_items_count, removed_items_count)

            else:
                matched_items = []
                for it in unique_items:
                    r = it.get("itemRefining", 0)
                    p = it.get("itemPrice", 0)
                    raw_name = it.get("itemName", "")

                    if is_buy_deal(it):
                        continue

                    if exact_query:
                        if (min_refine <= r <= max_refine or min_refine == 0) and p <= max_price:
                            matched_items.append(it)
                    elif is_card:
                        if raw_name == item_name and p <= max_price:
                            matched_items.append(it)
                    else:
                        if (raw_name == item_name or raw_name.startswith(f"{item_name} ")) and (min_refine <= r <= max_refine) and (p <= max_price):
                            matched_items.append(it)

                snapshot_id = exact_query if exact_query else item_name
                current_keys = {
                    f"{it.get('itemName')}_+{it.get('itemRefining', 0)}_{it.get('itemPrice')}_{it.get('storeName')}"
                    for it in matched_items
                }
                current_snapshots[snapshot_id] = list(current_keys)

                last_keys = set(last_snapshots.get(snapshot_id, []))
                new_items_count = len(current_keys - last_keys) if last_keys else 0
                removed_items_count = len(last_keys - current_keys) if last_keys else 0

                print(f"📊 符合條件: {len(matched_items)} 筆")
                send_summary_alert(matched_items, target, new_items_count, removed_items_count)

        browser.close()

    if current_snapshots:
        save_snapshot({
            "snapshots": current_snapshots,
            "last_run_time": current_time
        })
    print("\n🏁 任務完成！")

# 直接執行進入點
main()
