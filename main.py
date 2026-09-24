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

def truncate_text(text, max_len=5):
    """通用字串截斷函數"""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) > max_len:
        return f"{text[:max_len]}.."
    return text

def send_login_alert():
    if not WEBHOOK_URL:
        return
    embed = {
        "title": "⚠️ RO 拍賣監控：登入憑證失效！",
        "description": "系統抓取不到拍賣數據，請前往網頁重新登入一次以延長 Session。",
        "color": 0xE74C3C,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)

def send_summary_alert(matched_items, target_config, new_items_count, removed_items_count):
    if not WEBHOOK_URL:
        return

    item_name = target_config["itemName"]
    is_card = item_name.endswith("卡片")
    min_r = target_config.get("minRefine", 0)
    max_r = target_config.get("maxRefine", 10)

    # 判斷是否為「多精煉跨度裝備」（例如 +7~+10）
    is_multi_refine = (not is_card) and (max_r > min_r) and (max_r > 0)

    # 異動備註
    diff_texts = []
    if new_items_count > 0:
        diff_texts.append(f"🟢 **新增上架**: {new_items_count} 筆")
    if removed_items_count > 0:
        diff_texts.append(f"🔴 **已售出/下架**: {removed_items_count} 筆")
    if new_items_count == 0 and removed_items_count == 0:
        diff_summary = "⚪ **架上狀況**: 價格與數量無變動（持平）"
    else:
        diff_summary = " | ".join(diff_texts)

    fields = [
        {
            "name": "🔔 本次異動備註",
            "value": diff_summary,
            "inline": False
        }
    ]

    DIVIDER_LINE = "──────────────────"

    if is_card:
        # 1. 卡片類：無精煉，顯示最多 10 筆
        title = f"🃏 【卡片行情】{item_name}"
        if matched_items:
            matched_items.sort(key=lambda x: x.get("itemPrice", 0))
            lowest_item = matched_items[0]
            highest_item = matched_items[-1]

            lines = []
            for i, it in enumerate(matched_items[:10], 1):
                p = it.get("itemPrice", 0)
                s = truncate_text(it.get("storeName", "未知攤位"), 5)
                c = it.get("itemCNT", 1)
                lines.append(f"**{i}.** `{p:,} Z` (x{c}) ｜ *{s}*")

            if len(matched_items) > 10:
                lines.append(f"... 尚有 {len(matched_items) - 10} 筆較高價格未顯示")

            fields.append({"name": "📉 架上最低價", "value": f"**{lowest_item.get('itemPrice', 0):,} Z**", "inline": True})
            fields.append({"name": "📈 架上最高價", "value": f"**{highest_item.get('itemPrice', 0):,} Z**", "inline": True})
            fields.append({"name": "📋 架上販售列表（由低至高）", "value": "\n".join(lines), "inline": False})
        else:
            fields.append({"name": "🏪 架上狀況", "value": "*目前架上無任何販售*", "inline": False})

    elif not is_multi_refine:
        # 2. 單一裝備 / 飾品（如 +0 翡翠耳環）：單一分類，顯示最多 10 筆
        refine_tag = f"+{min_r} " if min_r > 0 else ""
        title = f"🛡️ 【裝備行情】{refine_tag}{item_name}"
        if matched_items:
            matched_items.sort(key=lambda x: x.get("itemPrice", 0))
            lowest_item = matched_items[0]
            highest_item = matched_items[-1]

            lines = []
            for i, it in enumerate(matched_items[:10], 1):
                p = it.get("itemPrice", 0)
                r = it.get("itemRefining", 0)
                s = truncate_text(it.get("storeName", "未知攤位"), 5)
                c = it.get("itemCNT", 1)

                slots = [it.get(f"slot_{k}") for k in range(1, 5) if it.get(f"slot_{k}")]
                slot_t = f" ({truncate_text('/'.join(slots), 8)})" if slots else ""

                r_str = f"`+{r}` " if r > 0 else ""
                lines.append(f"**{i}.** {r_str}`{p:,} Z` (x{c}) ｜ *{s}*{slot_t}")

            if len(matched_items) > 10:
                lines.append(f"... 尚有 {len(matched_items) - 10} 筆較高價格未顯示")

            fields.append({"name": "📉 架上最低價", "value": f"**{lowest_item.get('itemPrice', 0):,} Z**", "inline": True})
            fields.append({"name": "📈 架上最高價", "value": f"**{highest_item.get('itemPrice', 0):,} Z**", "inline": True})
            fields.append({"name": "📋 架上販售列表（由低至高）", "value": "\n".join(lines), "inline": False})
        else:
            fields.append({"name": "🏪 架上狀況", "value": "*目前架上無任何販售*", "inline": False})

    else:
        # 3. 多精煉跨度裝備（如 +7~+10 神槍手紅色典藏板）：每個精煉等級獨立顯示各自的最低與最高價
        title = f"🛡️ 【裝備行情】+{min_r}~+{max_r} {item_name}"

        grouped = {}
        for item in matched_items:
            r = item.get("itemRefining", 0)
            if r not in grouped:
                grouped[r] = []
            grouped[r].append(item)

        display_refines = sorted(list(set(range(min_r, max_r + 1)).union(grouped.keys())))
        display_refines = [r for r in display_refines if min_r <= r <= max_r]

        if not display_refines:
            display_refines = [min_r]

        total_groups = len(display_refines)

        for idx, r in enumerate(display_refines):
            is_last_group = (idx == total_groups - 1)
            items_r = grouped.get(r, [])

            if not items_r:
                content = "*目前架上無販售*"
                if not is_last_group:
                    content += f"\n{DIVIDER_LINE}"
                fields.append({
                    "name": f"🔹 +{r} {item_name}",
                    "value": content,
                    "inline": False
                })
                continue

            items_r.sort(key=lambda x: x.get("itemPrice", 0))
            lowest_p = items_r[0].get("itemPrice", 0)
            highest_p = items_r[-1].get("itemPrice", 0)

            lines = []
            # 在清單上方直接顯示該精煉分組的獨立最低價與最高價
            lines.append(f"📉 最低: `{lowest_p:,} Z` ｜ 📈 最高: `{highest_p:,} Z`")

            for i, it in enumerate(items_r[:5], 1):
                p = it.get("itemPrice", 0)
                s = truncate_text(it.get("storeName", "未知攤位"), 5)
                c = it.get("itemCNT", 1)

                slots = [it.get(f"slot_{k}") for k in range(1, 5) if it.get(f"slot_{k}")]
                slot_t = f" ({truncate_text('/'.join(slots), 8)})" if slots else ""

                lines.append(f"**{i}.** `+{r}` `{p:,} Z` (x{c}) ｜ *{s}*{slot_t}")

            if len(items_r) > 5:
                lines.append(f"... 尚有 {len(items_r) - 5} 筆較高價格")

            if not is_last_group:
                lines.append(DIVIDER_LINE)

            fields.append({
                "name": f"🔹 +{r}（共 {len(items_r)} 筆）",
                "value": "\n".join(lines),
                "inline": False
            })

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

    requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)

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
    for p_num in range(2, 6):
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
            page.wait_for_timeout(6000)
        else:
            break

    page.remove_listener("response", handle_response)
    return captured_items

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

        print("開啟露天拍賣平台...")
        page.goto("https://event.gnjoy.com.tw/RoZ/RoZ_ShopSearch", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(8000)

        for target in active_targets:
            item_name = target["itemName"]
            is_card = item_name.endswith("卡片")

            if is_card:
                query_text = f'"{item_name}"'
            else:
                query_text = item_name

            max_price = target.get("maxPrice", 999999999)
            min_refine = target.get("minRefine", 0)
            max_refine = target.get("maxRefine", 10 if not is_card else 0)

            print(f"\n🔍 正在查詢：{item_name} (送出字串: {query_text})")

            captured_items = search_item_with_pages(page, query_text)

            # 去重處理
            unique_items = []
            seen_ids = set()
            for it in captured_items:
                uid = str(it.get("SSI2")) if it.get("SSI2") else f"{it.get('storeName')}_{it.get('itemPrice')}_{it.get('itemRefining')}"
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    unique_items.append(it)

            # 篩選匹配商品
            matched_items = []
            for it in unique_items:
                r = it.get("itemRefining", 0)
                p = it.get("itemPrice", 0)
                if is_card:
                    if it.get("itemName") == item_name and p <= max_price:
                        matched_items.append(it)
                else:
                    if min_refine <= r <= max_refine and p <= max_price:
                        matched_items.append(it)

            current_keys = {
                f"{it.get('itemName')}_+{it.get('itemRefining', 0)}_{it.get('itemPrice')}_{it.get('storeName')}"
                for it in matched_items
            }
            current_snapshots[item_name] = list(current_keys)

            last_keys = set(last_snapshots.get(item_name, []))
            new_items_count = len(current_keys - last_keys) if last_keys else 0
            removed_items_count = len(last_keys - current_keys) if last_keys else 0

            print(f"🎯 執行定時報價：架上符合 {len(matched_items)} 筆（新增 {new_items_count}，售出/下架 {removed_items_count}）")
            send_summary_alert(matched_items, target, new_items_count, removed_items_count)

        browser.close()

    if current_snapshots:
        save_snapshot({
            "snapshots": current_snapshots,
            "last_run_time": current_time
        })
    print("\n比價任務執行完畢！")

if __name__ == "__main__":
    main()
