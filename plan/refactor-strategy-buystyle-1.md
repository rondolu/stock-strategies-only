---
goal: 將單一 BUY 模型重構為保守型BUY / 積極型BUY 雙風格分類架構，並同步修正所有舊敘述與輸出模型
version: "1.0"
date_created: 2026-06-03
last_updated: 2026-06-03
owner: kevin801221
status: 'Planned'
tags: [refactor, strategy, buy-style, telegram, evaluate, notify]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

本次重構的核心目標，是將 stock-strategies-only 目前以**單一 BUY + 綜合分主導**的舊模型，重構為以「這檔股票此時是否適合開始布局」為核心問句的新架構。BUY action 保留不動以維持相容性，但在 BUY 之下新增 `buy_style` 欄位，以 `conservative` / `aggressive` 區分風格，並在 Telegram 上對外顯示「保守型BUY」與「積極型BUY」。

所有舊描述（30/30/40 權重、3 年回測、20 日持有、EPS > 5、技術分 0-100）也一併在本次同步修正，確保 README、通知訊息、回測說明與實際邏輯完全一致。

---

## 1. Requirements & Constraints

### 核心需求

- **REQ-001**: 只使用 repo 目前已存在的資料與指標，不新增任何新財務資料來源、估值欄位或外部依賴。
- **REQ-002**: `action` 保留 BUY / WATCH / SKIP，以維持既有輸出與下游相容性。
- **REQ-003**: 新增 `buy_style` 欄位（值為 `conservative` / `aggressive` / `null`），僅 BUY 才有非 null 值。
- **REQ-004**: Telegram 顯示名稱必須使用「保守型BUY」與「積極型BUY」，不顯示英文原始值。
- **REQ-005**: `signal_score` 降為排序分，不作為主決策依據。
- **REQ-006**: 趨勢（chg_20d、above_ma20、above_ma60）、位置（pct_from_high）、量價（vol_ratio）、回測品質（backtest_winrate、avg_return）必須成為分類主條件。
- **REQ-007**: 基本面（fund_pass）保留為資格條件，不主導買點判斷。
- **REQ-008**: 突破布林上軌（bb_upper）從不可買限制降為風險註記。
- **REQ-009**: `avg_return`（backtest.py 已有）必須納入次級條件或排序條件評估。
- **REQ-010**: Telegram 訊息中必須附上固定摘要說明，讓接收者理解兩種 BUY 的差異、入選原因與主要風險。
- **REQ-011**: Telegram 訊息架構可超過三則，但每則必須維持高可讀性。
- **REQ-012**: Signals 工作表可調整欄位排列以提升可讀性。

### 安全與品質限制

- **SEC-001**: 所有 Telegram 輸出應確保不洩露原始 API token 或系統路徑。
- **CON-001**: 不可在 Telegram 訊息中塞入全部欄位細節，應維持「最小必要資訊」原則。
- **CON-002**: 新增欄位不可破壞 main.py 現有 `order = {"BUY": 0, "WATCH": 1, "SKIP": 2, "ERROR": 3}` 排序邏輯。
- **CON-003**: sheet.py 的 append_signals 在欄位調整後仍需維持冪等性（重複執行不會產生壞資料）。

### 已確認的舊描述錯誤（必須修正）

- **BUG-001**: README 寫「基本面30% + 技術30% + 回測40%」，但實際 evaluate.py 是 20% + 50% + 30%。
- **BUG-002**: README 與 config 範例寫「EPS > 5」，但實際 config 是 eps_threshold = 2.0。
- **BUG-003**: README 寫「3 年歷史回測」，但 config 實際是 backtest_years = 2。
- **BUG-004**: README 寫「持有 20 個交易日」，但 config 實際是 hold_days = 10。
- **BUG-005**: indicators.py 的 tech_score_at 函式文件寫「0-100」，但最高實際可達 120（4×25 + RSI 20）。
- **BUG-006**: notify.py 第一則訊息仍硬寫「基本面(EPS>5,ROE>15) + 技術面 + 3年回測」舊描述。
- **BUG-007**: notify.py 的 _explain_why 仍比對 signal_score < 65 / tech_score < 50 等舊門檻，無法說明新分類語意。
- **BUG-008**: evaluate.py 先決定 action，再計算 chg_5d / chg_20d / vol_ratio / pct_from_high / above_ma20 / above_ma60，導致這些欄位從未參與主決策。

### 設計指引

- **GUD-001**: 保守型BUY 著重趨勢完整性：above_ma20 AND above_ma60，chg_20d > 0，pct_from_high 位置合理（未追高）。
- **GUD-002**: 積極型BUY 著重趨勢轉強：above_ma20 OR 技術訊號出現轉折，vol_ratio 上升，但位置或均線不一定完整。
- **GUD-003**: WATCH 為「方向不差但條件未全過」的觀察池，不應與 SKIP 混淆。
- **GUD-004**: Telegram 訊息每則應有明確標題與角色，避免接收者需要反推哪一則是什麼。

---

