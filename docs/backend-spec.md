# Quant Zifang（張良）後端現行規格（VAG Grid）

> *The strategist in the command tent. A modular decision-support system for daily order planning. (For fully automated execution, see `quant-hanxin`)*
>
> **文件定位**：本文件為 `quant-zifang` 後端系統的**現行活規格（Single Source of Truth）**，隨策略公式與 API 變更同步維護。專案建立時的原始啟動 prompt 歷史紀錄保留於 [docs/archive/backend_prompt.md](archive/backend_prompt.md)（唯讀歸檔）。

---

## 1. 系統架構與全域規則

- **純函式核心**：`backend/app/core/` 僅含純函式與領域模型，不依賴 FastAPI、yfinance 或檔案 I/O；行情來源（`MarketDataFetcher`）、持久化（`HoldingsRepository`）與現在時間（`Clock`）皆透過 Protocol 介面注入。
- **百分比表示**：系統內部與 API 的比例／百分比一律以小數表示（例如 `0.25%` 表示為 `0.0025`）。
- **數值運算**：一律使用 `Decimal`（`getcontext().prec = 40`、`DefaultContext.prec = 40`），禁止以 `float` 進行金融計算；外部浮點數（如 yfinance K 棒）皆透過 `Decimal(str(val))` 轉換並驗證為有限數值。
- **捨入規則**：一律採用銀行家捨入（`ROUND_HALF_EVEN`），僅在公式明確標示捨入處與 API 輸出時捨入，其餘中間計算保留 40 位全精度：
  - **價格與金額（`round_price`）**：小數第 2 位（`0.01`）。
  - **追蹤緩衝 `y`（`round_trail_pct`）**：百分比小數第 2 位，即小數第 4 位（`0.0001`，因券商追蹤掛單僅能輸入至百分比兩位小數）；**計算後立即捨入，後續所有用到 `y` 的公式均使用捨入後的值**；API 輸出仍以 6 位小數字串格式呈現（如 `"0.008500"`）以與其他比例欄位一致。
  - **其餘比例（`round_ratio`）**：小數第 6 位（`0.000001`）。
- **股數取整（`floor_int`）**：所有無條件捨去（含 `⌊K/a⌋`、`Q0`、`Q_j`、`retain_shares`）皆先以 `ROUND_HALF_EVEN` 量化至小數第 10 位（`0.0000000001`），再向下取整（`ROUND_FLOOR`）。
- **API 數值格式**：所有 `Decimal` 欄位一律輸出為字串，避免 JSON 浮點誤差。
- **統一錯誤格式**：HTTP 錯誤回應皆為 `{"code": "...", "message": "..."}`：
  - `422`：`VALIDATION_ERROR`
  - `404`：`NOT_FOUND`
  - `409`：`BASE_LOT_EXISTS`
- **策略警示格式**：`warnings: [{"code": "...", "message": "..."}]`（繁體中文）；同時命中多項時全數回傳，固定順序為 `NO_POSITION`、`BUDGET_EXHAUSTED`、`GRID_FULL`。
- **持久化與環境設定**：
  - 使用 `pydantic-settings`（`BaseSettings`）自動載入環境變數與 `.env`（系統環境變數優先，專案根目錄附 `.env.example` 範本）；支援 `ENV`（`dev | prod`，預設 `dev`）、`LOG_LEVEL`（`DEBUG | INFO | WARNING | ERROR | CRITICAL`，預設 `INFO`）、`DATA_DIR`（預設 `data/`）與 `CORS_ORIGINS`（逗號分隔 `http(s)://host[:port]`，禁止萬用字元 `*` 或結尾斜線，預設允許本機 `localhost` / `127.0.0.1` 的 `3000`、`5173`、`8000` 埠），並相容 `ZIFANG_*` 前綴別名。
  - JSON 寫檔一律透過 `filelock` 加鎖並原子寫入（`JsonFileStore`）。
  - 應用啟動元件初始化（日誌層級、資料目錄建立、Windows 非 ASCII `CURL_CA_BUNDLE` 檢查、`MarketDataProvider` 與 `JsonHoldingsStore` 建置）與優雅關閉皆統一透過 FastAPI `lifespan` 管理，避免在併發請求路徑中修改全域環境變數。

