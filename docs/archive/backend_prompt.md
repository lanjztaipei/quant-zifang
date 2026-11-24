> [!NOTE]
> **歷史紀錄（唯讀）**：此檔案為專案建立時的原始初始規格 prompt，僅作開發起點紀錄，不再更新。現行後端規格請見 [docs/backend-spec.md](../docs/backend-spec.md)。

# Quant Zifang（張良）後端規格（首個策略模組：波動率自適應網格 VAG Grid）

> *The strategist in the command tent. A modular decision-support system for daily order planning. (For fully automated execution, see `quant-hanxin`)*
> **專案定位**：`quant-zifang`（張良）為每日開盤前一次頻率的「交易掛單決策支援系統」，與負責盤中秒級全自動實時交易的姊妹專案 `quant-hanxin`（韓信 — *The general on the battlefield. A fully automated trading engine for split-second execution. (For manual decision support, see `quant-zifang`)*）相互呼應。

請在 `backend/` 建立 `quant-zifang` 的 core 模組與 FastAPI 服務：策略核心是純函式，不依賴 FastAPI、yfinance 或檔案 I/O；行情來源、持久化與「現在時間」透過介面注入。

## 1. 全域規則
- **百分比**一律以小數表示。
- **數值**：所有計算用 `Decimal`（全域 `getcontext().prec = 40`；將外部浮點數如 yfinance K 棒轉為 `Decimal` 時一律先轉字串 `Decimal(str(val))`），不用 float。
- **捨入**：一律用銀行家捨入（`ROUND_HALF_EVEN`），只在公式標示 `round` 的地方與 API 輸出時捨入，中間計算保留全精度。
  - 價格與金額取到小數第 2 位
  - 比例取到小數第 6 位
- **股數**：一律向下取整。所有 floor（含 ⌊K/a⌋、Q0、Q_j、q_retain）都先用 ROUND_HALF_EVEN 量化到小數第 10 位再取整。
- **API 數值格式**：Decimal 一律以字串輸出。
- **錯誤格式**：HTTP 錯誤一律回 `{code, message}`，對應如下：
  - 422：`VALIDATION_ERROR`
  - 404：`NOT_FOUND`
  - 409：`BASE_LOT_EXISTS`
- **警示格式**：策略警示放在 `warnings: [{code, message}]`，訊息用繁體中文；同時符合多個條件時全部回傳，順序為 `NO_POSITION`、`BUDGET_EXHAUSTED`、`GRID_FULL`。
- **JSON 寫檔**：資料目錄預設 `data/`（可透過設定或環境變數覆寫）；寫檔一律用 `filelock` 加鎖並原子寫入。
- **CORS**：開啟，允許的來源由環境變數設定，預設 localhost。

## 2. DataProvider：行情與 ATR
1. **最新已收盤交易日（純函式 `get_latest_closed_session(now)`）**：使用 exchange_calendars（XNYS）交易日曆，以美東時間（`America/New_York`）判斷；現在時間 ≥ 該交易日收盤時間（含提前收盤日，如感恩節隔天 13:00 ET 收盤）+ 15 分鐘，該交易日才算已收盤，否則往前取上一個已收盤交易日。
2. **快取**：`data/atr_cache.json`，鍵為 `SYMBOL_YYYY-MM-DD`（代號轉大寫），值包含交易日、收盤價（2 位小數）、`atr_14_pct`（6 位小數）、`atr_50_pct`（6 位小數）、抓取時間。命中就直接回傳；`force_refresh=true` 時略過快取。
3. **抓取**：
   - 用 yfinance 的 `download()` 或 `Ticker().history()` 抓近 **2 年**日線，使用 `auto_adjust=True`，禁止使用 `.info`。
   - **剔除未收盤 K 棒（純函式 `filter_closed_bars(bars, latest_session)`）**：只保留日期 ≤ 最新已收盤交易日的 K 棒（剔除盤中 K 棒）。
   - 最後一根 K 棒不是預期的交易日（資料延遲或停牌）→ 照樣回傳，附上實際資料日期與 `STALE_MARKET_DATA` 警示，但不寫入快取。
   - 查無代號資料 → 404；DataProvider 過濾後 K 棒少於 51 根 → 422。
