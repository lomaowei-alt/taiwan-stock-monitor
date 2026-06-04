#!/usr/bin/env python3
"""
台灣股市月度績效監測
欄位名稱已從 TWSE swagger_decoded.json 100% 確認
"""
import requests, json, os, datetime

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
BASE = "https://openapi.twse.com.tw/v1"
H = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

def fetch(url, label):
    try:
        r = requests.get(url, headers=H, timeout=60)
        print(f"  {label}: HTTP {r.status_code}")
        if r.status_code == 200:
            text = r.text.strip()
            if text.startswith("["):
                data = json.loads(text)
                if data:
                    print(f"  ✓ {len(data)} 筆")
                    return data
            print(f"  ✗ 非JSON: {text[:60]}")
    except Exception as e:
        print(f"  ✗ {e}")
    return []

def fetch_finmind(dataset, start):
    try:
        r = requests.get("https://api.finmindtrade.com/api/v4/data",
            params={"dataset": dataset, "start_date": start},
            headers=H, timeout=60)
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == 200:
                data = d.get("data", [])
                print(f"  ✓ FinMind {dataset}: {len(data)} 筆")
                return data
    except Exception as e:
        print(f"  ✗ FinMind: {e}")
    return []

def pn(v):
    if v is None or str(v).strip() in ("", "N/A", "--", "－", "***"): return None
    try: return float(str(v).replace(",", "").replace("%", ""))
    except: return None

def safe_pct(a, b):
    if a is None or b is None or b == 0: return None
    return round((a - b) / abs(b) * 100, 1)

def median(vals):
    if not vals: return None
    s = sorted(vals); m = len(s) // 2
    return round(s[m] if len(s) % 2 else (s[m-1] + s[m]) / 2, 1)

def calc_margin(numerator_key, rev_key, row):
    """Calculate margin ratio from two amount fields"""
    num = pn(row.get(numerator_key))
    rev = pn(row.get(rev_key))
    if num is None or rev is None or rev == 0: return None
    return round(num / rev * 100, 1)