## 2. Implementation Steps

### Implementation Phase 1：舊敘述審計與命名盤點

- **GOAL-001**: 完整列出所有文件與程式碼中仍存在的舊描述，建立「舊描述對照表」，作為後續所有修正的依據基準，確保沒有漏網之魚。

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-001 | 審計 README.md：找出所有含「30/30/40」、「EPS > 5」、「3 年」、「20 個交易日」、「0-100」的行號，記錄位置與舊文字 | | |
| TASK-002 | 審計 notify.py：找出 format_messages 第一則訊息中硬寫的策略規則說明（`msg1.append("📋 *策略規則*")` 區段），記錄全文 | | |
| TASK-003 | 審計 notify.py：找出 _explain_why 函式中所有依賴 signal_score / tech_score 舊門檻的判斷邏輯，記錄每一個 if 條件 | | |
| TASK-004 | 審計 indicators.py：確認 tech_score_at 函式說明文字（目前寫 `0-100`），記錄實際最大值（4×25 + RSI 20 = 120） | | |
| TASK-005 | 審計 config.py：確認目前所有實際值（eps_threshold=2.0, roe=15, years=2, hold=10, target=0.10, stop=0.08, min_tech=60, min_total=65）與 README 不一致之處逐條對應 | | |
| TASK-006 | 審計 evaluate.py：確認 action 決定（第 46-55 行）發生在 chg_5d/chg_20d/vol_ratio/pct_from_high/above_ma20/above_ma60 計算（第 59-71 行）之前，記錄行號與影響範圍 | | |
| TASK-007 | 審計 sheet.py：記錄 Signals 分頁現有 14 個欄位的名稱與順序，確認哪些欄位在本次重構後需要新增或搬移 | | |
| TASK-008 | 審計 backtest.py：確認 avg_return 回傳位置（dict key `avg_return`）與目前在 evaluate.py 的引用方式（未進入主決策），記錄確切程式碼位置 | | |

---

### Implementation Phase 2：資料模型與輸出 dict 重構設計確認

- **GOAL-002**: 確定 evaluate() 輸出 dict 的新結構，包含哪些欄位屬於主決策依據、哪些屬於排序用途、哪些屬於通知展示，以及 buy_style 的加入位置與語意。

#### 2.1 evaluate 輸出 dict 新結構設計

輸出 dict 欄位分為四層：

**層 A — 主決策欄位（決定 action 與 buy_style 的輸入）**

| 欄位 | 舊地位 | 新地位 | 說明 |
|------|--------|--------|------|
| `fund_pass` | 主條件之一 | **資格條件** | BUY 必要前提，未過則不可為 BUY；但不再影響 buy_style 區分 |
| `above_ma20` | 後計算，未進決策 | **BUY 主條件** | 保守型BUY 必要，積極型BUY 彈性判斷 |
| `above_ma60` | 後計算，未進決策 | **BUY 主條件（保守）** | 保守型BUY 必要；積極型BUY 可放寬 |
| `chg_20d` | 後計算，未進決策 | **BUY 主條件** | 20 日漲幅 > 0 為保守型BUY 必要趨勢佐證 |
| `pct_from_high` | 後計算，未進決策 | **BUY 主條件（位置）** | 距 252 日高點 < 25% 為保守型入場條件；> 40% 列風險 |
| `vol_ratio` | 後計算，未進決策 | **BUY 次級條件** | > 1.2 為量能佐證；< 0.8 列風險 |
| `backtest_winrate` | 已進決策（bt_score） | **保留為次級條件** | < 0.5 仍列風險，但不再獨立主導 action |
| `backtest_samples` | 已進風險 | **保留為風險判斷** | < 8 次仍觸發「統計弱」風險 |
| `avg_return` | 有值但未使用 | **新增為排序條件** | avg_return > 0 時作為排序加分；≤ 0 列次要風險 |
| `tech_score` | 主條件之一 | **降為次級條件** | tech_score ≥ 50 仍需要，但不再以單分主導決策 |
| `chg_5d` | 後計算，未進決策 | **排序輔助** | 短線動能參考，不參與主決策 |

**已明確降為風險註記的條件：**
- `bb_upper`：close > bb_upper → 列風險「短線過熱，接近布林上軌」，不阻斷 BUY
- `rsi > 70`：列風險「RSI 過熱區」
- `k > 80`：列風險「KD 高檔，注意回落」
- `winrate < 0.5`：列風險「歷史勝率低於五成」
- `avg_return ≤ 0`：列風險「回測平均報酬為負」
- `pct_from_high < -40%`：列風險「距高點逾 40%，確認非下跌途中」
- `vol_ratio < 0.8`：列風險「量能萎縮」

**層 B — 新增欄位**

| 新欄位 | 型別 | 說明 |
|--------|------|------|
| `buy_style` | `str \| None` | BUY 時值為 `conservative` 或 `aggressive`；WATCH / SKIP 為 `null` |
| `buy_reason` | `list[str]` | 入選此分類的主要原因，2-4 條，用於 Telegram 顯示 |
| `primary_risk` | `str` | 最重要的一條風險說明，用於 Telegram 每檔個股必要提醒 |
| `sort_score` | `float` | 排序用分數：signal_score 仍作為基底，加上 avg_return 加權，保守型BUY 優先於積極型BUY 排序 |

