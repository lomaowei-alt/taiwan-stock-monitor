#!/usr/bin/env python3
"""
台灣股市月度績效監測 - 四層篩選版本 v2
修正：T86 欄位名稱動態解析 + Layer1 初始月份處理
"""
import requests, json, os, datetime, time

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
BASE = "https://openapi.twse.com.tw/v1"
H = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

def fetch(url, label, delay=0.3):
    try:
        time.sleep(delay)
        r = requests.get(url, headers=H, timeout=60)
        print(f"  {label}: HTTP {r.status_code}")
        if r.status_code == 200:
            text = r.text.strip()
            if text.startswith("["):
                data = json.loads(text)
                if data:
                    print(f"  ✓ {len(data)} 筆")
                    return data
            elif text.startswith("{"):
                d = json.loads(text)
                if d.get("stat") == "OK":
                    rows = d.get("data", [])
                    fields = d.get("fields", [])
                    print(f"  ✓ {len(rows)} 筆 | fields: {fields[:5]}")
                    return {"data": rows, "fields": fields}
            print(f"  ✗ 非JSON或空: {text[:80]}")
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
        print(f"  ✗ FinMind {dataset}: {e}")
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

def calc_margin(num_key, rev_key, row):
    num = pn(row.get(num_key))
    rev = pn(row.get(rev_key))
    if num is None or rev is None or rev == 0: return None
    return round(num / rev * 100, 1)

def parse_t86_row(row, fields):
    """動態解析 T86 欄位，適應不同欄位名稱版本"""
    if isinstance(row, list) and fields:
        d = dict(zip(fields, row))
    elif isinstance(row, dict):
        d = row
    else:
        return None, None, None

    code = str(d.get("證券代號","")).strip()
    if not code:
        return None, None, None

    # 動態找外資淨買賣超欄位（含各種命名變體）
    foreign = None
    invest = None
    for k, v in d.items():
        n = pn(v)
        if n is None: continue
        kk = k.replace(" ","").replace("　","")
        # 外資淨買賣超：找含「外資」且含「買賣超」或「淨」的欄位，但排除「自營商」
        if "外資" in kk and ("買賣超" in kk or "淨買" in kk) and "自營商" not in kk and foreign is None:
            foreign = n
        # 投信淨買賣超
        if "投信" in kk and ("買賣超" in kk or "淨買" in kk) and invest is None:
            invest = n

    return code, foreign, invest

