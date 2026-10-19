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
    js_code = (
        "() => {"
        "  const rows = document.querySelectorAll('table tbody tr');"
        "  const list = [];"
        "  rows.forEach(tr => {"
        "    const cols = tr.querySelectorAll('td');"
        "    if (cols.length >= 6) {"
        "      const sName = cols[0].innerText.trim();"
        "      const iName = cols[1].innerText.trim();"
        "      const sInfo = cols[2].innerText.trim();"
        "      const pText = cols[3].innerText.replace(/[^0-9]/g, '');"
        "      const cText = cols[4].innerText.replace(/[^0-9]/g, '');"
        "      const dType = cols[5].innerText.trim();"
        "      let itemRefining = 0;"
        "      const refineMatch = iName.match(/^\\+(\\d+)/);"
        "      if (refineMatch) {"
        "        itemRefining = parseInt(refineMatch[1], 10);"
        "      }"
        "      list.push({"
        "        storeName: sName,"
        "        itemName: iName,"
        "        slotInfo: sInfo,"
        "        fullDesc: iName + ' ' + sInfo,"
        "        itemPrice: parseInt(pText, 10) || 0,"
        "        itemCNT: parseInt(cText, 10) || 1,"
        "        itemRefining: itemRefining,"
        "        isBuy: dType.includes('收')"
        "      });"
        "    }"
        "  });"
        "  return list;"
        "}"
    )
    return page.evaluate(js_code)

def search_item(page, query_text):
    page.fill("#txb_KeyWord", "")
    page.fill("#txb_KeyWord", query_text)
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(7000)

    all_items = []
    dom_items = scrape_dom_table(page)
    all_items.extend(dom_items)

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
            all_items.extend(scrape_dom_table(page))
        else:
            break

    return all_items

def main():
    print("▶ 進入 main() 流程")
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

            query_text = exact_query if exact_query else (f'"{item_name}"' if is_card else item_name)
            min_price = target.get("minPrice", 0)
            max_price = target.get("maxPrice", 999999999)
            min_refine = target.get("minRefine", 0)
            max_refine = target.get("maxRefine", 20 if not is_card else 0)

            print(f"\n🔍 查詢: {item_name} (送出字串: {query_text})")
            captured_items = search_item(page, query_text)
            print(f"📦 收到數據筆數: {len(captured_items)}")

            unique_items = []
            seen_ids = set()
            for it in captured_items:
                uid = f"{it.get('storeName')}_{it.get('itemName')}_{it.get('slotInfo')}_{it.get('itemPrice')}_{it.get('itemCNT')}_{it.get('isBuy')}"
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    unique_items.append(it)

            matched_items = []
            for it in unique_items:
                r = it.get("itemRefining", 0)
                p = it.get("itemPrice", 0)
                raw_name = it.get("itemName", "")
                full_text = it.get("fullDesc", "")

                # 排除收購攤
                if it.get("isBuy"):
                    continue

                # 價格區間過濾
                if not (min_price <= p <= max_price):
                    continue

                if exact_query:
                    keywords = [k.strip('"').strip() for k in exact_query.split("%") if k.strip('"').strip()]
                    match_all = all(kw in full_text for kw in keywords)

                    if not match_all and any(" " in kw for kw in keywords):
                        full_text_nospace = full_text.replace(" ", "")
                        match_all = all(kw.replace(" ", "") in full_text_nospace for kw in keywords)

                    if match_all and (min_refine <= r <= max_refine or min_refine == 0):
                        matched_items.append(it)
                elif is_card:
                    if raw_name == item_name:
                        matched_items.append(it)
                else:
                    if (raw_name == item_name or raw_name.startswith(f"{item_name} ")) and (min_refine <= r <= max_refine):
                        matched_items.append(it)

            snapshot_id = exact_query if exact_query else item_name
            current_keys = {
                f"{it.get('itemName')}_{it.get('slotInfo')}_+{it.get('itemRefining', 0)}_{it.get('itemPrice')}_{it.get('storeName')}"
                for it in matched_items
            }
            current_snapshots[snapshot_id] = list(current_keys)

            last_keys = set(last_snapshots.get(snapshot_id, []))
            new_items_count = len(current_keys - last_keys) if last_keys else 0
            removed_items_count = len(last_keys - current_keys) if last_keys else 0

            print(f"📊 符合條件 (≥{min_price:,} Z): {len(matched_items)} 筆")
            send_summary_alert(matched_items, target, new_items_count, removed_items_count)
            time.sleep(2)

        browser.close()

    if current_snapshots:
        save_snapshot({
            "snapshots": current_snapshots,
            "last_run_time": current_time
        })
    print("\n🏁 任務完成！")

main()