**層 C — 保留不變的現有欄位（通知展示用）**
- `entry_price`, `stop_loss_price`, `target_price`, `risk_reward_ratio`, `position_size_pct`
- `risk_notes`（擴充，將部分舊「阻斷 BUY」條件改為風險記錄）
- `components`（tech_score, tech_signals, backtest_winrate, backtest_samples, eps_min, roe_min）
- `trend`（chg_5d, chg_20d, vol_ratio, pct_from_high, above_ma20, above_ma60）

**層 D — 降級為排序參考的欄位**
- `signal_score`：保留輸出，但只用於 sort_score 基底，不用於 action 決策
- `fund_score`, `bt_score`：可選擇保留在 `components` 供參考，不應對外展示為主分數

#### 2.2 分類規則層次（完整版）

**保守型BUY（conservative）資格 + 主條件：**

資格條件（全部必須通過，任一不過則降至 WATCH 或 SKIP）：
1. `fund_pass = True`
2. `tech_score ≥ 50`
3. `backtest_samples ≥ 5`（最低統計基礎）

主條件（需全部滿足）：
1. `above_ma20 = True`（站上月線）
2. `above_ma60 = True`（站上季線）
3. `chg_20d > 0`（20 日趨勢向上）
4. `pct_from_high ≥ -25`（距高點不超過 25%，位置合理）

次級條件（滿足越多越優先，但非阻斷）：
1. `vol_ratio ≥ 1.0`（量能平穩或放大）
2. `backtest_winrate ≥ 0.55`
3. `avg_return > 0`
4. `chg_5d > 0`（短線動能正向）

風險註記（不阻斷 BUY，但必須寫入 risk_notes 且作為 primary_risk 候選）：
- `close > bb_upper` → 「短線過熱，接近布林上軌」
- `rsi > 70` → 「RSI 過熱區，注意短線回落」
- `k > 80` → 「KD 高檔」
- `vol_ratio < 0.8` → 「量能萎縮，動能疑慮」
- `avg_return ≤ 0` → 「歷史回測平均報酬為負，參考價值有限」
- `backtest_samples < 8` → 「回測樣本不足 8 次，統計弱」

**積極型BUY（aggressive）資格 + 主條件：**

資格條件（全部必須通過）：
1. `fund_pass = True`
2. `tech_score ≥ 45`（略寬鬆）
3. `backtest_samples ≥ 3`

主條件（以下任一套路成立）：
- **套路 A — 均線剛突破**：`above_ma20 = True` AND `chg_20d > -5`（20 日未大跌）AND `vol_ratio ≥ 1.2`
- **套路 B — 技術強勢**：`tech_signals` 含「均線多頭」或「KD黃金交叉」或「MACD多頭」任兩項以上 AND `chg_5d > 0`
- **套路 C — 量價突破**：`vol_ratio ≥ 1.5`（量能明顯放大）AND `chg_5d > 2`（短線強勁）

但以下任一條成立時，積極型BUY 不可成立（直接降為 WATCH）：
- `above_ma20 = False` AND `above_ma60 = False`（月線季線雙破，不是轉強而是弱勢）
- `pct_from_high < -50`（距高點超 50%，風險過高）
- `backtest_winrate` 有值且 < 0.35

風險註記（必須寫入，且必有 primary_risk）：
- 固定加入：「積極型BUY 短線波動較大，建議小部位或分批」
- `above_ma60 = False` → 「未站上季線，趨勢尚未完整確立」
- 其他與保守型同樣的過熱 / 量縮 / 勝率低提醒

**WATCH 條件（以下任一）：**
- `fund_pass = True` AND (`above_ma20 = False` OR `chg_20d ≤ 0`) AND `tech_score ≥ 45`（方向未明，位置或趨勢有疑慮）
- `fund_pass = True` AND 技術面尚可（tech_score ≥ 40）AND backtest 樣本不足或勝率偏低（backtest_samples < 5 OR winrate < 0.45）
- `fund_pass = False` AND `tech_score ≥ 50`（技術面尚可但基本面未達格）

**SKIP 條件：**
- `tech_score < 40` AND `fund_pass = False`
- 資料不足（len(px) < 100）
- 積極型不成立 AND 不符合 WATCH 任一條件

**signal_score 的新角色（sort_score 計算依據）：**
- 現有 signal_score 公式（20%基本面 + 50%技術 + 30%回測）保留計算，作為 sort_score 基底。
- sort_score = signal_score + (avg_return > 0 ? avg_return * 100 * 0.1 : 0)
- 保守型BUY 在排序時加 10 分優先於積極型BUY（sort_score += 10），以確保保守型在訊息頂端。
- main.py 排序改為 order + sort_score 雙鍵排序。

