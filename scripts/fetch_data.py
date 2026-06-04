#!/usr/bin/env python3
"""
台灣股市月度績效監測 - 使用 FinMind API
Token 需透過 Authorization: Bearer header 傳入
"""
import requests, json, os, time, datetime

API = "https://api.finmindtrade.com/api/v4/data"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
TOKEN = os.environ.get("FINMIND_TOKEN", "")

def get_headers():
    h = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h

def fetch(dataset, start_date, data_id="", retries=3):
    params = {"dataset": dataset, "start_date": start_date}
    if data_id:
        params["data_id"] = data_id
    for i in range(retries):
        try:
            r = requests.get(API, params=params, headers=get_headers(), timeout=60)
            print(f"  [{r.status_code}] {dataset}")
            if r.status_code == 200:
                d = r.json()
                if d.get("status") == 200:
                    records = d.get("data", [])
                    print(f"  ✓ {dataset}: {len(records)} 筆")
                    return records
                else:
                    print(f"  ✗ msg: {d.get('msg')}")
            elif r.status_code == 401:
                print(f"  ✗ Token 無效")
                break
            else:
                print(f"  ✗ body: {r.text[:100]}")
        except Exception as e:
            print(f"  ✗ 第{i+1}次: {e}")
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
    rev_start = (today.replace(day=1) - datetime.timedelta(days=32)).replace(day=1).strftime("%Y-%m-%d")
    fin_start = (today - datetime.timedelta(days=400)).strftime("%Y-%m-%d")

    print("=" * 50)
    print(f"台灣股市資料抓取 {today} (FinMind)")
    print(f"Token 設定: {'是' if TOKEN else '否（無 Token）'}")
    print("=" * 50)

    print("\n【月營收】")
    rev_data = fetch("TaiwanStockMonthRevenue", rev_start)

    print("\n【公司基本資料】")
    info_data = fetch("TaiwanStockInfo", "2020-01-01")

    print("\n【季報損益表】")
    fin_data = fetch("TaiwanStockFinancialStatements", fin_start)

    # 整理基本資料
    info_map = {}
    for r in info_data:
        sid = r.get("stock_id", "")
        if len(sid) == 4:
            t = r.get("type", "")
            info_map[sid] = {
                "name": r.get("stock_name", ""),
                "market": "L" if t in ("twse", "上市") else "O",
                "industry": r.get("industry_category", "")
            }

    # 整理季報
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
        key = None
        if typ in ("毛利率", "GrossMargin"):
            key = "gp"
        elif typ in ("營業利益率", "OperatingIncomeMargin"):
            key = "op"
        elif typ in ("稅後淨利率", "AfterTaxNetProfitMargin", "淨利率"):
            key = "np"
        if key and (fin_map[sid].get(f"{key}_d", "") < date):
            fin_map[sid][key] = round(val, 1)
            fin_map[sid][f"{key}_d"] = date

    # 整理月營收
    rev_by_stock = {}
    for r in rev_data:
        sid = r.get("stock_id", "")
        if len(sid) != 4:
            continue
        rev = pn(r.get("revenue"))
        if not rev or rev <= 0:
            continue
        date = r.get("date", "")
        if sid not in rev_by_stock:
            rev_by_stock[sid] = []
        rev_by_stock[sid].append({"date": date, "rev": rev})

    companies = []
    rev_month = ""

    for sid, records in rev_by_stock.items():
        records.sort(key=lambda x: x["date"], reverse=True)
        latest = records[0]
        rev, date = latest["rev"], latest["date"]
        mom = None
        if len(records) >= 2 and records[1]["rev"] > 0:
            mom = round((rev - records[1]["rev"]) / records[1]["rev"] * 100, 1)
        yoy = None
        latest_dt = datetime.datetime.strptime(date[:10], "%Y-%m-%d")
        for old in records[1:]:
            old_dt = datetime.datetime.strptime(old["date"][:10], "%Y-%m-%d")
            diff = (latest_dt.year - old_dt.year) * 12 + (latest_dt.month - old_dt.month)
            if 11 <= diff <= 13 and old["rev"] > 0:
                yoy = round((rev - old["rev"]) / old["rev"] * 100, 1)
                break
        if not rev_month:
            rev_month = date[:7]
        info = info_map.get(sid, {})
        fin = fin_map.get(sid, {})
        companies.append({
            "c": sid, "n": info.get("name", sid),
            "m": info.get("market", "L"), "g": info.get("industry", ""),
            "r": int(rev), "y": yoy, "mo": mom,
            "gp": fin.get("gp"), "op": fin.get("op"), "np": fin.get("np"),
        })

    companies.sort(key=lambda x: x["c"])
    listed = sum(1 for c in companies if c["m"] == "L")
    otc = sum(1 for c in companies if c["m"] == "O")
    print(f"\n✓ 共整理 {len(companies)} 家（上市 {listed}，上櫃 {otc}）")

    stats = {
        "total": len(companies), "listed": listed, "otc": otc,
        "yoy_pos": sum(1 for c in companies if c["y"] is not None and c["y"] > 0),
        "yoy_neg": sum(1 for c in companies if c["y"] is not None and c["y"] < 0),
        "gross_med": median([c["gp"] for c in companies if c["gp"] is not None]),
        "net_med": median([c["np"] for c in companies if c["np"] is not None]),
        "rev_month": rev_month,
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "companies": companies}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"✓ 已輸出 {out} ({os.path.getsize(out)//1024} KB)")
    print("完成！")

if __name__ == "__main__":
    main()