def main():
    today = datetime.date.today()
    print("=" * 55)
    print(f"台灣股市資料抓取 {today}")
    print("=" * 55)

    # ── 1. 月營收 ─────────────────────────────────────────
    print("\n【上市月營收 t187ap05_L】")
    twse_rev = fetch(f"{BASE}/opendata/t187ap05_L", "月營收")

    # ── 2. 公司基本資料 ────────────────────────────────────
    print("\n【上市公司基本資料 t187ap03_L】")
    twse_info = fetch(f"{BASE}/opendata/t187ap03_L", "基本資料")

    # ── 3. 損益表 ──────────────────────────────────────────
    print("\n【損益表】")
    inc_ci   = fetch(f"{BASE}/opendata/t187ap06_L_ci",   "一般業")
    inc_basi = fetch(f"{BASE}/opendata/t187ap06_L_basi", "金融業")
    inc_fh   = fetch(f"{BASE}/opendata/t187ap06_L_fh",   "金控業")
    inc_ins  = fetch(f"{BASE}/opendata/t187ap06_L_ins",  "保險業")
    inc_bd   = fetch(f"{BASE}/opendata/t187ap06_L_bd",   "券商業")
    inc_mim  = fetch(f"{BASE}/opendata/t187ap06_L_mim",  "異業")
    all_income = inc_ci + inc_basi + inc_fh + inc_ins + inc_bd + inc_mim

    # ── 4. 收盤價+成交量 ───────────────────────────────────
    print("\n【每日成交 STOCK_DAY_ALL】")
    stock_day = fetch(f"{BASE}/exchangeReport/STOCK_DAY_ALL", "每日成交")

    # ── 5. 三大法人 T86 ────────────────────────────────────
    print("\n【三大法人 T86】")
    t86_raw = fetch(
        "https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALL",
        "三大法人"
    )

    # ── 6. 上櫃月營收 ──────────────────────────────────────
    print("\n【上櫃月營收 TPEx】")
    tpex_rev = fetch("https://www.tpex.org.tw/openapi/v1/mopsfin_t53", "上櫃月營收")

    # ── 7. FinMind 補充 ────────────────────────────────────
    print("\n【FinMind 基本資料】")
    fm_info = fetch_finmind("TaiwanStockInfo", "2020-01-01")

    # ── 載入既有資料（歷史月營收）──────────────────────────
    existing = {}
    data_path = os.path.join(OUT_DIR, "data.json")
    if os.path.exists(data_path):
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except: pass
    prev = {c["c"]: c for c in existing.get("companies", [])}

    # ── Build maps ────────────────────────────────────────
    ind_map, mkt_map, shares_map = {}, {}, {}

    for r in fm_info:
        sid = r.get("stock_id","")
        if len(sid) == 4:
            ind_map[sid] = r.get("industry_category","")
            mkt_map[sid] = "L" if r.get("type","") in ("twse","上市") else "O"

    for r in (twse_info if isinstance(twse_info, list) else []):
        code = str(r.get("公司代號","")).strip()
        if len(code) == 4:
            ind_map[code] = str(r.get("產業別","")).strip()
            mkt_map[code] = "L"
            sh = pn(r.get("已發行普通股數或TDR原股發行股數"))
            if sh: shares_map[code] = sh

    # 收盤價 & 市值
    price_map = {}
    for r in (stock_day if isinstance(stock_day, list) else []):
        code = str(r.get("Code","")).strip()
        price = pn(r.get("ClosingPrice"))
        if code and price: price_map[code] = price

    cap_map = {}
    for code, sh in shares_map.items():
        p = price_map.get(code)
        if p: cap_map[code] = round(p * sh / 1e8, 1)

    # 損益表 map（最近兩季 + YoY）
    fin_map = {}
    for r in all_income:
        code = str(r.get("公司代號","")).strip()
        if not code: continue
        rev = pn(r.get("營業收入"))
        if not rev or rev == 0: continue
        gp = calc_margin("營業毛利（毛損）淨額", "營業收入", r)
        op = calc_margin("營業利益（損失）", "營業收入", r)
        np_ = calc_margin("本期淨利（淨損）", "營業收入", r)
        yr = str(r.get("年度","")).strip()
        qt = str(r.get("季別","")).strip()
        period = f"{yr}Q{qt}"
        if code not in fin_map: fin_map[code] = []
        fin_map[code].append({"period": period, "gp": gp, "op": op, "np": np_, "rev": rev})

    fin_latest = {}
    for code, recs in fin_map.items():
        recs.sort(key=lambda x: x["period"], reverse=True)
        lat = recs[0]
        yoy_rec = recs[4] if len(recs) > 4 else None
        fin_latest[code] = {
            "gp": lat.get("gp"), "op": lat.get("op"), "np": lat.get("np"),
            "gp_yoy": safe_pct(lat.get("gp"), yoy_rec.get("gp")) if yoy_rec else None,
            "op_yoy": safe_pct(lat.get("op"), yoy_rec.get("op")) if yoy_rec else None,
            "period": lat.get("period","")
        }

    # T86 法人 map
    inst_map = {}
    t86_data   = t86_raw.get("data", [])   if isinstance(t86_raw, dict) else (t86_raw if isinstance(t86_raw, list) else [])
    t86_fields = t86_raw.get("fields", []) if isinstance(t86_raw, dict) else []
    print(f"  T86 fields sample: {t86_fields[:8]}")
    parsed_inst = 0
    for row in t86_data:
        code, foreign, invest = parse_t86_row(row, t86_fields)
        if not code: continue
        inst_map[code] = {
            "foreign": int(foreign or 0),
            "invest":  int(invest  or 0),
            "total":   int((foreign or 0) + (invest or 0))
        }
        parsed_inst += 1
    print(f"  ✓ 解析法人資料: {parsed_inst} 家")

    # ── 整理公司資料 ──────────────────────────────────────
    def build_company(code, name, market, rev, yoy, mom, ind, fin, inst, mktcap):
        p = prev.get(code, {})
        rev_hist = list(p.get("rev_hist", []))
        cur_m = rev_month or str(today)[:7]

        # 更新本月資料
        if not rev_hist or rev_hist[-1].get("m") != cur_m:
            rev_hist = rev_hist[-5:]  # 保留前 5 個月
            rev_hist.append({"m": cur_m, "y": round(yoy, 1) if yoy is not None else None})
        else:
            # 同月更新
            rev_hist[-1]["y"] = round(yoy, 1) if yoy is not None else None

        # 計算連續 YoY >= 門檻月數（預設門檻 5%，前端可調整）
        # 後端只存 rev_hist，前端動態計算連續月數
        # 但也預算一個 consec_yoy（以 5% 為基準）供快速參考
        consec = 0
        for item in reversed(rev_hist):
            if item.get("y") is not None and item["y"] >= 5:
                consec += 1
            else:
                break

        return {
            "c": code, "n": name, "m": market, "g": ind,
            "r": int(rev),
            "y": round(yoy, 1) if yoy is not None else None,
            "mo": round(mom, 1) if mom is not None else None,
            "gp": fin.get("gp"), "op": fin.get("op"), "np": fin.get("np"),
            "gp_yoy": fin.get("gp_yoy"), "op_yoy": fin.get("op_yoy"),
            "fin_period": fin.get("period",""),
            "inst_total": inst.get("total", 0),
            "inst_foreign": inst.get("foreign", 0),
            "inst_invest": inst.get("invest", 0),
            "mktcap": mktcap,
            "rev_hist": rev_hist,
            "consec_yoy": consec,
        }

    companies = []
    rev_month = ""

    for r in (twse_rev if isinstance(twse_rev, list) else []):
        code = str(r.get("公司代號","")).strip()
        if not code or len(code) != 4: continue
        rev = pn(r.get("營業收入-當月營收"))
        if not rev or rev <= 0: continue
        name = str(r.get("公司名稱","")).strip()
        yoy  = pn(r.get("營業收入-去年同月增減(%)"))
        mom  = pn(r.get("營業收入-上月比較增減(%)"))
        if yoy is None: yoy = safe_pct(rev, pn(r.get("營業收入-去年當月營收")))
        if r.get("出表日期") and not rev_month: rev_month = str(r["出表日期"])
        ind  = str(r.get("產業別","")).strip() or ind_map.get(code,"")
        fin  = fin_latest.get(code, {})
        inst = inst_map.get(code, {})
        mktcap = cap_map.get(code)
        companies.append(build_company(code, name, mkt_map.get(code,"L"), rev, yoy, mom, ind, fin, inst, mktcap))

    for r in (tpex_rev if isinstance(tpex_rev, list) else []):
        code = str(r.get("SecuritiesCompanyCode") or r.get("公司代號") or "").strip()
        if not code or len(code) != 4: continue
        rev = pn(r.get("MonthlyRevenue") or r.get("當月營收"))
        if not rev or rev <= 0: continue
        name = str(r.get("CompanyName") or r.get("公司名稱") or "").strip()
        yoy_raw = r.get("YoYGrowthRate") or r.get("MonthlyRevenueGrowthRate")
        mom_raw = r.get("MoMGrowthRate")
        yoy = pn(yoy_raw) if yoy_raw not in (None,"","N/A") else safe_pct(rev, pn(r.get("RevenueLYSameMonth") or r.get("去年同月營收")))
        mom = pn(mom_raw) if mom_raw not in (None,"","N/A") else None
        fin  = fin_latest.get(code, {})
        inst = inst_map.get(code, {})
        mktcap = cap_map.get(code)
        companies.append(build_company(code, name, "O", rev, yoy, mom, ind_map.get(code,""), fin, inst, mktcap))

    companies.sort(key=lambda x: x["c"])
    listed = sum(1 for c in companies if c["m"] == "L")
    otc    = sum(1 for c in companies if c["m"] == "O")

    # Layer 統計（以預設門檻）
    l1 = sum(1 for c in companies if c["consec_yoy"] >= 3)
    l2 = sum(1 for c in companies if c["inst_total"] > 0)
    l3 = sum(1 for c in companies if c.get("mktcap") and c["mktcap"] >= 50)
    print(f"\n✓ 共 {len(companies)} 家（上市 {listed}，上櫃 {otc}）")
    print(f"  Layer1(連續3月YoY≥5%) {l1} 家 | Layer2(法人買超) {l2} 家 | Layer3(市值≥50億) {l3} 家")

    stats = {
        "total": len(companies), "listed": listed, "otc": otc,
        "yoy_pos": sum(1 for c in companies if c["y"] is not None and c["y"] > 0),
        "yoy_neg": sum(1 for c in companies if c["y"] is not None and c["y"] < 0),
        "gross_med": median([c["gp"] for c in companies if c["gp"] is not None]),
        "net_med":   median([c["np"] for c in companies if c["np"] is not None]),
        "rev_month": rev_month,
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "layer_counts": {"l1": l1, "l2": l2, "l3": l3}
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