#### 2.3 Signals 工作表新欄位設計

新欄位順序（從左到右，分組設計）：

**識別組（A-D）**：date, stock_id, name, action

**買入風格組（E-F）**：buy_style（新增）, buy_reason（新增，逗號分隔）

**評分參考組（G-I）**：signal_score, sort_score（新增）, tech_score

**趨勢位置組（J-N）**：above_ma20, above_ma60, chg_20d, pct_from_high, vol_ratio

**回測品質組（O-Q）**：backtest_winrate, backtest_samples, avg_return（新增）

**風控組（R-U）**：entry_price, stop_loss_price, target_price, rr_ratio

**風險與說明組（V-W）**：primary_risk（新增）, risk_notes

舊的 position_pct, tech_signals 可移至最右側輔助欄。

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-009 | 確認 evaluate() 輸出 dict 新結構設計（A/B/C/D 四層），並確認 buy_style 值為 `conservative` / `aggressive` / `null` | | |
| TASK-010 | 確認分類規則層次設計（保守型 / 積極型 / WATCH / SKIP 四套規則）是否與現有欄位完全對應，無超出 repo 範圍的欄位 | | |
| TASK-011 | 確認 sort_score 計算公式，確認 avg_return 的取用方式與 backtest() 回傳 dict 一致 | | |
| TASK-012 | 確認 Signals 工作表新欄位順序與分組原則，確認不破壞既有 append_rows 機制 | | |

---

### Implementation Phase 3：evaluate.py 主決策重構

- **GOAL-003**: 將 evaluate.py 的計算順序翻轉，使趨勢與位置欄位先計算，再進入主決策；並以新規則層次決定 action 與 buy_style，同時輸出 buy_reason 與 primary_risk。

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-013 | 將 chg_5d / chg_20d / vol_ratio / pct_from_high / above_ma20 / above_ma60 的計算邏輯整體搬移至 signal_score 計算之前，確保這些值在進入分類判斷前已可用 | | |
| TASK-014 | 移除現有 `if signal_score >= 65 and fund_pass and tech_score >= 50` 的單一 BUY 判斷邏輯 | | |
| TASK-015 | 實作資格條件篩選（fund_pass + tech_score + backtest_samples），未通過資格條件者直接進 WATCH / SKIP 分流 | | |
| TASK-016 | 實作保守型BUY 主條件判斷（above_ma20 AND above_ma60 AND chg_20d > 0 AND pct_from_high ≥ -25），通過則 action=BUY, buy_style=conservative | | |
| TASK-017 | 實作積極型BUY 三套套路判斷（套路A / 套路B / 套路C），通過任一套路且無下殺條件，則 action=BUY, buy_style=aggressive | | |
| TASK-018 | 實作 WATCH 條件判斷（基本面通過但趨勢或驗證有疑慮） | | |
| TASK-019 | 實作風險註記邏輯：bb_upper / rsi / k / vol_ratio / avg_return / backtest_samples 各自觸發對應的風險文字，寫入 risk_notes | | |
| TASK-020 | 實作 primary_risk 選取邏輯：從 risk_notes 中選取最嚴重的一條（積極型BUY 固定附上短線波動提醒） | | |
| TASK-021 | 實作 buy_reason 產生邏輯：依 buy_style 從已通過的主條件中生成 2-4 條說明文字（中文），寫入 buy_reason list | | |
| TASK-022 | 實作 sort_score 計算（signal_score 基底 + avg_return 加權 + 保守型加 10 分優先） | | |
| TASK-023 | 更新 evaluate() 回傳 dict：加入 buy_style, buy_reason, primary_risk, sort_score，avg_return 從 bt dict 取出並納入 components | | |

---

### Implementation Phase 4：main.py 排序與流程調整

- **GOAL-004**: 將 main.py 的排序邏輯改為雙鍵（action 優先順序 + sort_score 降序），並確認 format_messages 傳入的 signals list 已具備新欄位。

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-024 | 將排序邏輯從 `(order.get(x.get("action"), 4), -x.get("signal_score", 0))` 改為 `(order.get(x.get("action"), 4), -x.get("sort_score", 0))` | | |
| TASK-025 | 確認 main.py 印出的摘要統計（BUY / WATCH 數量）加上保守型 / 積極型細分計數輸出 | | |
| TASK-026 | 確認 main.py 傳入 append_signals 與 format_messages 的 results list 已含新欄位，無需再在這兩個函式內重算 | | |

---

### Implementation Phase 5：notify.py 分流與訊息重構

- **GOAL-005**: 將 format_messages 拆為五則訊息（市場總覽 → 策略說明 → 保守型BUY → 積極型BUY → WATCH與摘要），並改造 _explain_why 為 _explain_buy_style 以支援新語意。

#### 5.1 新訊息架構設計

**第一則 — 市場總覽（Market Overview）**

