# 台灣股市月度績效監測

每天自動從台灣證券交易所 & 櫃買中心官方 API 抓取資料，透過 GitHub Pages 提供免費的互動式儀表板。

## 功能

- 監測上市 + 上櫃約 1,700 家公司
- 每天早上 10:00（台灣時間）自動更新
- 顯示月營收、YoY%、MoM%、毛利率%、營業利益率%、淨利率%
- 可依公司代號/名稱搜尋、依產業篩選、依任意欄位排序

## 資料來源

- [台灣證券交易所 OpenAPI](https://openapi.twse.com.tw/)
- [證券櫃檯買賣中心 OpenAPI](https://www.tpex.org.tw/openapi/)

## 技術架構

```
GitHub Actions（每日排程）
    │
    ▼
scripts/fetch_data.py   ← 從官方 API 抓資料
    │
    ▼
docs/data.json          ← 靜態 JSON 資料檔
    │
    ▼
docs/index.html         ← GitHub Pages 網站（純前端，讀取 data.json）
```

完全免費，無需伺服器，無需資料庫。
