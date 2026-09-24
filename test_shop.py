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

# 帶入從 cURL 抓取到的有效 recaptcha 與 _Action 進行驗證
payload = {
    "div_svr": "529",
    "div_storetype": "2",
    "txb_KeyWord": "神槍手紅色典藏板",
    "row_start": "1",
    "sort_by": "itemPrice",
    "sort_desc": "",
    "recaptcha": "1.J35_NH6tvLVt9QNxHkJnZUFKTePkn-iZVKpTp4gD1FPWo4-U69GdwjyFKYJNgY7xH07GOpkFtJISNOI4kyDVMBX6UDFLL2UwEMQuxc0K7w5UUvxl-H5qguEm3x1WmUV_YOzOF4xY8weeCeVZZuxR5Wq3m6ArPPUzlqgre4p0c4if1vjKdrihwQuNm9S5YdiyOR7KD0I88uWea0aV-HFS4qOXAlbuWAtI6YNxBe109z_l22w6XpRMMYEsda4yEV_UHKFx1XVDgfEd39wom2bNZ38hLwoqeNcngEIoDHFTB6TNXSjWAqbw_7BZQPolFDys-3pSJOKgh9iTUeBnVX5K1HLdA1J_5QOW21Hbz1XDXVJdR19zeyQvanzRhoN_A0VSUAd5c_oqdD_6yRVXIE3AIuOWLaGTKPqozmfyfChasag8TVJ2SKN5fK_gdXui9oKCndLVFPBgzu85Q1crY_ieAHSOOOsG7HzLKFeEEZJDXSns97XmYKDYfS-Khy994rATMvj0HX2z5CTAJQV6FFpe03pq2WTws6NLtseHxUcRG51V97Rj_T22Mw160TzKlmL5Ni1_NIPaeudyi5ifooA-rEltHjWu-Nm9MlE0AcXjDvm9O53jwtLDGhMS063xCBgku2nopE1TxgVvm8Mmozyl1EGwKAsKrDhYrtq2KQkINJY.x0NQRbivJ3NTbDe_ohW0bw.db149ac5a9a228468b592aa83dba4deb70b5255bc0cd27c7e29e36326856304c",
    "_Action": "znMZTidkYDUM1OxkWoPyLDSSY+DiLb5c/35xQkyZ1/7tMXH6/B6C+KT6zIfVHA9DfZDEkxfMdbtjIs7B4tLTXw=="
}

print("正在發送帶身分憑證與驗證碼的查詢請求...")
res = requests.post(API_URL, json=payload, headers=headers, timeout=15)

print("HTTP 狀態碼:", res.status_code)

try:
    data = res.json()
    items = data.get("dt")
    
    if items:
        print(f"✅ 成功抓取到商品筆數: {len(items)}")
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
        print("❌ 未取得商品列表，官方回傳訊息:", res.text)
except Exception as e:
    print("❌ 解析失敗:", e, "回傳文字:", res.text)
