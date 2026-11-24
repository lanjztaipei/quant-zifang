# Quant Zifang（張良）

> *The strategist in the command tent. A modular decision-support system for daily order planning. (For fully automated execution, see `quant-hanxin`)*

每日開盤前一次頻率的「交易掛單決策支援系統」，首個策略模組為 **波動率自適應網格（VAG Grid）**。

## 專案架構

```text
backend/
├── app/
│   ├── core/            # 純函式策略核心（Decimal prec=40、XNYS 日曆、Wilder ATR、VAG Grid 與結算運算）
│   ├── providers/       # 行情介面、yfinance 抓取器與 ATR 快取（data/atr_cache.json）
│   ├── storage/         # filelock + 原子寫入 JSON 持久化（data/holdings.json）
│   ├── schemas/         # FastAPI Pydantic 請求/回應模型（Decimal 一律字串輸出）
│   ├── routers/         # /api/v1/market、/api/v1/calculator、/api/v1/holdings
│   ├── config.py        # 環境變數設定（DATA_DIR、CORS_ORIGINS）
│   ├── dependencies.py  # FastAPI 依賴注入
│   └── main.py          # FastAPI 應用工廠、CORS 與統一錯誤處理
├── tests/               # pytest 全 mock 測試（涵蓋所有黃金案例與 API 守衛）
├── .python-version      # 鎖定 Python 版本（3.12）
├── pyproject.toml       # 專案依賴、dev 依賴與 pytest 設定（單一真相來源）
└── uv.lock              # 精確套件版本鎖定檔
```

## 快速開始（使用 `uv`）

先確認已安裝 [uv](https://docs.astral.sh/uv/)（Windows PowerShell 安裝方式：`irm https://astral.sh/uv/install.ps1 | iex`）。

### 1. 同步虛擬環境與相依套件

```powershell
cd backend
uv sync --frozen
```

> 若在正式部署環境不需要測試工具，可改用 `uv sync --frozen --no-dev`。

### 2. 啟動後端服務（Uvicorn）

```powershell
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

啟動後可開啟互動式 API 文件：`http://127.0.0.1:8000/docs`

#### 環境變數（選填）

```powershell
$env:DATA_DIR = "data"
$env:CORS_ORIGINS = "http://localhost:3000,http://localhost:5173"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. 執行測試（Pytest，全 mock 不連網）

```powershell
cd backend
uv run pytest -v
```

## API 端點總覽（前綴 `/api/v1`）

| Method | Path | 說明 |
| --- | --- | --- |
| `GET` | `/api/v1/market/{symbol}?force_refresh=false` | 取得最新已收盤交易日收盤價、ATR14%、ATR50% 與快取狀態 |
| `POST` | `/api/v1/calculator/compute` | 無狀態試算策略參數、儀表板、既有持股子母單與未來網格表 |
| `GET` | `/api/v1/holdings` | 列出所有已儲存的股票代號 |
| `GET` | `/api/v1/holdings/{symbol}` | 取得單一代號的策略參數與持股明細 |
| `PUT` | `/api/v1/holdings/{symbol}` | 建立或更新策略參數（無持股時依 `Q0` 自動建立底倉） |
| `DELETE` | `/api/v1/holdings/{symbol}` | 刪除該代號所有設定與持股 |
| `POST` | `/api/v1/holdings/{symbol}/lots` | 新增單筆持股（重複 `base` 回 `409 BASE_LOT_EXISTS`） |
| `PUT` | `/api/v1/holdings/{symbol}/lots/{lot_id}` | 修改單筆持股 |
| `DELETE` | `/api/v1/holdings/{symbol}/lots/{lot_id}` | 刪除單筆持股 |
| `POST` | `/api/v1/holdings/{symbol}/lots/{lot_id}/settle` | 停利結算 `grid` lot、滾動已實現獲利與少賣留股併入底倉 |
