#!/usr/bin/env python3
"""
台灣股市月度績效監測
先做 API 連線診斷，再依結果決定抓取策略
"""
import requests, json, os, time, datetime

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
TOKEN = os.environ.get("FINMIND_TOKEN", "")

S = {"Accept": "application/json",
     "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

def get(url, **kwargs):
    try:
        r = requests.get(url, headers=S, timeout=30, **kwargs)
        return r.status_code, r.text[:200]
    except Exception as e:
        return 0, str(e)

def post(url, data):
    try:
        r = requests.post(url, data=data, headers={**S,
            "Referer": "https://mops.twse.com.tw/",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
        }, timeout=30)
        return r.status_code, r.text[:200]
    except Exception as e:
        return 0, str(e)

def pn(v):
    if v is None or str(v).strip() in ("","N/A","--","－"): return None
    try: return float(str(v).replace(",",""))
    except: return None

def calc_pct(a, b):
    if a is None or b is None or b == 0: return None
    return round((a-b)/abs(b)*100, 1)

def median(vals):
    if not vals: return None
    s = sorted(vals); m = len(s)//2
    return round(s[m] if len(s)%2 else (s[m-1]+s[m])/2, 1)

def try_twse():
    """嘗試從 TWSE openapi 抓資料"""
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    sc, body = get(url)
    print(f"  TWSE openapi: {sc} | {body[:80]}")
    if sc == 200 and body.strip().startswith("["):
        try:
            data = json.loads(body + requests.get(url, headers=S, timeout=30).text[200:])
            return data
        except:
            r = requests.get(url, headers=S, timeout=30)
            if r.status_code == 200:
                t = r.text.strip()
                if t.startswith("["):
                    return json.loads(t)
    return []

def try_mops():
    """嘗試從 MOPS 抓全市場月營收"""
    today = datetime.date.today()
    yr = today.year - 1911
    mo = today.month - 1 or 12
    if mo == 12: yr -= 1

    url = "https://mops.twse.com.tw/mops/web/ajax_t05st10_ifrs"
    sc, body = post(url, {
        "encodeURIComponent":"1","step":"1","firstin":"1","off":"1",
        "TYPEK":"all","isnew":"false","co_id":"","year":str(yr),"month":f"{mo:02d}"
    })
    print(f"  MOPS monthly: {sc} | {body[:80]}")
    return sc, body

def try_finmind_free():
    """不帶 token 試 FinMind 免費資料"""
    url = "https://api.finmindtrade.com/api/v4/data"
    sc, body = get(url, params={"dataset":"TaiwanStockInfo","start_date":"2020-01-01"})
    print(f"  FinMind (no token): {sc} | {body[:80]}")
    if sc == 200:
        try:
            d = json.loads(requests.get(url, params={"dataset":"TaiwanStockInfo","start_date":"2020-01-01"}, headers=S, timeout=30).text)
            if d.get("status") == 200:
                return d.get("data", [])
        except: pass
    return []

def try_twse_direct():
    """嘗試 TWSE 另一個端點"""
    urls = [
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999",
        "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json",
    ]
    for url in urls:
        sc, body = get(url)
        print(f"  TWSE direct: {sc} | {body[:80]}")
        if sc == 200 and (body.strip().startswith("{") or body.strip().startswith("[")):
            return True
    return False

def main():
    print("="*50)
    print(f"台灣股市資料抓取 {datetime.date.today()}")
    print("="*50)

    print("\n【API 連線診斷】")
    
    # 1. 先試 TWSE openapi
    print("→ 測試 TWSE openapi...")
    twse_rev = []
    sc, body = get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
    print(f"  status={sc}, starts_with_bracket={body.strip().startswith('[')}")
    if sc == 200 and body.strip().startswith("["):
        try:
            r_full = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", headers=S, timeout=60)
            twse_rev = json.loads(r_full.text)
            print(f"  ✓ TWSE openapi 月營收: {len(twse_rev)} 筆")
        except Exception as e:
            print(f"  ✗ parse error: {e}")

    # 2. 試 TWSE 基本資料
    twse_info = []
    sc2, body2 = get("https://openapi.twse.com.tw/v1/opendata/t187ap03_2")
    if sc2 == 200 and body2.strip().startswith("["):
        try:
            twse_info = json.loads(requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_2", headers=S, timeout=60).text)
            print(f"  ✓ TWSE 基本資料: {len(twse_info)} 筆")
        except: pass

    # 3. 試 TPEX
    tpex_rev = []
    sc3, body3 = get("https://www.tpex.org.tw/openapi/v1/mopsfin_t53")
    print(f"  TPEX status={sc3}, preview={body3[:60]}")
    if sc3 == 200 and body3.strip().startswith("["):
        try:
            tpex_rev = json.loads(requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t53", headers=S, timeout=60).text)
            print(f"  ✓ TPEX 月營收: {len(tpex_rev)} 筆")
        except: pass

    # 4. 試 FinMind (TaiwanStockInfo 不需要 token)
    fm_info = []
    try:
        r = requests.get("https://api.finmindtrade.com/api/v4/data",
            params={"dataset":"TaiwanStockInfo","start_date":"2020-01-01"},
            headers=S, timeout=30)
        print(f"  FinMind status={r.status_code}")
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == 200:
                fm_info = d.get("data",[])
                print(f"  ✓ FinMind StockInfo: {len(fm_info)} 筆")
    except Exception as e:
        print(f"  FinMind error: {e}")

    print(f"\n【診斷結果】")
    print(f"  TWSE 月營收: {len(twse_rev)} 筆")
    print(f"  TWSE 基本資料: {len(twse_info)} 筆")
    print(f"  TPEX 月營收: {len(tpex_rev)} 筆")
    print(f"  FinMind StockInfo: {len(fm_info)} 筆")

    # 整合可用資料
    ind_map = {}
    for r in twse_info:
        code = (r.get("公司代號") or r.get("股票代號") or "").strip()
        if code: ind_map[code] = (r.get("產業類別") or "").strip()
    for r in fm_info:
        sid = r.get("stock_id","")
        if len(sid)==4 and sid not in ind_map:
            ind_map[sid] = r.get("industry_category","")

    companies = []
    rev_month = ""

    for r in twse_rev:
        code = (r.get("公司代號") or "").strip()
        if not code or len(code) != 4: continue
        rev = pn(r.get("當月營收") or r.get("revenue"))
        if not rev or rev <= 0: continue
        name = (r.get("公司名稱") or "").strip()
        yoy_raw = r.get("當月營收年增率")
        mom_raw = r.get("當月營收月增率")
        yoy = float(yoy_raw) if yoy_raw not in (None,"","N/A") else calc_pct(rev, pn(r.get("去年同月營收")))
        mom = float(mom_raw) if mom_raw not in (None,"","N/A") else calc_pct(rev, pn(r.get("上月營收")))
        if r.get("出表日期") and not rev_month: rev_month = r["出表日期"]
        companies.append({"c":code,"n":name,"m":"L","g":ind_map.get(code,""),
                          "r":int(rev),"y":round(yoy,1) if yoy else None,
                          "mo":round(mom,1) if mom else None,"gp":None,"op":None,"np":None})

    for r in tpex_rev:
        code = (r.get("SecuritiesCompanyCode") or r.get("公司代號") or "").strip()
        if not code or len(code) != 4: continue
        rev = pn(r.get("MonthlyRevenue") or r.get("當月營收"))
        if not rev or rev <= 0: continue
        name = (r.get("CompanyName") or r.get("公司名稱") or "").strip()
        yoy_raw = r.get("YoYGrowthRate") or r.get("MonthlyRevenueGrowthRate")
        mom_raw = r.get("MoMGrowthRate")
        yoy = float(yoy_raw) if yoy_raw not in (None,"","N/A") else calc_pct(rev, pn(r.get("RevenueLYSameMonth")))
        mom = float(mom_raw) if mom_raw not in (None,"","N/A") else calc_pct(rev, pn(r.get("RevenuePrevMonth")))
        companies.append({"c":code,"n":name,"m":"O","g":ind_map.get(code,""),
                          "r":int(rev),"y":round(yoy,1) if yoy else None,
                          "mo":round(mom,1) if mom else None,"gp":None,"op":None,"np":None})

    listed = sum(1 for c in companies if c["m"]=="L")
    otc = sum(1 for c in companies if c["m"]=="O")
    print(f"\n✓ 共整理 {len(companies)} 家（上市 {listed}，上櫃 {otc}）")

    stats = {
        "total":len(companies),"listed":listed,"otc":otc,
        "yoy_pos":sum(1 for c in companies if c["y"] and c["y"]>0),
        "yoy_neg":sum(1 for c in companies if c["y"] and c["y"]<0),
        "gross_med":None,"net_med":None,
        "rev_month":rev_month,
        "updated":datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "data.json")
    with open(out,"w",encoding="utf-8") as f:
        json.dump({"stats":stats,"companies":companies},f,ensure_ascii=False,separators=(",",":"))
    print(f"✓ 輸出 {out} ({os.path.getsize(out)//1024} KB)")
    print("完成！")

if __name__ == "__main__":
    main()