---

## 2. 行情與 ATR 引擎（`MarketDataProvider`）

1. **最新已收盤交易日（`get_latest_closed_session(now)`）**：
   - 使用 `exchange_calendars`（`XNYS`）以美東時間（`America/New_York`）判斷，要求傳入 timezone-aware `datetime`。
   - 須滿足「現在時間 ≥ 該交易日收盤時間（含提前收盤日，如感恩節隔天 13:00 ET）+ 15 分鐘」，該交易日才視為已收盤；否則回推至上一個已收盤交易日。
2. **快取（`data/atr_cache.json`）**：
   - 鍵為 `SYMBOL_YYYY-MM-DD`（代號轉大寫），值含 `trading_date`、`close`（2 位小數）、`atr_14_pct`（6 位小數）、`atr_50_pct`（6 位小數）、`fetched_at`。
   - 命中即回傳（`cache_hit = true`）；`force_refresh = true` 時略過快取重新抓取。
3. **行情抓取與過濾（`YFinanceFetcher` + `filter_closed_bars`）**：
   - 透過 `yfinance.Ticker(symbol).history(period="2y", auto_adjust=True)` 抓取近 2 年日線，禁止使用 `.info`。
   - `filter_closed_bars(bars, latest_session)` 僅保留日期 ≤ 最新已收盤交易日的 K 棒（剔除盤中未收盤 K 棒）。
   - 查無資料回 `404 NOT_FOUND`；過濾後 K 棒少於 `51` 根回 `422 VALIDATION_ERROR`。
   - 若最後一根 K 棒日期落後於預期的最新已收盤交易日（資料延遲或停牌），仍照常回傳實際資料日期並附上 `STALE_MARKET_DATA` 警示，且**不寫入快取**。
4. **Wilder ATR 計算（`compute_wilder_atr(bars, n)`）**：
   - 接收至少 `n + 1` 根已收盤 K 棒，分別計算 `n = 14` 與 `n = 50` 的 Wilder ATR 與 ATR%。
   - `TR = max(H − L, |H − 前收|, |L − 前收|)`（自第 2 根起共 `len(bars) − 1` 筆）。
   - 首值（第 `n + 1` 根）為前 `n` 個 TR 之簡單平均；後續 `ATR_t = (ATR_{t−1} × (n − 1) + TR_t) / n`。
   - `ATR% = 最新 ATR / 最新收盤價`（API 輸出與快取儲存以 `ROUND_HALF_EVEN` 取至小數第 6 位）。

---

## 3. 策略核心（VAG Grid `StrategyEngine`）

### 3.1 輸入與驗證

- **輸入欄位**：`symbol`、`B`、`initial_price`、`P0`（預設 `0.30`）、`a`（預設 `0.6`）、`b`（預設 `0.1`）、`c`（預設 `0.5`）、`K`（預設 `6`）、`realized_profit`（預設 `0`）、`base_profit_pool`（預設 `0`）、`atr_14_pct`、`atr_50_pct`、`holdings`（預設空）、`current_price`（選填）。
- `initial_price` 與 `P0` 皆為必填；實戰模式下 `initial_price` 不參與網格價格計算，`P0` 作為網格停利獲利撥入底倉獲利池的比例。
- **驗證條件（不通過回 `422 VALIDATION_ERROR`）**：
  - `symbol` 轉大寫後須符合 `^[A-Z0-9.\-]{1,10}$`
  - `B > 0`、`initial_price > 0`、`0 < P0 ≤ 1`
  - `a > 0`、`b ≥ 0`、`c > 0`、`K > 0`
  - `realized_profit ≥ 0`、`base_profit_pool ≥ 0`
  - `0 < atr_14_pct < 1`、`0 < atr_50_pct < 1`、`x < 1`、`⌊K/a⌋ ≤ 100`
  - `current_price` 若提供必須 `> 0`
  - 每筆 lot：`type` 僅能為 `base`（最多 1 筆）或 `grid`、`price > 0`、`shares` 為 `≥ 1` 的整數

