#!/usr/bin/env python3
"""
台灣股市月度績效監測 - 資料抓取腳本
TWSE/TPEx API 會擋非台灣 IP，改用 allorigins proxy 繞過
"""

import requests, json, time, os
from datetime import datetime, timezone

TWSE = "https://openapi.twse.com.tw/v1"
TPEX = "https://www.tpex.org.tw/openapi/v1"

# 多個 proxy 輪流嘗試，確保成功
PROXIES = [
    lambda u: f"https://api.allorigins.win/raw?url={requests.utils.quote(u)}",
    lambda u: f"https://corsproxy.io/?url={requests.utils.quote(u)}",
    lambda u: u,  # 直連最後嘗試
]

HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")


def fetch(url, label):
    for i, make_url in enumerate(PROXIES):
        proxy_url = make_url(url)
        try:
            r = requests.get(proxy_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                print(f"  ✓ {label}: {len(data)} 筆 (proxy #{i+1})")
                return data
        except Exception as e:
            print(f"  ✗ {label} proxy #{i+1} 失敗: {e}")
            time.sleep(2)
    print(f"  ✗ {label}: 所有 proxy 失敗，回傳空陣列")
    return []


def pn(v):
    if v is None or str(v).strip() in ("", "N/A", "--", "－"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except:
        return None


def calc_pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return round((a - b) / abs(b) * 100, 1)


def extract_ratios(row):
    gross = op = net = None
    for k, v in row.items():
        kk = k.replace(" ", "")
        n = pn(v)
        if n is None:
            continue
        if "毛利率" in kk and gross is None:
            gross = round(n, 1)
        if ("營業利益率" in kk or "營業利潤率" in kk) and op is None:
            op = round(n, 1)
        if ("淨利率" in kk or "稅後純益率" in kk) and net is None:
            net = round(n, 1)
    return gross, op, net


def median(vals):
    if not vals:
        return None
    s = sorted(vals)
    m = len(s) // 2
    return round(s[m] if len(s) % 2 else (s[m-1] + s[m]) / 2, 1)


def main():
    print("=" * 50)
    print(f"台灣股市資料抓取 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    print("\n【上市公司】")
    twse_rev    = fetch(f"{TWSE}/opendata/t187ap03_L",   "月營收")
    twse_info   = fetch(f"{TWSE}/opendata/t187ap03_2",    "基本資料")
    twse_income = fetch(f"{TWSE}/opendata/t187ap06_X_ci", "季報損益表")

    print("\n【上櫃公司】")
    tpex_rev    = fetch(f"{TPEX}/mopsfin_t53",                            "月營收")
    tpex_info   = fetch(f"{TPEX}/tpex_mainboard_companies_information",    "基本資料")
    tpex_income = fetch(f"{TPEX}/tpex_mainboard_income_statement",         "季報損益表")

    # Build maps
    twse_ind = {(r.get("公司代號") or r.get("股票代號") or "").strip(): (r.get("產業類別") or "").strip() for r in twse_info}
    tpex_ind = {(r.get("SecuritiesCompanyCode") or r.get("公司代號") or "").strip(): (r.get("IndustryCode") or r.get("IndustryName") or r.get("產業別") or "").strip() for r in tpex_info}
    twse_fin = {}
    for r in twse_income:
        code = (r.get("公司代號") or "").strip()
        if code:
            twse_fin[code] = extract_ratios(r)
    tpex_fin = {}
    for r in tpex_income:
        code = (r.get("SecuritiesCompanyCode") or r.get("公司代號") or "").strip()
        if code:
            tpex_fin[code] = extract_ratios(r)

    companies = []
    rev_month = ""

    for r in twse_rev:
        code = (r.get("公司代號") or "").strip()
        if not code or len(code) != 4:
            continue
        rev = pn(r.get("當月營收") or r.get("revenue"))
        if not rev or rev <= 0:
            continue
        name = (r.get("公司名稱") or "").strip()
        yoy_raw = r.get("當月營收年增率")
        mom_raw = r.get("當月營收月增率")
        yoy = float(yoy_raw) if yoy_raw not in (None, "", "N/A") else calc_pct(rev, pn(r.get("去年同月營收")))
        mom = float(mom_raw) if mom_raw not in (None, "", "N/A") else calc_pct(rev, pn(r.get("上月營收")))
        if r.get("出表日期") and not rev_month:
            rev_month = r["出表日期"]
        g, o, n = twse_fin.get(code, (None, None, None))
        companies.append({"c": code, "n": name, "m": "L", "g": twse_ind.get(code, ""),
                          "r": int(rev), "y": round(yoy, 1) if yoy is not None else None,
                          "mo": round(mom, 1) if mom is not None else None,
                          "gp": g, "op": o, "np": n})

    for r in tpex_rev:
        code = (r.get("SecuritiesCompanyCode") or r.get("公司代號") or "").strip()
        if not code or len(code) != 4:
            continue
        rev = pn(r.get("MonthlyRevenue") or r.get("當月營收"))
        if not rev or rev <= 0:
            continue
        name = (r.get("CompanyName") or r.get("公司名稱") or "").strip()
        yoy_raw = r.get("YoYGrowthRate") or r.get("MonthlyRevenueGrowthRate")
        mom_raw = r.get("MoMGrowthRate")
        yoy = float(yoy_raw) if yoy_raw not in (None, "", "N/A") else calc_pct(rev, pn(r.get("RevenueLYSameMonth") or r.get("去年同月營收")))
        mom = float(mom_raw) if mom_raw not in (None, "", "N/A") else calc_pct(rev, pn(r.get("RevenuePrevMonth") or r.get("上月營收")))
        g, o, n = tpex_fin.get(code, (None, None, None))
        companies.append({"c": code, "n": name, "m": "O", "g": tpex_ind.get(code, ""),
                          "r": int(rev), "y": round(yoy, 1) if yoy is not None else None,
                          "mo": round(mom, 1) if mom is not None else None,
                          "gp": g, "op": o, "np": n})

    print(f"\n✓ 共整理 {len(companies)} 家公司")

    listed_ct = sum(1 for c in companies if c["m"] == "L")
    otc_ct    = sum(1 for c in companies if c["m"] == "O")
    stats = {
        "total": len(companies), "listed": listed_ct, "otc": otc_ct,
        "yoy_pos": sum(1 for c in companies if c["y"] is not None and c["y"] > 0),
        "yoy_neg": sum(1 for c in companies if c["y"] is not None and c["y"] < 0),
        "gross_med": median([c["gp"] for c in companies if c["gp"] is not None]),
        "net_med":   median([c["np"] for c in companies if c["np"]  is not None]),
        "rev_month": rev_month,
        "updated":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "companies": companies}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"✓ 已輸出 docs/data.json ({os.path.getsize(out)//1024} KB)")
    print("完成！")


if __name__ == "__main__":
    main()