內容組成：
- 標題：「📊 每日選股報告 V4.0 日期」
- 掃描統計：總檔數 / 保守型BUY N / 積極型BUY N / WATCH N / SKIP N
- 市場氛圍（_market_sentiment 現有邏輯沿用）
- 池內均漲 / 上漲檔數 / 站上月線檔數
- 類股強弱排名（_sector_summary 現有邏輯沿用）

**第二則 — 策略說明（固定文字，讓接收者理解兩種 BUY 差異）**

內容組成（固定不隨每日資料變動）：
```
📖 今日策略說明

🔵 保守型BUY — 趨勢已完整確立
  站穩月線(MA20)與季線(MA60)，20日方向向上，
  位置合理（未過度追高），適合分批布局。
  風險相對較低，但需留意量能是否持續。

🟠 積極型BUY — 趨勢轉強或接近突破
  月線剛突破或技術訊號出現 + 量能放大，
  可提早切入，但短線波動較大。
  建議小部位進場，嚴守停損。

💡 每檔說明包含：入選主因 + 最主要風險
   兩種 BUY 都已設定停損/停利參考價
```

注意：此則為固定說明文字，每日均附帶，可作為接收者的常設參考。

**第三則 — 保守型BUY 詳細（僅 buy_style = conservative 的股票）**

每股格式：
```
🔵 保守型BUY（N檔）

*股票代號 股票名稱*
入選原因：[buy_reason 逐條列出]
⚠️ 主要風險：[primary_risk]
進場 xxx → 停損 xxx / 目標 xxx（風報比 1:N）
技術分 N | 勝率 N%（N次）| 20日 +N%
```

若無保守型BUY：「🔵 保守型BUY：今日無符合趨勢完整條件的標的」

**第四則 — 積極型BUY 詳細（僅 buy_style = aggressive 的股票）**

每股格式：
```
🟠 積極型BUY（N檔）
⚠️ 提醒：積極型標的短線波動較大，建議小部位或等回測確認

*股票代號 股票名稱*
入選原因：[buy_reason 逐條列出]
⚠️ 主要風險：[primary_risk]
進場 xxx → 停損 xxx / 目標 xxx（風報比 1:N）
技術分 N | 勝率 N%（N次）| 5日 +N%
```

若無積極型BUY：「🟠 積極型BUY：今日無趨勢轉強的標的」

**第五則 — WATCH 與操作建議**

內容組成：
- WATCH 列表（前 6 檔）：股票代號/名稱 + 差在哪裡（改為新的 _explain_watch_gap 語意）
- 超過 6 檔：列出代號與分數的精簡行
- 今日操作建議（_market_sentiment 驅動，現有邏輯沿用）

#### 5.2 _explain_why → _explain_buy_style / _explain_watch_gap 改造

舊版 `_explain_why` 邏輯（依賴 signal_score / tech_score 舊門檻）應改為：

**新 `_explain_buy_style(s)` 函式**（用於 BUY 類的「為何買」）：
- 直接從 `s["buy_reason"]` list 取值，格式化為多行中文說明
- 不再自行計算門檻，因 evaluate.py 重構後 buy_reason 已預先產生

**新 `_explain_watch_gap(s)` 函式**（用於 WATCH 的「差在哪裡」）：
- 依序檢查：fund_pass → above_ma20/ma60 → chg_20d → backtest_samples/winrate
- 以正向語言說明「還缺什麼才能進 BUY」，而不是純粹列缺陷

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-027 | 新增 `_explain_buy_style(s)` 函式，從 `s["buy_reason"]` 取出並格式化為 Telegram 顯示格式 | | |
| TASK-028 | 新增 `_explain_watch_gap(s)` 函式，依序檢查 fund_pass / above_ma20 / above_ma60 / chg_20d / backtest，以「還缺什麼」正向語言說明 | | |
| TASK-029 | 移除舊的 `_explain_why` 函式（或保留但標記為 deprecated，僅在移轉期過渡使用） | | |
| TASK-030 | 改寫 `format_messages` 為五則訊息架構：市場總覽 / 固定策略說明 / 保守型BUY / 積極型BUY / WATCH與建議 | | |
| TASK-031 | 在第三則開頭加入保守型BUY 固定說明文字（趨勢完整定義），在第四則開頭加入積極型BUY 固定警示文字（短線波動提醒） | | |
| TASK-032 | 修正第一則訊息的策略規則說明文字（移除 30/30/40、EPS>5、3年回測、20日持有等舊描述，改為「signal_score 僅供排序，分類以趨勢與位置為主」） | | |
| TASK-033 | 每檔個股格式更新：加入 buy_reason（2-4 條入選原因）與 primary_risk（最主要風險）顯示 | | |
| TASK-034 | 確認每則訊息長度不超過 Telegram 單則訊息 4096 字元限制；若 BUY 過多，加入分批截斷邏輯（BUY 超過 8 檔時自動分兩則傳送） | | |

---

### Implementation Phase 6：sheet.py 欄位擴充

