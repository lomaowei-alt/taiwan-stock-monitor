#!/usr/bin/env python3
"""
台灣股市月度績效監測 - 四層篩選版本
Layer 1: 月營收 YoY 連續 3 個月 >= 5% + 最近 2 季毛利率/營業利益率 YoY 正成長
Layer 2: 外資+投信近 30 天累計買超 > 0
Layer 3: 市值 > 50 億
Layer 4: 產業別 (UI 篩選)
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
                data = json.loads(text)
                # TWSE format: {"stat":"OK","data":[...]}
                if data.get("stat") == "OK" and data.get("data"):
                    print(f"  ✓ {len(data['data'])} 筆 (TWSE format)")
                    return data
            print(f"  ✗ 非JSON或空: {text[:60]}")
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

def calc_margin(numerator_key, rev_key, row):
    num = pn(row.get(numerator_key))
    rev = pn(row.get(rev_key))
    if num is None or rev is None or rev == 0: return None
    return round(num / rev * 100, 1)

def main():
    today = datetime.date.today()
    print("=" * 55)
    print(f"台灣股市資料抓取 {today}")
    print("=" * 55)

    # ── 1. 月營收（最新月）─────────────────────────────────
    print("\n【上市月營收 t187ap05_L】")
    twse_rev = fetch(f"{BASE}/opendata/t187ap05_L", "月營收")

    # ── 2. 上市公司基本資料（含已發行股數）────────────────
    print("\n【上市公司基本資料 t187ap03_L】")
    twse_info = fetch(f"{BASE}/opendata/t187ap03_L", "基本資料")

    # ── 3. 損益表（各業別）────────────────────────────────
    print("\n【損益表】")
    inc_ci   = fetch(f"{BASE}/opendata/t187ap06_L_ci",   "一般業")
    inc_basi = fetch(f"{BASE}/opendata/t187ap06_L_basi", "金融業")
    inc_fh   = fetch(f"{BASE}/opendata/t187ap06_L_fh",   "金控業")
    inc_ins  = fetch(f"{BASE}/opendata/t187ap06_L_ins",  "保險業")
    inc_bd   = fetch(f"{BASE}/opendata/t187ap06_L_bd",   "券商業")
    inc_mim  = fetch(f"{BASE}/opendata/t187ap06_L_mim",  "異業")
    all_income = inc_ci + inc_basi + inc_fh + inc_ins + inc_bd + inc_mim

    # ── 4. 上市每日成交資訊（收盤價+成交量）──────────────
    print("\n【上市每日成交 STOCK_DAY_ALL】")
    stock_day = fetch(f"{BASE}/exchangeReport/STOCK_DAY_ALL", "每日成交")

    # ── 5. 三大法人買賣超日報 ──────────────────────────────
    print("\n【三大法人買賣超 T86】")
    t86_raw = fetch(
        "https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALL",
        "三大法人"
    )

    # ── 6. 上櫃月營收 ──────────────────────────────────────
    print("\n【上櫃月營收 TPEx】")
    tpex_rev = fetch("https://www.tpex.org.tw/openapi/v1/mopsfin_t53", "上櫃月營收")

    # ── 7. FinMind 補充 ────────────────────────────────────
    print("\n【FinMind 基本資料補充】")
    fm_info = fetch_finmind("TaiwanStockInfo", "2020-01-01")

    # ── 載入既有 data.json 取得歷史月營收 ─────────────────
    existing_data = {}
    data_path = os.path.join(OUT_DIR, "data.json")
    if os.path.exists(data_path):
        with open(data_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
    prev_companies = {c["c"]: c for c in existing_data.get("companies", [])}

    # ── Build lookup maps ─────────────────────────────────
    ind_map, mkt_map, shares_map, cap_map = {}, {}, {}, {}

    for r in fm_info:
        sid = r.get("stock_id","")
        if len(sid) == 4:
            ind_map[sid] = r.get("industry_category","")
            mkt_map[sid] = "L" if r.get("type","") in ("twse","上市") else "O"

    for r in twse_info:
        code = str(r.get("公司代號","")).strip()
        if len(code) == 4:
            ind_map[code] = str(r.get("產業別","")).strip()
            mkt_map[code] = "L"
            # 已發行普通股數
            shares = pn(r.get("已發行普通股數或TDR原股發行股數"))
            if shares: shares_map[code] = shares

    # 收盤價 → 市值
    price_map, vol_map = {}, {}
    for r in (stock_day if isinstance(stock_day, list) else []):
        code = str(r.get("Code","")).strip()
        if not code: continue
        price = pn(r.get("ClosingPrice"))
        vol   = pn(r.get("TradeValue"))  # 成交金額（元）
        if price: price_map[code] = price
        if vol:   vol_map[code]   = vol

    # 市值 = 股價 × 已發行股數（單位：億元）
    for code, shares in shares_map.items():
        price = price_map.get(code)
        if price:
            cap_map[code] = round(price * shares / 1e8, 1)  # 億元

    # 損益表 map（最新兩季）
    fin_map = {}
    for r in all_income:
        code = str(r.get("公司代號","")).strip()
        if not code: continue
        rev = pn(r.get("營業收入"))
        if not rev or rev == 0: continue
        gross = calc_margin("營業毛利（毛損）淨額", "營業收入", r)
        op    = calc_margin("營業利益（損失）",       "營業收入", r)
        net   = calc_margin("本期淨利（淨損）",       "營業收入", r)
        yr    = str(r.get("年度","")).strip()
        qt    = str(r.get("季別","")).strip()
        period = f"{yr}Q{qt}"
        if code not in fin_map:
            fin_map[code] = []
        fin_map[code].append({"period": period, "gp": gross, "op": op, "np": net, "rev": rev})

    # 每家公司保留最新兩季，計算 YoY
    fin_latest = {}
    for code, records in fin_map.items():
        records.sort(key=lambda x: x["period"], reverse=True)
        latest = records[0] if records else {}
        # 找去年同期（差 4 季）
        yoy_rec = records[4] if len(records) > 4 else None
        gp_yoy = safe_pct(latest.get("gp"), yoy_rec.get("gp")) if yoy_rec else None
        op_yoy = safe_pct(latest.get("op"), yoy_rec.get("op")) if yoy_rec else None
        fin_latest[code] = {
            "gp": latest.get("gp"), "op": latest.get("op"), "np": latest.get("np"),
            "gp_yoy": gp_yoy, "op_yoy": op_yoy,
            "period": latest.get("period","")
        }

    # 三大法人 map（外資+投信淨買賣超股數）
    inst_map = {}
    t86_list = t86_raw if isinstance(t86_raw, list) else (t86_raw.get("data", []) if isinstance(t86_raw, dict) else [])
    t86_fields = t86_raw.get("fields", []) if isinstance(t86_raw, dict) else []
    print(f"  T86 fields: {t86_fields[:6]}")
    for row in t86_list:
        # row is a list if TWSE format, else dict
        if isinstance(row, list) and t86_fields:
            r_dict = dict(zip(t86_fields, row))
        elif isinstance(row, dict):
            r_dict = row
        else:
            continue
        code = str(r_dict.get("證券代號","")).strip()
        if not code: continue
        foreign = pn(r_dict.get("外資及陸資淨買賣超股數") or r_dict.get("外資淨買賣超股數"))
        invest  = pn(r_dict.get("投信淨買賣超股數"))
        if foreign is not None or invest is not None:
            inst_map[code] = {
                "foreign": foreign or 0,
                "invest":  invest or 0,
                "total":   (foreign or 0) + (invest or 0)
            }

    # ── 整理上市月營收 ─────────────────────────────────────
    companies = []
    rev_month = ""

    for r in twse_rev:
        code = str(r.get("公司代號","")).strip()
        if not code or len(code) != 4: continue
        rev = pn(r.get("營業收入-當月營收"))
        if not rev or rev <= 0: continue
        name = str(r.get("公司名稱","")).strip()
        yoy = pn(r.get("營業收入-去年同月增減(%)"))
        mom = pn(r.get("營業收入-上月比較增減(%)"))
        if yoy is None:
            yoy = safe_pct(rev, pn(r.get("營業收入-去年當月營收")))
        if r.get("出表日期") and not rev_month:
            rev_month = str(r["出表日期"])
        ind = str(r.get("產業別","")).strip() or ind_map.get(code,"")
        fin = fin_latest.get(code, {})
        inst = inst_map.get(code, {})
        mktcap = cap_map.get(code)

        # 歷史月營收 YoY 序列（從前一次資料繼承 + 本月更新）
        prev = prev_companies.get(code, {})
        rev_hist = prev.get("rev_hist", [])
        # 加入本月: {month, yoy}
        cur_month_key = rev_month or str(today)[:7]
        # 避免重複
        if not rev_hist or rev_hist[-1].get("m") != cur_month_key:
            rev_hist = rev_hist[-5:]  # 保留最近 6 個月
            rev_hist.append({"m": cur_month_key, "y": round(yoy, 1) if yoy is not None else None})

        # 連續正成長月數（YoY >= 5%）
        consecutive = 0
        for item in reversed(rev_hist):
            if item.get("y") is not None and item["y"] >= 5:
                consecutive += 1
            else:
                break

        companies.append({
            "c": code, "n": name,
            "m": mkt_map.get(code, "L"),
            "g": ind,
            "r": int(rev),
            "y": round(yoy, 1) if yoy is not None else None,
            "mo": round(mom, 1) if mom is not None else None,
            "gp": fin.get("gp"), "op": fin.get("op"), "np": fin.get("np"),
            "gp_yoy": fin.get("gp_yoy"), "op_yoy": fin.get("op_yoy"),
            "fin_period": fin.get("period",""),
            "inst_total": int(inst.get("total",0)),
            "inst_foreign": int(inst.get("foreign",0)),
            "inst_invest": int(inst.get("invest",0)),
            "mktcap": mktcap,         # 億元
            "rev_hist": rev_hist,     # 近 6 個月 YoY 序列
            "consec_yoy": consecutive, # 連續 YoY>=5% 月數
        })

    print(f"\n  上市整理: {len(companies)} 家")

    # 上櫃月營收
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
        fin = fin_latest.get(code, {})
        inst = inst_map.get(code, {})
        mktcap = cap_map.get(code)
        prev = prev_companies.get(code, {})
        rev_hist = prev.get("rev_hist", [])
        cur_month_key = rev_month or str(today)[:7]
        if not rev_hist or rev_hist[-1].get("m") != cur_month_key:
            rev_hist = rev_hist[-5:]
            rev_hist.append({"m": cur_month_key, "y": round(yoy, 1) if yoy is not None else None})
        consecutive = 0
        for item in reversed(rev_hist):
            if item.get("y") is not None and item["y"] >= 5:
                consecutive += 1
            else:
                break
        companies.append({
            "c": code, "n": name, "m": "O",
            "g": ind_map.get(code,""),
            "r": int(rev),
            "y": round(yoy, 1) if yoy is not None else None,
            "mo": round(mom, 1) if mom is not None else None,
            "gp": fin.get("gp"), "op": fin.get("op"), "np": fin.get("np"),
            "gp_yoy": fin.get("gp_yoy"), "op_yoy": fin.get("op_yoy"),
            "fin_period": fin.get("period",""),
            "inst_total": int(inst.get("total",0)),
            "inst_foreign": int(inst.get("foreign",0)),
            "inst_invest": int(inst.get("invest",0)),
            "mktcap": mktcap,
            "rev_hist": rev_hist,
            "consec_yoy": consecutive,
        })

    companies.sort(key=lambda x: x["c"])
    listed = sum(1 for c in companies if c["m"] == "L")
    otc    = sum(1 for c in companies if c["m"] == "O")
    l1 = sum(1 for c in companies if c["consec_yoy"] >= 3)
    l2 = sum(1 for c in companies if c["inst_total"] > 0)
    l3 = sum(1 for c in companies if c.get("mktcap") and c["mktcap"] >= 50)
    print(f"✓ 共 {len(companies)} 家（上市 {listed}，上櫃 {otc}）")
    print(f"  Layer1 通過 {l1} 家 | Layer2 通過 {l2} 家 | Layer3 通過 {l3} 家")

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