### 3.2 核心衍生參數

- `B_eff = B + realized_profit`
- `ATR_eff = max(atr_50_pct, atr_14_pct)`
- `x = a × ATR_eff`（單層網格間距）
- `y = round_trail_pct(b × atr_14_pct)`（追蹤緩衝，取至小數第 4 位即百分比第 2 位；後續所有公式皆使用此捨入值）
- `z = c × atr_14_pct`（單層停利間距）
- `N = max(1, ⌊K/a⌋)`（總網格層數）
- `max_safe_drop = round_ratio(1 − (1 − x)^N)`

### 3.3 模式與錨點

- **新建倉模式（`mode = "new"`，`holdings` 為空）**：
  - `Q0 = ⌊B_eff × P0 / initial_price⌋`、`C_now = Q0 × initial_price`、`P_anchor = initial_price`（`Q0 = 0` 時為 `null`）、`m = 0`。
  - `Q0 > 0` 時，回傳一筆建議底倉（`type = "base"`、`id = null`、`price = initial_price`、`shares = Q0`）；`Q0 = 0` 時 `holdings = []`。
- **實戰模式（`mode = "rebalance"`，`holdings` 不為空）**：
  - `C_now = Σ(price × shares)`、`P_anchor = min(price)`、`m = type 為 "grid" 的筆數`。

### 3.4 已成交持股明細與停利子母單

- **`type = "base"`（底倉不掛停利單）**：
  - `tp = null`、`tp_trail_pct = null`、`tp_reached = null`、`expected_profit = null`、`proj_base_pool = null`、`retain_shares = 0`、`sell_shares = 0`、`reverse_buy = null`。
- **`type = "grid"`（依 `TP` 由低到高遞進累計底倉獲利池）**：
  - 內部先對所有 `grid` 持股計算 `TP = round_price(price × (1 + z))`，並依 `(TP, 原輸入索引)` 升冪排序逐層試算（低價網格先賣出、獲利依序進入底倉獲利池；API 回傳的 `holdings` 列表仍**保留原輸入順序**）。
  - 初始 `running_pool = base_profit_pool`，逐筆計算：
    1. `tp_trail_pct = round_ratio(y)`、`tp_reached = (current_price ≥ TP)`（未提供 `current_price` 時為 `null`）。
    2. 保守估算賣價（期望中值）：`TP_est = TP × (1 − 0.5y)`（保留全精度）。
    3. 預估獲利：`ΔΠ_lot = Q × (TP_est − price)`；可用底倉池：`Pool_avail = running_pool + ΔΠ_lot × P0`。
    4. 留股與賣股：`retain_shares = min(Q, max(0, ⌊Pool_avail / TP_est⌋))`（`TP_est > 0` 時）、`sell_shares = Q − retain_shares`。
    5. 留股後結餘池：`running_pool = Pool_avail − retain_shares × TP_est`（傳遞給下一筆較高 `TP` 的 `grid` lot）。
    6. API 輸出：`expected_profit = round_price(ΔΠ_lot)`、`proj_base_pool = round_price(running_pool)`（**留股後結餘池**）。
  - 反向回補買入子單 `reverse_buy`：
    - `buy_trigger_price = round_price(TP × (1 − x))`
    - `buy_trail_pct = round_ratio(y)`
    - `buy_max_price = round_price(buy_trigger_price × (1 + y))`
    - `shares = sell_shares`

### 3.5 邊界條件與未來加碼網格（`j = 1…N_rem`）