- **GOAL-006**: 更新 Signals 分頁的欄位定義，加入 buy_style / buy_reason / sort_score / avg_return / primary_risk，並調整欄位分組順序以提升可讀性。

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-035 | 更新 `append_signals` 函式中的表頭 list，按照 Phase 2 設計的新欄位分組順序定義新的 header row | | |
| TASK-036 | 更新 `append_signals` 函式中的 rows 資料組裝邏輯，從 signal dict 取出 buy_style / buy_reason / sort_score / primary_risk / avg_return 並填入對應位置 | | |
| TASK-037 | 確認 `append_signals` 在首次建立工作表時（gspread.WorksheetNotFound）使用新 header，舊工作表若已存在則評估是否需要在 README 加入「手動清空 Signals 分頁」的遷移步驟說明 | | |
| TASK-038 | 在 README 的部署說明中加入：「若升級自舊版，建議手動清空 Signals 分頁後重跑，以確保欄位一致」 | | |

---

### Implementation Phase 7：indicators.py 技術分說明校正

- **GOAL-007**: 修正 tech_score_at 函式說明文字，使其反映實際最大分數（120），並加入 RSI 加分的說明。

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-039 | 將 `tech_score_at` 函式的 docstring 從「0-100」改為「0-120（均線/布林/KD/MACD 各 25 分 + RSI 最高 20 分）」 | | |
| TASK-040 | 確認 config 中 `min_tech_score_for_signal = 60` 是基於 120 分制仍合理（60/120 = 50%），若認為應調整，在 config.py 中加入說明註解 | | |

---

### Implementation Phase 8：README 與對外說明全面同步

- **GOAL-008**: 將 README 所有舊描述更新為與實際邏輯一致的版本，並加入新分類架構說明。

| Task     | Description | Completed | Date |
| -------- | ----------- | --------- | ---- |
| TASK-041 | 修正「評分公式」區段：移除「30/30/40」，改為「signal_score = 基本面20% + 技術面50% + 回測30%，**僅用於排序，不決定 BUY/WATCH**」 | | |
| TASK-042 | 修正「基本面篩選」區段：將「近 3 年 EPS > 5」改為「近 2 年 EPS > 2.0 (eps_threshold 可調)、ROE > 15%」 | | |
| TASK-043 | 修正「歷史回測」區段：將「3 年」改為「2 年（config.backtest_years）」，「持有 20 個交易日」改為「持有 10 個交易日（config.hold_days）」 | | |
| TASK-044 | 修正「技術面評分」區段：將「0-100」改為「0-120」，RSI 加分（最高 20 分）說明加入表格 | | |
| TASK-045 | 在「選股策略解析」區段加入新的「BUY 分類說明」小節，說明保守型BUY / 積極型BUY 的判斷依據（月季線站穩 / 趨勢轉強）與適用場景 | | |
| TASK-046 | 修正 README 的「Telegram 通知長這樣」範例區段：更新為新的五則訊息架構範例，顯示保守型BUY / 積極型BUY 分流格式 | | |
| TASK-047 | 修正「自訂策略 → 調整評分權重」範例程式碼：移除舊的 0.3/0.3/0.4 範例，改為說明正確的 0.2/0.5/0.3 現況 | | |
| TASK-048 | 在 README 加入「升級遷移說明」小節：說明 v3 → v4 的主要變更（buy_style 新增、signal_score 語意降級、Signals 欄位新增），以及 Signals 工作表遷移步驟 | | |

---

## 3. Alternatives

- **ALT-001**: 直接將 action 改為 BUY_CONSERVATIVE / BUY_AGGRESSIVE / WATCH / SKIP。評估後不採用，因為 main.py 的排序 order dict、sheet.py 的直接讀取、任何外部依賴 action 值的工具都需要一起改，風險面廣；保留 BUY + 新增 buy_style 欄位的設計可讓所有依賴 `action == "BUY"` 的舊邏輯不變，改動範圍更小且可逆。
- **ALT-002**: 直接廢棄 signal_score。評估後不採用，因為 signal_score 目前仍是唯一現成的多維合成分數，完全廢棄後排序需要另設計 sort_score 且沒有歷史可比對；保留作為排序基底，只是語意降級，維護成本較低。
- **ALT-003**: 將保守型BUY 與積極型BUY 分拆到不同 Telegram chat_id 傳送。評估後不採用，因為需要多組 env 設定，且接收者分群管理複雜；同一 chat 內分開訊息已能達到分流效果，且格式差異夠明顯（顏色 emoji + 固定說明文字）。
- **ALT-004**: 用 config.py 集中管理所有分類門檻（如 ma_required、min_winrate 等）。可作為 Phase 8 後的優化選項，但本次重構不強制，避免過度設計。

---

## 4. Dependencies

- **DEP-001**: Phase 3（evaluate.py 重構）完成後，Phase 4（main.py）、Phase 5（notify.py）、Phase 6（sheet.py）才可實作，因為後三者都依賴 evaluate() 輸出的新欄位。
- **DEP-002**: Phase 2（資料模型設計確認）需在 Phase 3 之前完成，作為 evaluate 實作的設計依據。
- **DEP-003**: Phase 1（審計）需在 Phase 2 之前完成，以確保設計不遺漏任何舊邏輯衝突。
- **DEP-004**: Phase 7（indicators.py 校正）與 Phase 8（README）可在 Phase 3 完成後並行進行，彼此無依賴。
- **DEP-005**: Phase 5 的 _format_stock_detail 改造依賴 evaluate() 輸出中 buy_reason / primary_risk / buy_style 三個新欄位已存在。