4. **ATR（Wilder 原始定義，純函式 `compute_wilder_atr(bars, n)`）**：
   - 接收已過濾的 K 棒（至少 `n + 1` 根），計算 `n` 期 Wilder ATR 與 ATR%。
   - TR = max(H−L, |H−前收|, |L−前收|)（第 1 根無前收，TR 從第 2 根開始共 `len(bars) − 1` 個）。
   - 首值（第 `n + 1` 根 K 棒）= 前 `n` 個 TR 的簡單平均；之後 ATR_t = (ATR_{t−1}×(n−1) + TR_t) / n，n = 14 與 50。
   - ATR% = 最新 ATR / 最新收盤價（API 輸出與快取儲存皆用 `ROUND_HALF_EVEN` 取到小數第 6 位）。

## 3. StrategyEngine：純函式
**輸入**：`symbol`、`B`、`initial_price`、`P0`（預設 0.30）、`a`（預設 0.6）、`b`（預設 0.1）、`c`（預設 0.5）、`K`（預設 6）、`realized_profit`（預設 0）、`base_profit_pool`（預設 0）、`atr_14_pct`、`atr_50_pct`（抓取值或手動覆蓋值）、`holdings`、`current_price`（選填）。
`initial_price` 與 P0 一律必填；在實戰模式下，`initial_price` 不參與網格計算，P0 作為網格獲利滾入底倉的分配比例。

**輸入驗證**（不通過 → 422）：
- `symbol` 轉大寫後須符合 `^[A-Z0-9.\-]{1,10}$`
- B > 0、`initial_price` > 0、0 < P0 ≤ 1
- a > 0、b ≥ 0、c > 0、K > 0
- `realized_profit` ≥ 0、`base_profit_pool` ≥ 0
- 0 < ATR% < 1、x < 1、⌊K/a⌋ ≤ 100
- `current_price` 若有提供必須 > 0
- lot：`type` 只能是 `base`（最多 1 筆）或 `grid`；`price` > 0；`shares` 為 ≥ 1 的整數

**參數**
- B_eff = B + realized_profit
- ATR_eff = max(atr_50_pct, atr_14_pct)
- x = a × ATR_eff，y = b × atr_14_pct，z = c × atr_14_pct
- N = max(1, ⌊K/a⌋)

**模式與錨點**
- **新建倉**（holdings 為空）：
  - Q0 = ⌊B_eff × P0 / initial_price⌋，C_now = Q0 × initial_price，P_anchor = initial_price（Q0 = 0 時為 null），m = 0。
  - Q0 > 0 時，持股明細回傳一列建議底倉（`type=base`、`id=null`、`price=initial_price`、`shares=Q0`）；Q0 = 0 時持股明細為 []。
- **實戰**（holdings 不為空）：C_now = Σ(price × shares)，P_anchor = min(price)，m = type 為 grid 的筆數。

**持股 lot 與賣出子母單**：每筆包含 `id`（在 Holdings 持久化 API 由後端以 uuid 產生；在無狀態 `/calculator/compute` 輸入中為選填字串，若有提供則原樣回傳，未提供或新建倉建議底倉則為 `null`）、`type`、`price`（實際成交價）、`shares`（記為 Q）、`filled_at`（選填字串）、`note`（選填字串），並依下列規則計算停利母單、少賣留股數與反向回補買入子單：
- `type = base`（底倉不掛停利單）：
  - `tp = null`、`tp_trail_pct = null`、`tp_reached = null`、`expected_profit = null`、`proj_base_pool = null`、`retain_shares = 0`、`sell_shares = 0`、`reverse_buy = null`。