def main():
    today = datetime.date.today()
    print("=" * 55)
    print(f"台灣股市資料抓取 {today}")
    print("=" * 55)

    # ── 1. 上市月營收 (t187ap05_L) ─────────────────────────
    # 確認欄位: 公司代號, 公司名稱, 產業別,
    #           營業收入-當月營收, 營業收入-上月營收, 營業收入-去年當月營收,
    #           營業收入-上月比較增減(%), 營業收入-去年同月增減(%)
    print("\n【上市月營收 t187ap05_L】")
    twse_rev = fetch(f"{BASE}/opendata/t187ap05_L", "月營收")

    # ── 2. 上市公司基本資料 (t187ap03_L) ──────────────────
    # 確認欄位: 公司代號, 公司名稱, 產業別
    print("\n【上市公司基本資料 t187ap03_L】")
    twse_info = fetch(f"{BASE}/opendata/t187ap03_L", "基本資料")

    # ── 3. 上市損益表（各業別）─────────────────────────────
    # 確認欄位: 公司代號, 公司名稱, 營業收入, 營業毛利（毛損）淨額,
    #           營業利益（損失）, 本期淨利（淨損）
    print("\n【損益表】")
    inc_ci   = fetch(f"{BASE}/opendata/t187ap06_L_ci",   "一般業")
    inc_basi = fetch(f"{BASE}/opendata/t187ap06_L_basi", "金融業")
    inc_fh   = fetch(f"{BASE}/opendata/t187ap06_L_fh",   "金控業")
    inc_ins  = fetch(f"{BASE}/opendata/t187ap06_L_ins",  "保險業")
    inc_bd   = fetch(f"{BASE}/opendata/t187ap06_L_bd",   "券商業")
    inc_mim  = fetch(f"{BASE}/opendata/t187ap06_L_mim",  "異業")
    all_income = inc_ci + inc_basi + inc_fh + inc_ins + inc_bd + inc_mim

    # ── 4. 上櫃月營收 ──────────────────────────────────────
    print("\n【上櫃月營收 TPEx】")
    tpex_rev = fetch("https://www.tpex.org.tw/openapi/v1/mopsfin_t53", "上櫃月營收")

    # ── 5. FinMind 補充資料 ────────────────────────────────
    print("\n【FinMind 基本資料】")
    fm_info = fetch_finmind("TaiwanStockInfo", "2020-01-01")

    # ── 建立 lookup maps ──────────────────────────────────
    ind_map, mkt_map = {}, {}

    # FinMind 基本資料（補底）
    for r in fm_info:
        sid = r.get("stock_id", "")
        if len(sid) == 4:
            ind_map[sid] = r.get("industry_category", "")
            mkt_map[sid] = "L" if r.get("type","") in ("twse","上市") else "O"

    # TWSE 官方基本資料（覆蓋）
    for r in twse_info:
        code = str(r.get("公司代號","")).strip()
        if len(code) == 4:
            ind_map[code] = str(r.get("產業別","")).strip()
            mkt_map[code] = "L"

    # 損益表 → 毛利率、營業利益率、淨利率
    fin_map = {}
    for r in all_income:
        code = str(r.get("公司代號","")).strip()
        if not code: continue
        rev = pn(r.get("營業收入"))
        if not rev or rev == 0: continue
        gross = calc_margin("營業毛利（毛損）淨額", "營業收入", r)
        op    = calc_margin("營業利益（損失）",       "營業收入", r)
        net   = calc_margin("本期淨利（淨損）",       "營業收入", r)
        if any(x is not None for x in [gross, op, net]):
            fin_map[code] = {"gp": gross, "op": op, "np": net}

    # ── 整理上市月營收 ─────────────────────────────────────
    companies = []
    rev_month = ""

    for r in twse_rev:
        code = str(r.get("公司代號","")).strip()
        if not code or len(code) != 4: continue
        rev = pn(r.get("營業收入-當月營收"))
        if not rev or rev <= 0: continue
        name = str(r.get("公司名稱","")).strip()
        # 確認欄位名: 營業收入-去年同月增減(%) / 營業收入-上月比較增減(%)
        yoy = pn(r.get("營業收入-去年同月增減(%)"))
        mom = pn(r.get("營業收入-上月比較增減(%)"))
        if yoy is None:
            yoy = safe_pct(rev, pn(r.get("營業收入-去年當月營收")))
        if r.get("出表日期") and not rev_month:
            rev_month = str(r["出表日期"])
        # 產業：優先 t187ap05_L 自帶的產業別
        ind = str(r.get("產業別","")).strip() or ind_map.get(code,"")
        fin = fin_map.get(code, {})
        companies.append({
            "c": code, "n": name,
            "m": mkt_map.get(code, "L"),
            "g": ind,
            "r": int(rev),
            "y": round(yoy, 1) if yoy is not None else None,
            "mo": round(mom, 1) if mom is not None else None,
            "gp": fin.get("gp"), "op": fin.get("op"), "np": fin.get("np"),
        })

    print(f"\n  上市整理: {len(companies)} 家")

    # ── 整理上櫃月營收 ─────────────────────────────────────
    for r in tpex_rev:
        code = str(r.get("SecuritiesCompanyCode") or r.get("公司代號") or "").strip()
        if not code or len(code) != 4: continue
        rev = pn(r.get("MonthlyRevenue") or r.get("當月營收"))
        if not rev or rev <= 0: continue
        name = str(r.get("CompanyName") or r.get("公司名稱") or "").strip()
        yoy_raw = r.get("YoYGrowthRate") or r.get("MonthlyRevenueGrowthRate")
        mom_raw = r.get("MoMGrowthRate")
        yoy = pn(yoy_raw) if yoy_raw not in (None,"","N/A") else \
              safe_pct(rev, pn(r.get("RevenueLYSameMonth") or r.get("去年同月營收")))
        mom = pn(mom_raw) if mom_raw not in (None,"","N/A") else None
        fin = fin_map.get(code, {})
        companies.append({
            "c": code, "n": name, "m": "O",
            "g": ind_map.get(code, ""),
            "r": int(rev),
            "y": round(yoy, 1) if yoy is not None else None,
            "mo": round(mom, 1) if mom is not None else None,
            "gp": fin.get("gp"), "op": fin.get("op"), "np": fin.get("np"),
        })

    companies.sort(key=lambda x: x["c"])
    listed = sum(1 for c in companies if c["m"] == "L")
    otc    = sum(1 for c in companies if c["m"] == "O")
    with_fin = sum(1 for c in companies if c["gp"] is not None)
    print(f"✓ 共 {len(companies)} 家（上市 {listed}，上櫃 {otc}，含季報 {with_fin} 家）")

    stats = {
        "total": len(companies), "listed": listed, "otc": otc,
        "yoy_pos": sum(1 for c in companies if c["y"] is not None and c["y"] > 0),
        "yoy_neg": sum(1 for c in companies if c["y"] is not None and c["y"] < 0),
        "gross_med": median([c["gp"] for c in companies if c["gp"] is not None]),
        "net_med":   median([c["np"] for c in companies if c["np"] is not None]),
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
