import os
import requests
import json

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COOKIE = os.environ.get("RO_COOKIE", "")
TOKEN = os.environ.get("RO_VERIFICATION_TOKEN", "")

API_URL = "https://event.gnjoy.com.tw/RoZ/RoZ_ShopSearch/forAjax_shopDeal"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    "Referer": "https://event.gnjoy.com.tw/RoZ/RoZ_ShopSearch",
    "Origin": "https://event.gnjoy.com.tw",
    "Content-Type": "application/json; charset=UTF-8",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "requestverificationtoken": TOKEN,
    "Cookie": COOKIE
}

# 測試關鍵字：神槍手紅色典藏板（西格倫 529）
payload = {
    "div_svr": "529",
    "div_storetype": "2",
    "txb_KeyWord": "神槍手紅色典藏板",
    "row_start": "1",
    "sort_by": "itemPrice",
    "sort_desc": "",
    "recaptcha": "",
    "_Action": "znMZTidkYDUM1OxkWoPyLDSSY+DiLb5c/35xQkyZ1/7tMXH6/B6C+KT6zIfVHA9DfZDEkxfMdbtjIs7B4tLTXw=="
}

print("正在發送帶身分憑證的查詢請求...")
res = requests.post(API_URL, json=payload, headers=headers, timeout=15)

print("HTTP 狀態碼:", res.status_code)

try:
    data = res.json()
    items = data.get("dt", [])
    print(f"✅ 成功抓取到商品筆數: {len(items)}")
    
    if items:
        print("\n--- 架上最低價前 3 筆 ---")
        for i, item in enumerate(items[:3], 1):
            refine = f"+{item.get('itemRefining')} " if item.get('itemRefining') else ""
            print(f"【{i}】{refine}{item.get('itemName')} - 單價: {item.get('itemPrice'):,} Z | 商店: {item.get('storeName')}")
            
        if WEBHOOK_URL:
            lowest = items[0]
            refine = f"+{lowest.get('itemRefining')} " if lowest.get('itemRefining') else ""
            msg = (
                f"🛒 **RO 露天拍賣比價連線成功！**\n"
                f"物品：`{refine}{lowest.get('itemName')}`\n"
                f"最低單價：`{lowest.get('itemPrice'):,} Z`\n"
                f"攤位名稱：`{lowest.get('storeName')}`"
            )
            requests.post(WEBHOOK_URL, json={"content": msg})
            print("已成功發送 Discord 測試通知！")
    else:
        print("未取得資料，回傳內容:", res.text[:200])
except Exception as e:
    print("❌ 解析失敗:", e, "回傳文字:", res.text[:200])