- `N_rem = N − m`，依序檢查以下條件並加入警示：
  1. `C_now ≤ 0` → `NO_POSITION`
  2. `C_now ≥ B_eff` → `BUDGET_EXHAUSTED`
  3. `N_rem ≤ 0` → `GRID_FULL`
- 任一警示成立時，`future_grid` 回傳 `[]`；否則依序產生 `j = 1…N_rem` 層：
  1. `r_new = (B_eff / C_now)^(1 / N_rem) − 1`
  2. `P_j = round_price(P_anchor × (1 − x)^j)`（後續計算一律採用捨入後的 `P_j`）
  3. `buy_trail_pct = round_ratio(y)`、`P_j_max = round_price(P_j × (1 + y))`
  4. `C_theo(j) = C_now × (1 + r_new)^j`；最後一層（`j = N_rem`）直接設為 `B_eff`
  5. `Budget_j = C_theo(j) − (C_now + Σ_{k<j} E_k)`，其中 `E_k = Q_k × P_k × (1 + 0.5y)`
  6. `Q_j = max(0, ⌊Budget_j / (P_j × (1 + y))⌋)`（`Q_j = 0` 的層照常輸出）
  7. `cum_invest = round_price(C_now + Σ_{k≤j} E_k)`
  8. `TP_j = round_price(P_j × (1 + z))`、`breached = (current_price ≤ P_j)`（未提供 `current_price` 時為 `null`）
  9. `reverse_sell`（**各層維持以當下 `base_profit_pool` 獨立試算，不跨層累計**）：
     - `sell_trigger_price = TP_j`、`sell_trail_pct = round_ratio(y)`
     - 保守估算賣價：`TP_est_j = TP_j × (1 − 0.5y)`
     - `ΔΠ_j = Q_j × (TP_est_j − P_j)`、`Pool_avail_j = base_profit_pool + ΔΠ_j × P0`
     - `retain_shares = min(Q_j, max(0, ⌊Pool_avail_j / TP_est_j⌋))`、`sell_shares = Q_j − retain_shares`
     - API 輸出：`expected_profit = round_price(ΔΠ_j)`、`proj_base_pool = round_price(Pool_avail_j − retain_shares × TP_est_j)`（**留股後結餘池**）

### 3.6 停利結算運算（`compute_settlement`）

對已成交的 `grid` lot 以實際出場價 `exit_price` 結算（非 `grid` lot 或 `exit_price ≤ lot.price` 回 `422`）：
1. `ΔΠ = Q × (exit_price − lot.price)`、`Pool_avail = base_profit_pool + ΔΠ × P0`。
2. `retain_shares` 若未提供，自動取 `min(Q, max(0, ⌊Pool_avail / exit_price⌋))`；若手動提供，須滿足整數 `0 ≤ retain_shares ≤ Q` 且 `retain_shares × exit_price ≤ Pool_avail`，否則回 `422`。
3. `sell_shares = Q − retain_shares`。
4. `new_realized_profit = round_price(realized_profit + ΔΠ)`。
5. `new_base_profit_pool = round_price(Pool_avail − retain_shares × exit_price)`。
6. 若 `retain_shares > 0`：已有 `base` lot 時以 `exit_price` 併入並更新為加權平均價 `round_price((Q_base × P_base + retain_shares × exit_price) / (Q_base + retain_shares))`；無 `base` lot 時新增一筆 `type = "base"`、`shares = retain_shares`、`price = round_price(exit_price)`。

---

## 4. FastAPI 路由總覽

