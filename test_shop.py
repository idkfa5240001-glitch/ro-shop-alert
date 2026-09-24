import os
import json
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COOKIE_STR = os.environ.get("RO_COOKIE", "")
TARGET_ITEM = "神槍手紅色典藏板"

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

def run():
    with sync_playwright() as p:
        print("啟動虛擬 Chrome 瀏覽器...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )

        # 注入登入 Cookie
        if COOKIE_STR:
            cookies = parse_cookies(COOKIE_STR)
            context.add_cookies(cookies)
            print(f"已成功注入 {len(cookies)} 組身分憑證 Cookie")

        page = context.new_page()
        captured_data = []

        # 攔截包含查詢結果的網路封包
        def handle_response(response):
            if "forAjax_shopDeal" in response.url:
                try:
                    data = response.json()
                    items = data.get("dt")
                    if items:
                        captured_data.extend(items)
                except Exception:
                    pass

        page.on("response", handle_response)

        print("正在開啟露天拍賣網頁...")
        page.goto("https://event.gnjoy.com.tw/RoZ/RoZ_ShopSearch", wait_until="networkidle", timeout=60000)

        # 等待網頁前端驗證初始化（轉圈圈驗證完成）
        print("等待前端驗證初始化...")
        page.wait_for_timeout(6000)

        # 輸入關鍵字
        print(f"輸入物品名稱：{TARGET_ITEM}")
        page.fill("#txb_KeyWord", TARGET_ITEM)

        # 點擊查詢按鈕
        print("點擊查詢按鈕...")
        page.click("button:has-text('查詢'), input[value='查詢'], #btn_Search")

        # 等待查詢 API 回傳
        page.wait_for_timeout(8000)

        browser.close()

        if captured_data:
            print(f"✅ 成功攔截到商品筆數: {len(captured_data)}")
            print("\n--- 架上最低價前 3 筆 ---")
            for i, item in enumerate(captured_data[:3], 1):
                refine = f"+{item.get('itemRefining')} " if item.get('itemRefining') else ""
                print(f"【{i}】{refine}{item.get('itemName')} - 單價: {item.get('itemPrice'):,} Z | 商店: {item.get('storeName')}")

            if WEBHOOK_URL:
                lowest = captured_data[0]
                refine = f"+{lowest.get('itemRefining')} " if lowest.get('itemRefining') else ""
                import requests
                msg = (
                    f"🛒 **RO 露天拍賣比價連線成功！**\n"
                    f"物品：`{refine}{lowest.get('itemName')}`\n"
                    f"最低單價：`{lowest.get('itemPrice'):,} Z`\n"
                    f"攤位名稱：`{lowest.get('storeName')}`"
                )
                requests.post(WEBHOOK_URL, json={"content": msg})
                print("已成功發送 Discord 測試通知！")
        else:
            print("❌ 未攔截到商品列表，可能按鈕觸發有誤或需延長等待時間。")

if __name__ == "__main__":
    run()
