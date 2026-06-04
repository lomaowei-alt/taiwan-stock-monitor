#!/usr/bin/env python3
"""
台灣股市月度績效監測 - 使用 FinMind 開源資料平台
FinMind: https://finmindtrade.com - 不封鎖海外 IP，GitHub Actions 可正常存取
免費帳號每天 600 次請求，足夠每日更新使用
"""
import requests, json, os, time, datetime

API = "https://api.finmindtrade.com/api/v4/data"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
TOKEN = os.environ.get("FINMIND_TOKEN", "")  # 空白也可用，但有限制

HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}

def fetch_finmind(dataset, start_date, data_id="", retries=3):
    params = {"dataset": dataset, "start_date": start_date, "token": TOKEN}
    if data_id:
        params["data_id"] = data_id
    for i in range(retries):
        try:
            r = requests.get(API, params=params, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                d = r.json()
                if d.get("status") == 200:
                    records = d.get("data", [])
                    print(f"  ✓ {dataset}: {len(records)} 筆")
                    return records
                else:
                    print(f"  ✗ {dataset}: {d.get('msg','unknown error')}")
            else:
                print(f"  ✗ {dataset}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  ✗ {dataset} 第{i+1}次: {e}")
        if i < retries - 1:
            time.sleep(5)
    return []

def pn(v):
    if v is None or str(v).strip() in ("", "N/A", "--"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except:
        return None

def median(vals):
    if not vals:
        return None
    s = sorted(vals)
    m = len(s) // 2
    return round(s[m] if len(s) % 2 else (s[m-1] + s[m]) / 2, 1)

def main():
    today = datetime.date.today()
    # 月營收：抓最近 2 個月確保有資料（每月 10 號前公告）
    rev_start = (today.replace(day=1) - datetime.timedelta(days=32)).replace(day=1).strftime("%Y-%m-%d")
    # 季報：抓最近一年
    fin_start = (today - datetime.timedelta(days=400)).strftime("%Y-%m-%d")

    print("=" * 50)
    print(f"台灣股市資料抓取 {today.strftime('%Y-%m-%d')} (FinMind)")
    print("=" * 50)

    print("\n【月營收】")
    rev_data = fetch_finmind("TaiwanStockMonthRevenue", rev_start)

    print("\n【公司基本資料】")
    info_data = fetch_finmind("TaiwanStockInfo", "2020-01-01")

    print("\n【季報損益表】")
    fin_data = fetch_finmind("TaiwanStockFinancialStatements", fin_start)

    # ── 整理公司基本資料 ──────────────────────────────────
    # TaiwanStockInfo 欄位: stock_id, stock_name, type, industry_category, market
    info_map = {}
    for r in info_data:
        sid = r.get("stock_id", "")
        if len(sid) == 4:
            info_map[sid] = {
                "name": r.get("stock_name", ""),
                "market": "L" if r.get("type", "") in ("twse", "上市") or r.get("market", "") == "上市" else "O",
                "industry": r.get("industry_category", "")
            }

    # ── 整理季報：取最新一季的毛利率、營業利益率、淨利率 ──
    # TaiwanStockFinancialStatements 欄位: stock_id, date, type, value
    fin_map = {}
    for r in fin_data:
        sid = r.get("stock_id", "")
        typ = r.get("type", "")
        val = pn(r.get("value"))
        date = r.get("date", "")
        if not sid or val is None:
            continue
        if sid not in fin_map:
            fin_map[sid] = {}
        # 取最新日期的數值
        key = None
        if typ in ("毛利率", "GrossMargin"):
            key = "gp"
        elif typ in ("營業利益率", "OperatingIncomeMargin"):
            key = "op"
        elif typ in ("稅後淨利率", "AfterTaxNetProfitMargin", "淨利率"):
            key = "np"
        if key:
            existing = fin_map[sid].get(key)
            if existing is None or date > fin_map[sid].get(f"{key}_date", ""):
                fin_map[sid][key] = round(val, 1)
                fin_map[sid][f"{key}_date"] = date

    # ── 整理月營收：取最新月份，計算 YoY / MoM ────────────
    # TaiwanStockMonthRevenue 欄位: stock_id, date, country, revenue, revenue_month, revenue_year
    rev_by_stock = {}
    for r in rev_data:
        sid = r.get("stock_id", "")
        if len(sid) != 4:
            continue
        date = r.get("date", "")
        rev = pn(r.get("revenue"))
        if not rev or rev <= 0:
            continue
        if sid not in rev_by_stock:
            rev_by_stock[sid] = []
        rev_by_stock[sid].append({"date": date, "rev": rev})

    companies = []
    rev_month = ""

    for sid, records in rev_by_stock.items():
        records.sort(key=lambda x: x["date"], reverse=True)
        if not records:
            continue
        latest = records[0]
        rev = latest["rev"]
        date = latest["date"]

        # MoM: 上個月
        mom = None
        if len(records) >= 2:
            prev_rev = records[1]["rev"]
            if prev_rev > 0:
                mom = round((rev - prev_rev) / prev_rev * 100, 1)

        # YoY: 去年同月（找日期差 11~13 個月的資料）
        yoy = None
        latest_dt = datetime.datetime.strptime(date[:10], "%Y-%m-%d")
        for old in records[1:]:
            old_dt = datetime.datetime.strptime(old["date"][:10], "%Y-%m-%d")
            months_diff = (latest_dt.year - old_dt.year) * 12 + (latest_dt.month - old_dt.month)
            if 11 <= months_diff <= 13:
                if old["rev"] > 0:
                    yoy = round((rev - old["rev"]) / old["rev"] * 100, 1)
                break

        if not rev_month and date:
            rev_month = date[:7]

        info = info_map.get(sid, {})
        fin = fin_map.get(sid, {})
        companies.append({
            "c": sid,
            "n": info.get("name", sid),
            "m": info.get("market", "L"),
            "g": info.get("industry", ""),
            "r": int(rev),
            "y": yoy,
            "mo": mom,
            "gp": fin.get("gp"),
            "op": fin.get("op"),
            "np": fin.get("np"),
        })

    # 按代號排序
    companies.sort(key=lambda x: x["c"])
    listed_ct = sum(1 for c in companies if c["m"] == "L")
    otc_ct    = sum(1 for c in companies if c["m"] == "O")

    print(f"\n✓ 共整理 {len(companies)} 家公司（上市 {listed_ct}，上櫃 {otc_ct}）")

    stats = {
        "total": len(companies), "listed": listed_ct, "otc": otc_ct,
        "yoy_pos": sum(1 for c in companies if c["y"] is not None and c["y"] > 0),
        "yoy_neg": sum(1 for c in companies if c["y"] is not None and c["y"] < 0),
        "gross_med": median([c["gp"] for c in companies if c["gp"] is not None]),
        "net_med":   median([c["np"] for c in companies if c["np"] is not None]),
        "rev_month": rev_month,
        "updated":   datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "companies": companies}, f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"✓ 已輸出 docs/data.json ({os.path.getsize(out)//1024} KB)")
    print("完成！")

if __name__ == "__main__":
    main()