- `type = grid`：
  - TP = round(price × (1+z))，`tp_trail_pct` = y，`tp_reached` = (current_price ≥ TP，未提供 current_price 時為 null)。
  - ΔΠ_lot = Q × (TP − price)，Pool_proj = base_profit_pool + ΔΠ_lot × P0（API 輸出 `expected_profit` = round(ΔΠ_lot)、`proj_base_pool` = round(Pool_proj)）。
  - `retain_shares` (q_retain) = min(Q, max(0, ⌊Pool_proj / TP⌋))
  - `sell_shares` (Q_sell) = Q − q_retain
  - `reverse_buy`：
    - `buy_trigger_price` = round(TP × (1−x))
    - `buy_trail_pct` = y
    - `buy_max_price` = round(buy_trigger_price × (1+y))
    - `shares` = Q_sell

**邊界**：N_rem = N − m。依下列條件各自加入對應警示：
- C_now ≤ 0 → `NO_POSITION`
- C_now ≥ B_eff → `BUDGET_EXHAUSTED`
- N_rem ≤ 0 → `GRID_FULL`

只要有任何一個成立，未來網格就回傳 []。

**未來第 j = 1…N_rem 層（開盤前靜態批次買入母單 + 反向停利子單）**
1. r_new = (B_eff / C_now)^(1/N_rem) − 1
2. P_j = round(P_anchor × (1−x)^j)；後續所有用到 P_j 的計算都用捨入後的值
3. `buy_trail_pct` = y，P_j_max = round(P_j × (1+y))
4. C_theo(j) = C_now × (1+r_new)^j；最後一層（j = N_rem）直接設為 B_eff
5. Budget_j = C_theo(j) − (C_now + Σ_{k<j} E_k)，其中 E_k = Q_k × P_k × (1 + 0.5y)
6. Q_j = max(0, ⌊Budget_j / (P_j × (1+y))⌋)；Q_j = 0 的層照樣輸出
7. 累計投入額 `cum_invest` = round(C_now + Σ_{k≤j} E_k)
8. TP_j = round(P_j × (1+z))
9. `reverse_sell`：
   - `sell_trigger_price` = TP_j，`sell_trail_pct` = y
   - ΔΠ_j = Q_j × (TP_j − P_j)，Pool_proj_j = base_profit_pool + ΔΠ_j × P0（API 輸出 `expected_profit` = round(ΔΠ_j)、`proj_base_pool` = round(Pool_proj_j)）
   - `retain_shares` (q_retain_j) = min(Q_j, max(0, ⌊Pool_proj_j / TP_j⌋))
   - `sell_shares` (Q_sell_j) = Q_j − q_retain_j

## 4. FastAPI 路由（前綴 `/api/v1`）
1. `GET /market/{symbol}?force_refresh=false` → 最新已收盤交易日、收盤價、`atr_14_pct`、`atr_50_pct`、`cache_hit`、`warnings`。
2. `POST /calculator/compute`：無狀態（不讀寫檔案）。回傳：
   - **策略參數摘要**：`atr_eff_pct`、x、y、z、N、N_rem、最大安全跌幅 1−(1−x)^N。
   - **儀表板**：
     - 總股數（分列底倉股數與網格股數）、平均成本（無持股時為 null）
     - B、`realized_profit`、B_eff、`base_profit_pool`
     - C_now、剩餘現金 B_eff − C_now、資金使用率 C_now / B_eff
     - 剩餘防線跌幅 1−(1−x)^N_rem（N_rem ≤ 0 時為 0）、warnings
   - **已成交持股明細**：各筆持股加上 `tp`、`tp_trail_pct`、`tp_reached`、`expected_profit`、`proj_base_pool`、`retain_shares`、`sell_shares`、`reverse_buy`。
   - **未來網格表**：j、P_j、`buy_trail_pct`、P_j_max、Q_j、`cum_invest`、TP_j、`breached`（有提供 `current_price` 時為 current_price ≤ P_j，沒提供時為 null）、`reverse_sell`。
