import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COOKIE_STR = os.environ.get("RO_COOKIE", "")
SEEN_FILE = "seen_deals.json"

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

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen(seen_set):
    recent = list(seen_set)[-500:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(recent, f, ensure_ascii=False, indent=2)

def send_summary_alert(matched_items, target_config):
    if not WEBHOOK_URL or not matched_items:
        return

    # 按單價由低到高排序
    matched_items.sort(key=lambda x: x.get("itemPrice", 0))

    lowest_item = matched_items[0]
    highest_item = matched_items[-1]

    min_r = target_config.get("minRefine", 0)
    max_r = target_config.get("maxRefine", 99)
    if min_r == max_r and min_r > 0:
        refine_str = f"+{min_r} "
    elif min_r > 0:
        refine_str = f"+{min_r}~+{max_r} "
    else:
        refine_str = ""

    title = f"📊 【行情回報】{refine_str}{target_config['itemName']}"

    # 組合架上清單（最多列出前 10 筆）
    lines = []
    for i, item in enumerate(matched_items[:10], 1):
        price = item.get("itemPrice", 0)
        store = item.get("storeName", "未知攤位")
        cnt = item.get("itemCNT", 1)
        refine = f"+{item.get('itemRefining')} " if item.get("itemRefining") else ""
        slots = [item.get(f"slot_{k}") for k in range(1, 5) if item.get(f"slot_{k}")]
        slot_text = f" ({'/'.join(slots)})" if slots else ""
        lines.append(f"**{i}.** `{price:,} Z` (x{cnt}) - {store}{slot_text}")

    if len(matched_items) > 10:
        lines.append(f"... 尚有 {len(matched_items) - 10} 筆較高價格未顯示")

    list_content = "\n".join(lines)

    embed = {
        "title": title,
        "description": f"目前架上共找到 **{len(matched_items)}** 筆符合條件的商品！",
        "color": 0x3498DB,
        "fields": [
            {"name": "📉 架上最低價", "value": f"**{lowest_item.get('itemPrice', 0):,} Z**", "inline": True},
            {"name": "📈 架上最高價", "value": f"**{highest_item.get('itemPrice', 0):,} Z**", "inline": True},
            {"name": "🏪 架上所有販售列表（由低至高）", "value": list_content, "inline": False}
        ],
        "footer": {
            "text": "RO 露天拍賣比價監控"
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)

def main():
    if not os.path.exists("watchlist.json"):
        print("未找到 watchlist.json 設定檔")
        return

    with open("watchlist.json", "r", encoding="utf-8") as f:
        watchlist = json.load(f)

    active_targets = [t for t in watchlist if t.get("enabled", True)]
    if not active_targets:
        print("無啟用的追蹤品項")
        return

    seen_deals = load_seen()
    new_seen = set(seen_deals)

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

        print("開啟露天拍賣平台...")
        page.goto("https://event.gnjoy.com.tw/RoZ/RoZ_ShopSearch", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(8000)

        for target in active_targets:
            keyword = target["itemName"]
            max_price = target.get("maxPrice", 999999999)
            min_refine = target.get("minRefine", 0)
            max_refine = target.get("maxRefine", 99)

            print(f"\n🔍 正在查詢：{keyword} (精煉條件: +{min_refine} ~ +{max_refine})")

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
            page.fill("#txb_KeyWord", keyword)
            page.wait_for_timeout(1000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(7000)

            page.remove_listener("response", handle_response)

            matched_items = []
            has_new_item = False

            for item in captured_items:
                price = item.get("itemPrice", 0)
                refine = item.get("itemRefining", 0)
                ssi2 = item.get("SSI2", "")
                unique_key = f"{item.get('itemName')}_{refine}_{price}_{item.get('storeName')}_{ssi2}"

                # 篩選精煉度與價格區間
                if min_refine <= refine <= max_refine and price <= max_price:
                    matched_items.append(item)
                    if unique_key not in seen_deals:
                        has_new_item = True
                        new_seen.add(unique_key)

            if matched_items:
                if has_new_item:
                    print(f"🎯 發現有新上架或變動，發送彙整行情推播（共 {len(matched_items)} 筆）！")
                    send_summary_alert(matched_items, target)
                else:
                    print(f"⚪ 架上共 {len(matched_items)} 筆符合，但無新異動，略過通知。")
            else:
                print(f"目前架上沒有符合 +{min_refine} ~ +{max_refine} 的商品。")

        browser.close()

    save_seen(new_seen)
    print("\n比價任務執行完畢！")

if __name__ == "__main__":
    main()
