import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
COOKIE_STR = os.environ.get("RO_COOKIE", "")
SNAPSHOT_FILE = "last_snapshot.json"

print("=== 啟動檢查 ===")
print(f"Webhook 狀態: {'已設定' if WEBHOOK_URL else '❌ 未讀取到'}")
print(f"Cookie 狀態: {'已設定' if COOKIE_STR else '未設定'}")

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

def send_summary_alert(matched_items, target_config, new_items_count, removed_items_count):
    item_name = target_config["itemName"]
    is_card = item_name.endswith("卡片")
    min_price = target_config.get("minPrice", 0)

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
    desc_extra = f"（門檻: ≥ {min_price // 100000000}億 Z）" if min_price >= 100000000 else ""

    if matched_items:
        matched_items.sort(key=lambda x: x.get("itemPrice", 0))
        lowest_item = matched_items[0]
        highest_item = matched_items[-1]

        lines = []
        for i, it in enumerate(matched_items[:10], 1):
            p = it.get("itemPrice", 0)
            r = it.get("itemRefining", 0)
            raw_title = it.get("itemName", item_name)
            slot_info = it.get("slotInfo", "")
            s = truncate_text(it.get("storeName", "未知攤位"), 6)
            c = it.get("itemCNT", 1)

            slot_t = f" `[{slot_info}]`" if slot_info and slot_info != "-" else ""
            r_str = f"`+{r}` " if r > 0 else ""
            lines.append(f"**{i}.** {r_str}`{p:,} Z` (x{c}) ｜ {raw_title}{slot_t} ｜ *{s}*")

        if len(matched_items) > 10:
            lines.append(f"... 尚有 {len(matched_items) - 10} 筆較高價格未顯示")

        fields.append({"name": "📉 架上最低價", "value": f"**{lowest_item.get('itemPrice', 0):,} Z**", "inline": True})
        fields.append({"name": "📈 架上最高價", "value": f"**{highest_item.get('itemPrice', 0):,} Z**", "inline": True})
        fields.append({"name": "📋 架上販售列表（由低至高）", "value": "\n".join(lines), "inline": False})
    else:
        fields.append({"name": "🏪 架上狀況", "value": f"*目前架上無符合條件的商品 {desc_extra}*", "inline": False})

    embed = {
        "title": f"{title} {desc_extra}".strip(),
        "description": f"目前架上共 **{len(matched_items)}** 筆符合條件商品",
        "color": 0x2ECC71 if (new_items_count > 0 or removed_items_count > 0) else 0x3498DB,
        "fields": fields,
        "footer": {
            "text": "RO 露天拍賣比價監控 • 30分鐘定期推播"
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    post_discord({"embeds": [embed]}, item_name)

def scrape_dom_table(page):
    return page.evaluate("""() => {
        const rows = document.querySelectorAll('table tbody tr');
        const list = [];
        rows.forEach(tr => {
            const cols = tr.querySelectorAll('td');
            if (cols.length >= 6) {
                const sName = cols[0].innerText.trim();
                const iName = cols[1].innerText.trim();
                const sInfo = cols[2].innerText.trim(); // 第 3 欄：插槽/附魔/卡片資訊
                const pText = cols[3].innerText.replace(/[^0-9]/g, '');
                const cText = cols[4].innerText.replace(/[^0-9]/g, '');
                const dType = cols[5].innerText.trim();

                let itemRefining = 0;
                const refineMatch = iName.match(/^\\+(\\d+)/);
                if (refineMatch) {
                    itemRefining = parseInt(refineMatch[1], 10);
                }

                list.push({
                    storeName: sName,
                    itemName: iName,
                    slotInfo: sInfo,
                    fullDesc: iName + ' ' + sInfo, // 品名 + 附魔全文字串
                    itemPrice: parseInt(pText, 10) || 0,
                    itemCNT: parseInt(cText, 10) || 1,
                    itemRefining: itemRefining,
                    isBuy:
