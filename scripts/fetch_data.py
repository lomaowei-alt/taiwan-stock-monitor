#!/usr/bin/env python3
"""台灣股市月度績效監測"""
import requests, json, os, datetime

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
H = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

def fetch_json(url, label):
    try:
        r = requests.get(url, headers=H, timeout=60)
        print(f"  {label}: HTTP {r.status_code}")
        if r.status_code == 200:
            text = r.text.strip()
            if text.startswith("["):
                data = json.loads(text)
                print(f"  ✓ {label}: {len(data)} 筆, 欄位: {list(data[0].keys()) if data else '[]'}")
                return data
            else:
                print(f"  ✗ 非 JSON: {text[:80]}")
    except Exception as e:
        print(f"  ✗ {e}")
    return []

def fetch_finmind(dataset, start_date):
    try:
        r = requests.get("https://api.finmindtrade.com/api/v4/data",
            params={"dataset": dataset, "start_date": start_date},
            headers=H, timeout=60)
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == 200:
                data = d.get("data", [])
                print(f"  ✓ FinMind {dataset}: {len(data)} 筆")
                return data
            print(f"  ✗ {d.get('msg')}")
    except Exception as e:
        print(f"  ✗ FinMind: {e}")
    return []

def pn(v):
    if v is None or str(v).strip() in ("", "N/A", "--", "－", "***"): return None
    try: return float(str(v).replace(",", "").replace("%", ""))
    except: return None

def pct(a, b):
    if a is None or b is None or b == 0: return None
    return round((a - b) / abs(b) * 100, 1)

def median(vals):
    if not vals: return None
    s = sorted(vals); m = len(s) // 2
    return round(s[m] if len(s) % 2 else (s[m-1] + s[m]) / 2, 1)

def main():
    today = datetime.date.today()
    print("=" * 50)
    print(f"台灣股市資料抓取 {today}")
    print("=" * 50)

    print("\n【上市月營收 - t187ap04_L】")
    # 正確的月營收 endpoint 是 t187ap04_L，不是 t187ap03_L
    twse_rev = fetch_json("https://openapi.twse.com.tw/v1/opendata/t187ap04_L", "上市月營收")

    print("\n【公司基本資料 - FinMind】")
    fm_info = fetch_finmind("TaiwanStockInfo", "2020-01-01")

    print("\n【上櫃月營收 - TPEx】")
    tpex_rev = fetch_json("https://www.tpex.org.tw/openapi/v1/mopsfin_t53", "上櫃月營收")

    # 建立基本資料對照
    ind_map, mkt_map = {}, {}
    for r in fm_info:
        sid = r.get("stock_id", "")
        if len(sid) == 4:
            ind_map[sid] = r.get("industry_category", "")
            mkt_map[sid] = "L" if r.get("type","") in ("twse","上市") else "O"

    companies = []
    rev_month = ""

    # 整理上市月營收
    # t187ap04_L 欄位: 出表日期, 公司代號, 公司名稱, 當月營收, 當月累計營收,
    #                  去年當月營收, 去年累計營收, 前期比較增減(%), 去年同期比較增減(%)
    for r in twse_rev:
        code = str(r.get("公司代號", "")).strip()
        if not code or len(code) != 4: continue
        rev = pn(r.get("當月營收"))
        if not rev or rev <= 0: continue
        name = str(r.get("公司名稱", "")).strip()
        yoy = pn(r.get("去年同期比較增減(%)"))
        mom = pn(r.get("前期比較增減(%)"))
        if yoy is None:
            yoy = pct(rev, pn(r.get("去年當月營收")))
        if r.get("出表日期") and not rev_month:
            rev_month = str(r["出表日期"])
        companies.append({
            "c": code, "n": name,
            "m": mkt_map.get(code, "L"),
            "g": ind_map.get(code, ""),
            "r": int(rev),
            "y": round(yoy, 1) if yoy is not None else None,
            "mo": round(mom, 1) if mom is not None else None,
            "gp": None, "op": None, "np": None
        })

    print(f"  上市整理完成: {len(companies)} 家")

    # 整理上櫃月營收
    for r in tpex_rev:
        code = str(r.get("SecuritiesCompanyCode") or r.get("公司代號") or "").strip()
        if not code or len(code) != 4: continue
        rev = pn(r.get("MonthlyRevenue") or r.get("當月營收"))
        if not rev or rev <= 0: continue
        name = str(r.get("CompanyName") or r.get("公司名稱") or "").strip()
        yoy_raw = r.get("YoYGrowthRate") or r.get("MonthlyRevenueGrowthRate")
        mom_raw = r.get("MoMGrowthRate")
        yoy = pn(yoy_raw) if yoy_raw not in (None,"","N/A") else pct(rev, pn(r.get("RevenueLYSameMonth") or r.get("去年同月營收")))
        mom = pn(mom_raw) if mom_raw not in (None,"","N/A") else None
        companies.append({
            "c": code, "n": name, "m": "O",
            "g": ind_map.get(code, ""),
            "r": int(rev),
            "y": round(yoy, 1) if yoy is not None else None,
            "mo": round(mom, 1) if mom is not None else None,
            "gp": None, "op": None, "np": None
        })

    companies.sort(key=lambda x: x["c"])
    listed = sum(1 for c in companies if c["m"] == "L")
    otc    = sum(1 for c in companies if c["m"] == "O")
    print(f"\n✓ 共 {len(companies)} 家（上市 {listed}，上櫃 {otc}）")

    stats = {
        "total": len(companies), "listed": listed, "otc": otc,
        "yoy_pos": sum(1 for c in companies if c["y"] is not None and c["y"] > 0),
        "yoy_neg": sum(1 for c in companies if c["y"] is not None and c["y"] < 0),
        "gross_med": None, "net_med": None,
        "rev_month": rev_month,
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "companies": companies}, f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"✓ 輸出 data.json ({os.path.getsize(out) // 1024} KB)")
    print("完成！")

if __name__ == "__main__":
    main()