---

## 5. Files

- **FILE-001**: [stock_strategies/evaluate.py](stock_strategies/evaluate.py) — 主決策邏輯大改，趨勢欄位前移，新增分類規則與輸出欄位
- **FILE-002**: [stock_strategies/notify.py](stock_strategies/notify.py) — 訊息架構從三則改為五則，新增 _explain_buy_style / _explain_watch_gap，移除舊 _explain_why
- **FILE-003**: [stock_strategies/sheet.py](stock_strategies/sheet.py) — Signals 欄位擴充與重排序
- **FILE-004**: [main.py](main.py) — 排序邏輯改為 sort_score，印出摘要加入 buy_style 細分
- **FILE-005**: [stock_strategies/indicators.py](stock_strategies/indicators.py) — tech_score_at docstring 校正
- **FILE-006**: [stock_strategies/config.py](stock_strategies/config.py) — 加入 buy_style 門檻說明註解（不新增 key，只補文字說明）
- **FILE-007**: [README.md](README.md) — 全面同步，移除六處舊描述，加入新分類說明與遷移指引

---

## 6. Testing

- **TEST-001**: evaluate 案例型驗證 — 保守型BUY
  - 輸入條件：fund_pass=True, tech_score=65, above_ma20=True, above_ma60=True, chg_20d=+3.5, pct_from_high=-12, vol_ratio=1.1, backtest_winrate=0.6, backtest_samples=12
  - 預期輸出：action=BUY, buy_style=conservative, buy_reason 含「站穩月線季線」「20日趨勢向上」，risk_notes 無阻斷性錯誤

- **TEST-002**: evaluate 案例型驗證 — 積極型BUY（套路A）
  - 輸入條件：fund_pass=True, tech_score=55, above_ma20=True, above_ma60=False, chg_20d=-1, vol_ratio=1.3, chg_5d=+2, backtest_winrate=0.52, backtest_samples=8
  - 預期輸出：action=BUY, buy_style=aggressive, primary_risk 含「未站上季線」，buy_reason 含「月線突破」「量能放大」

- **TEST-003**: evaluate 案例型驗證 — WATCH
  - 輸入條件：fund_pass=True, tech_score=50, above_ma20=False, above_ma60=False, chg_20d=-2, backtest_winrate=0.55, backtest_samples=10
  - 預期輸出：action=WATCH, buy_style=null

- **TEST-004**: evaluate 案例型驗證 — SKIP
  - 輸入條件：fund_pass=False, tech_score=35, above_ma20=False, vol_ratio=0.7
  - 預期輸出：action=SKIP, buy_style=null

- **TEST-005**: Telegram 訊息可讀性驗證
  - 方法：使用 TEST-001 至 TEST-004 的輸入，模擬 format_messages 輸出，逐則確認：
    1. 第二則固定策略說明是否包含「保守型BUY」與「積極型BUY」差異說明
    2. 第三則是否只出現 buy_style=conservative 的股票
    3. 第四則是否只出現 buy_style=aggressive 的股票，且含固定短線波動警示
    4. 每檔個股是否顯示 buy_reason（至少 1 條）與 primary_risk（至少 1 條）

- **TEST-006**: 相容性檢查
  - 驗證項目 1：main.py 的 `order = {"BUY": 0, "WATCH": 1, "SKIP": 2, "ERROR": 3}` 排序仍正常，保守型BUY 與積極型BUY 在 order 層都等於 0（均為 BUY）
  - 驗證項目 2：sheet.py 的 append_signals 在 buy_style=null（WATCH 股票）時，欄位寫入 empty string 而非引發 KeyError
  - 驗證項目 3：任何直接讀取 `s.get("action") == "BUY"` 的程式路徑仍正常運作

- **TEST-007**: Signals 工作表遷移驗證
  - 方法：清空 Signals 分頁，重跑 main.py，確認新表頭欄位順序與設計一致，並確認所有既有欄位值正確寫入

---

## 7. Risks & Assumptions

- **RISK-001**: signal_score 語意降級後的誤用風險
  - 說明：signal_score 保留在輸出 dict 中，未來維護者可能仍會誤用它作為分類依據。
  - 取捨建議：在 config.py 與 README 中明確加入「signal_score 僅作排序參考，不決定 action 與 buy_style」說明，並在 evaluate.py 加入行內註解強調此語意。必要時可將欄位改名為 `sort_score_base` 以降低誤用可能，但需評估下游讀取影響。

