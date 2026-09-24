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

def send_summary_alert(matched_items, target_config, new_items_count, removed_items_count):
    if not WEBHOOK_URL:
        return

    min_r = target_config.get("minRefine", 7)
    max_r = target_config.get("maxRefine", 10)
    title = f"📊 【即時行情定時報】+{min_r}~+{max_r} {target_config['itemName']}"

    diff_texts = []
    if new_items_count > 0:
        diff_texts.append(f"🟢 **新增上架**: {new_items_count} 筆")
    if removed_items_count > 0:
        diff_texts.append(f"🔴 **已售出/下架**: {removed_items_count} 筆")
    if new_items_count == 0 and removed_items_count == 0:
        diff_summary = "⚪ **架上狀況**: 價格與數量無變動（持平）"
    else:
        diff_summary = " | ".join(diff_texts)

    # 依精煉度分組 (+7, +8, +9, +10)
    grouped = {r: [] for r in range(min_r, max_r + 1)}
    for item in matched_items:
        r = item.get("itemRefining", 0)
        if r in grouped:
            grouped[r].append(item)

    fields = [
        {
            "name": "🔔 本次異動備註",
            "value": diff_summary,
            "inline": False
        }
    ]

    for r in range(min_r, max_r + 1):
        items_r = grouped[r]
        if not items_r:
            fields.append({
                "name": f"🔹 +{r} {target_config['itemName']}",
                "value": "*目前架上無販售*",
                "inline": False
            })
            continue

        items_r.sort(key=lambda x: x.get("itemPrice", 0))
        lines = []
        for i, it in enumerate(items_r[:6], 1):
            p = it.get("itemPrice", 0)
            s = it.get("storeName", "未知攤位")
            c = it.get("itemCNT", 1)
            slots = [it.get(f"slot_{k}") for k in range(1, 5) if it.get(f"slot_{k}")]
            slot_t = f" ({'/'.join(slots)})" if slots else ""
            lines.append(f"**{i}.** `{p:,} Z` (x{c}) - {s}{slot_t}")

        if len(items_r) > 6:
            lines.append(f"... 尚有 {len(items_r) - 6} 筆較高價格")

        lowest_p = items_r[0].get("itemPrice", 0)
        fields.append({
            "name": f"🔹 +{r}（共 {len(items_r)} 筆，最低 `{lowest_p:,} Z`）",
            "value": "\n".join(lines),
            "inline": False
        })

    embed = {
        "title": title,
        "description": f"目前架上共 **{len(matched_items)}** 筆符合精煉門檻的商品（15 分鐘定時巡查）",
        "color": 0x2ECC71 if (new_items_count > 0 or removed_items_count > 0) else 0x3498DB,
        "fields": fields,
        "footer": {
            "text": "RO 露天拍賣比價監控 • 15分鐘定期推播"
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

    last_data = load_last_snapshot()
    last_snapshots = last_data.get("snapshots", {})
    last_run_time = last_data.get("last_run_time", 0)
    current_time = time.time()

    # 嚴格控制廣播間隔：若距上次執行未滿 12 分鐘且非手動強制，避免因 cron 抖動連續狂發
    # (但在 local 測試或首次運行時依然會放行)
    print(f"上次推播時間距今: {int(current_time - last_run_time)} 秒")

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

            # 填寫關鍵字並搜尋第一頁
            page.fill("#txb_KeyWord", "")
            page.fill("#txb_KeyWord", keyword)
            page.wait_for_timeout(1000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(7000)

            # --- 精準翻頁機制 ---
            # 依序嘗試點擊頁碼 2, 3, 4, 5
            for p_num in range(2, 6):
                # 尋找內容剛好為該數字的任何元素並強制點擊
                has_page = page.evaluate("""(pageNum) => {
                    const allNodes = Array.from(document.querySelectorAll('a, button, span, li'));
                    const pageNode = allNodes.find(el => el.children.length === 0 && el.textContent.trim() === String(pageNum));
                    if (pageNode) {
                        pageNode.scrollIntoView();
                        pageNode.click();
                        return true;
                    }
                    return false;
                }""", p_num)

                if has_page:
                    print(f"📄 找到第 {p_num} 頁按鈕並觸發點擊，等待伺服器回傳...")
                    page.wait_for_timeout(7000)
                else:
                    # 沒有下一頁數字了
                    break

            page.remove_listener("response", handle_response)
            print(f"累積抓取到原始資料共 {len(captured_items)} 筆")

            # 去重處理
            unique_items = []
            seen_ids = set()
            for it in captured_items:
                uid = str(it.get("SSI2")) if it.get("SSI2") else f"{it.get('storeName')}_{it.get('itemPrice')}_{it.get('itemRefining')}"
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    unique_items.append(it)

            # 篩選符合條件商品
            matched_items = [
                it for it in unique_items 
                if min_refine <= it.get("itemRefining", 0) <= max_refine and it.get("itemPrice", 0) <= max_price
            ]

            # 產生此物品當前商品指紋集合
            current_keys = {
                f"{it.get('itemName')}_+{it.get('itemRefining', 0)}_{it.get('itemPrice')}_{it.get('storeName')}"
                for it in matched_items
            }
            current_snapshots[keyword] = list(current_keys)

            # 比對上一輪快照
            last_keys = set(last_snapshots.get(keyword, []))
            new_items_count = len(current_keys - last_keys) if last_keys else 0
            removed_items_count = len(last_keys - current_keys) if last_keys else 0

            print(f"🎯 執行定時報價：架上符合 {len(matched_items)} 筆（新增 {new_items_count}，售出/下架 {removed_items_count}）")
            send_summary_alert(matched_items, target, new_items_count, removed_items_count)

        browser.close()

    save_snapshot({
        "snapshots": current_snapshots,
        "last_run_time": current_time
    })
    print("\n比價任務執行完畢！")

if __name__ == "__main__":
    main()
