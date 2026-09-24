import os
import json
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
TARGET_ITEM = "神槍手紅色典藏板"

def run():
    with sync_playwright() as p:
        print("啟動虛擬瀏覽器中...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        captured_data = []

        # 攔截包含查詢結果的網路封包
        def handle_response(response):
            if "forAjax_shopDeal" in response.url:
                try:
                    data = response.json()
                    items = data.get("dt", [])
                    if items:
                        captured_data.extend(items)
                except Exception:
                    pass

        page.on("response", handle_response)

        print("正在載入露天拍賣網頁...")
        page.goto("https://event.gnjoy.com.tw/RoZ/RoZ_ShopSearch", wait_until="networkidle", timeout=60000)

        # 輸入關鍵字
        print(f"輸入搜尋物品：{TARGET_ITEM}")
        page.fill("#txb_KeyWord", TARGET_ITEM)

        # 點擊查詢按鈕
        print("觸發查詢按鈕...")
        page.click("button:has-text('查詢'), input[type='button'][value='查詢']")

        # 等待資料回傳
        page.wait_for_timeout(8000)

        browser.close()

        print(f"✅ 成功攔截到商品筆數: {len(captured_data)}")
        if captured_data:
            print("\n--- 架上最低價前 3 筆 ---")
            for i, item in enumerate(captured_data[:3], 1):
                refine = f"+{item.get('itemRefining')} " if item.get('itemRefining') else ""
                print(f"【{i}】{refine}{item.get('itemName')} - 單價: {item.get('itemPrice'):,} Z | 商店: {item.get('storeName')}")
        else:
            print("❌ 未攔截到資料，可能是驗證碼阻擋或元素選取器需微調")

if __name__ == "__main__":
    run()