| Method | Path | 說明 |
| --- | --- | --- |
| `GET` | `/health` | 健康檢查，回傳 `{"status": "ok"}` |
| `GET` | `/api/v1/market/{symbol}?force_refresh=false` | 取得最新已收盤交易日、收盤價、`atr_14_pct`、`atr_50_pct`、`cache_hit`、`warnings` |
| `POST` | `/api/v1/calculator/compute` | 無狀態試算（不讀寫檔案），回傳 `params_summary`、`dashboard`、`holdings`、`future_grid` |
| `GET` | `/api/v1/holdings` | 列出所有已儲存股票代號（依字母排序） |
| `GET` | `/api/v1/holdings/{symbol}` | 取得單一代號的策略參數、ATR 設定與持股列表 |
| `PUT` | `/api/v1/holdings/{symbol}` | 建立或更新策略參數（`realized_profit`、`base_profit_pool`、配對的 `atr_14_pct`/`atr_50_pct`、`atr_source`、`atr_date` 更新時省略則保留既有值；無任何 lot 時依 `Q0` 自動建立 `base` lot，已有 lot 時不異動既有 lot） |
| `DELETE` | `/api/v1/holdings/{symbol}` | 刪除該代號所有設定與持股 |
| `POST` | `/api/v1/holdings/{symbol}/lots` | 新增單筆持股（已有 `base` lot 再新增回 `409 BASE_LOT_EXISTS`） |
| `PUT` | `/api/v1/holdings/{symbol}/lots/{lot_id}` | 修改單筆持股（改為 `base` 且已有其他 `base` lot 回 `409 BASE_LOT_EXISTS`） |
| `DELETE` | `/api/v1/holdings/{symbol}/lots/{lot_id}` | 刪除單筆持股 |
| `POST` | `/api/v1/holdings/{symbol}/lots/{lot_id}/settle` | 執行 `grid` lot 停利結算、更新已實現獲利與底倉獲利池、併入留股並刪除已結算 lot |

---

## 5. 測試與品質門檻（CI Quality Gates）

- **套件管理**：`backend/` 使用 `uv` + `pyproject.toml` + `uv.lock`（鎖定 Python 3.12）。
- **自動化檢查（與 GitHub Actions CI 一致）**：
  - `uv run ruff check app tests`
  - `uv run ruff format --check app tests`
  - `uv run mypy app tests`
  - `uv run pytest --cov=app -v`（全部 mock、不連網，branch coverage 門檻 `≥ 85%`）
  - `uv run pip-audit --strict`
- **測試範圍**：涵蓋黃金案例（`GC-01～04`、`GC-05A/B/C/G`、`GC-06`）、`API_Guards`（`GC-05D～N`）、Wilder ATR（`ATR_A_Basic`、`ATR_B_60bars`）、XNYS 日曆（`CAL-01～08`）、行情快取／過期資料行為、Holdings CRUD 與結算、追蹤緩衝 `y` 捨入及累計底倉獲利池規則。

---

## 6. 設計決策與變更紀錄（Design Decisions）

- **2026-11-23（PR #7）追蹤緩衝 `y` 限制至百分比小數第 2 位**：
  - **背景**：券商追蹤停損／買入掛單僅能輸入至百分比小數點後兩位（如 `0.85%`）。
  - **決定**：計算 `y = b × atr_14_pct` 後立即以 `ROUND_HALF_EVEN` 量化至 `0.0001`（`round_trail_pct`），後續所有公式均採用此值，API 仍維持 6 位小數字串格式以相容其他比例欄位。
- **2026-11-23（PR #8）已成交網格由低到高遞進累計底倉獲利池與保守賣價估算**：
  - **背景**：開盤前一次預掛多筆已成交網格停利單時，各層獨立試算會在獲利池接近 1 股時重複預支同一筆池金（超留），或遺漏連續停利累積出的留股；且追蹤停利回檔可能使實際賣價略低於觸發價 `TP`。
  - **決定**：
    1. 停利估算賣價改採保守期望中值 `TP × (1 − 0.5y)`（對稱於買入端 `P_k × (1 + 0.5y)`）。
    2. 已成交 `grid` 持股依 `TP` 由低到高遞進累計底倉獲利池，每層留股後立即扣除 `retain_shares × TP_est` 再傳給下一層。
    3. `future_grid` 的 `reverse_sell` 維持以當下 `base_profit_pool` 獨立試算（因開盤前無法預知當日回檔深度）。
    4. `proj_base_pool` 統一輸出「留股後結餘池」。