3. **Holdings**：持久化於 `data/holdings.json`。每個代號存一份資料，內容為策略參數（含 `realized_profit`、`base_profit_pool`）、ATR 值與其來源（`fetched` 或 `manual`，選填）及資料日期（選填）、lots。
   - `GET /holdings`：列出所有已儲存的代號
   - `GET /holdings/{symbol}`：取得該代號的參數與所有持股
   - `PUT /holdings/{symbol}`：建立或更新該代號的策略參數（參數驗證規則與 `/calculator/compute` 相同；`realized_profit` 與 `base_profit_pool` 選填，新建時預設 0，更新時未提供則保留既有值；`atr_14_pct` 與 `atr_50_pct` 選填，須同時提供或同時省略，更新時未提供則保留既有值；若當下有 ATR 值則一併驗證 `0 < ATR% < 1` 與 `x < 1`；`atr_source` 與 `atr_date` 為選填欄位）
     - 當下沒有任何 lot（包含全部刪光後）時，依 Q0 自動建立 base lot（price = initial_price；Q0 = 0 就不建立）
     - 已經有 lot 時，修改參數不會動到既有 lot
   - `DELETE /holdings/{symbol}`：刪除該代號的所有設定與持股
   - `POST /holdings/{symbol}/lots`：新增單筆持股，回傳新的 id 與更新後的完整資料；每個代號最多一筆 base lot，否則回 409
   - `PUT /holdings/{symbol}/lots/{lot_id}`：修改單筆持股（若改為 base 且已有其他 base lot 同樣回 409）
   - `DELETE /holdings/{symbol}/lots/{lot_id}`：刪除單筆持股
   - `POST /holdings/{symbol}/lots/{lot_id}/settle`：結算停利出場的 `grid` lot（若目標非 `grid` 則回 422）。
     - 輸入：`exit_price`（必須 > lot.price，否則回 422）、`retain_shares`（選填整數；未提供時自動取 min(Q, ⌊(base_profit_pool + ΔΠ × P0) / exit_price⌋)；若有提供則須滿足 0 ≤ retain_shares ≤ Q 且 retain_shares × exit_price ≤ base_profit_pool + ΔΠ × P0，否則回 422）。
     - 處理：
       1. ΔΠ = Q × (exit_price − lot.price)
       2. `realized_profit` = round(realized_profit + ΔΠ)
       3. `base_profit_pool` = round(base_profit_pool + ΔΠ × P0 − retain_shares × exit_price)
       4. 若 `retain_shares` > 0：已有 `base` lot 時將 `retain_shares` 股以 `exit_price` 併入並更新為加權平均價 `round((Q_base × P_base + retain_shares × exit_price) / (Q_base + retain_shares))`；無 `base` lot 時新增一筆 `type=base`、`shares=retain_shares`、`price=round(exit_price)`。
       5. 刪除該筆已結算的 `grid` lot，回傳結算摘要與更新後的完整資料。

## 5. 測試（pytest，全部 mock，不連網）
黃金案例在 `test_cases/Quant_Zifang_Golden_Cases.xlsx`，黃底欄是獨立驗算的預期值。測試要把這些數值直接寫進程式（測試不讀 xlsx），而且必須**完全相符**：
- 涵蓋 `GC-01～04`、`GC-05A/B/C/G`、`GC-06`、`API_Guards`、`ATR_A_Basic`、`ATR_B_60bars`、`XNYS_Calendar` 各分頁所有案例。
- 快取命中、未命中後寫入、資料落後時不寫入；holdings CRUD 與 settle 用 `tmp_path` 加 TestClient 測試。

## 完成條件
`pytest` 全部通過；`uvicorn` 能啟動；README 附上 Windows PowerShell 的安裝、啟動、測試指令。