- **RISK-002**: 主條件過嚴導致保守型BUY 過少
  - 說明：保守型BUY 要求 above_ma20 AND above_ma60 AND chg_20d > 0 AND pct_from_high ≥ -25，對行情橫盤或牛皮市場，全觀察池都不符合時，推播可能連續多天無保守型BUY。
  - 取捨建議：pct_from_high 門檻可在 config.py 中以參數管理（如 `conservative_max_drawdown_pct = -25`），方便動態調整；同時在無 BUY 時的訊息文案中給予明確解釋（「今日市場未出現趨勢完整標的，建議觀望」），不要讓接收者誤解系統異常。

- **RISK-003**: 積極型BUY 定義過鬆導致推播品質下降
  - 說明：套路 B 與套路 C 的條件相對寬鬆（2 個以上技術訊號 + chg_5d > 0 即可），若觀察池中多數股票都短暫反彈，可能出現大量積極型BUY 訊號。
  - 取捨建議：為積極型BUY 加上 backtest_winrate ≥ 0.45 的最低底線（已在資格條件設計），並在訊息中固定加入「本週積極型 N 檔，請優先選 sort_score 前三」提示，讓接收者有取捨依據。

- **RISK-004**: Telegram 說明文字過長導致可讀性下降
  - 說明：五則訊息若每則都很長，接收者在手機上需大量滑動，反而降低實際參考率。
  - 取捨建議：第二則（固定策略說明）保持精簡，150 字以內；第三 / 四則每檔個股資訊嚴格控制在 6 行以內（代號+名稱 / buy_reason 最多 3 條 / primary_risk / 進出場 / 技術摘要）。可在 notify.py 加入行數計數檢查，超出自動截斷非關鍵行。

- **RISK-005**: Sheet 欄位新增過多導致維護成本提高
  - 說明：從 14 欄擴充至 22-24 欄，Google Sheet 橫向擴充後，手動查閱與公式維護都更複雜。
  - 取捨建議：嚴格限制只加入「分類決策必要」欄位（buy_style / buy_reason / primary_risk / avg_return / sort_score，共 5 個新增），避免把 risk_notes 每條都拆成獨立欄。buy_reason 仍以逗號分隔文字放入單欄，不要拆成多欄。

- **ASSUMPTION-001**: evaluate() 的 avg_return 取自 backtest() 回傳 dict 的 `avg_return` key，目前此 key 已確認存在於 backtest.py 實作中（`return {"winrate": ..., "samples": ..., "avg_return": ...}`）。
- **ASSUMPTION-002**: 保守型BUY 與積極型BUY 在同一個 Telegram chat 內分開訊息傳送，不拆成不同 chat_id。
- **ASSUMPTION-003**: tech_score 的 RSI 加分（20 分）已在現有 indicators.py 中實作，但未反映在任何文件中；本次校正只改文件，不改程式計算邏輯。

---

## 8. Related Specifications / Further Reading

- [stock_strategies/evaluate.py](stock_strategies/evaluate.py) — 現行決策邏輯（action 在趨勢欄位前決定的問題根源）
- [stock_strategies/notify.py](stock_strategies/notify.py) — 舊版 _explain_why 與 format_messages 三則架構
- [stock_strategies/sheet.py](stock_strategies/sheet.py) — 現行 14 欄 Signals 輸出
- [stock_strategies/backtest.py](stock_strategies/backtest.py) — avg_return 已有但未使用的位置（return dict 第三個 key）
- [stock_strategies/indicators.py](stock_strategies/indicators.py) — tech_score 實際最高 120 分的計算邏輯
- [stock_strategies/config.py](stock_strategies/config.py) — 與 README 不一致的實際參數值
- [README.md](README.md) — 六處已確認與實際不一致的舊描述位置

---

## 重構摘要說明

這份計畫嘗試回答一個核心問題：**為什麼現在這個系統用了這麼久，卻開始感覺「不太對」？**

答案不在功能缺失，而在語意混亂。現有系統的 BUY 是一個複合符號：它同時代表「基本面OK」、「技術分夠高」、「綜合分達門檻」，但沒有一個清楚的答案說「這檔現在的位置好不好？趨勢完不完整？」。接收者收到 BUY 訊號，其實不知道這是「可以放心分批」還是「要小心追高」，因為系統本身也沒有區分這件事。

更深層的問題是：趨勢、位置、量價這些最應該回答「現在適不適合布局」的欄位，目前是在 action 決定之後才算的。這意味著就算 above_ma20 是 False、chg_20d 是負的、pct_from_high 是 -60%，只要綜合分夠高，系統仍然輸出 BUY。

這次重構做的事，類比一下就是：原本評審是先看考試分數決定錄取，再補查體能；新版改成體能先過才看考試分數，而且根據體能狀況還分「穩健型錄取」與「需觀察的特殊錄取」。兩種都是錄取，但語意截然不同，對下一步的應對策略也不一樣。

實作順序的設計也刻意從「清查舊敘述」開始，因為若不先解決「文件說一套、系統跑一套」，任何重構都會在半途遇到「這個門檻到底是 3 年還是 2 年？」的混亂。把地基整平，才能安全地蓋新結構。
