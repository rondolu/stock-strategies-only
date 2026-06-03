---
goal: 將台股選股策略從雙軸 buy_style 模型擴展至三維 setup_type × buy_style 雙軸分類架構，並接入 FinMind 免費版新資料集以落地大多頭成長股選股思維
version: "2.0"
date_created: 2026-06-03
last_updated: 2026-06-03
owner: kevin801221
status: 'In progress'
tags: [refactor, strategy, setup-type, growth-stock, finmind, evaluate, notify, data]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

## 本輪重構定位

前一輪重構（
efactor-strategy-buystyle-1.md）已成功將單一 BUY 拆分為「保守型BUY / 積極型BUY」雙風格，並修正了所有已知文件與程式碼不一致問題（BUG-001~008 全部修正完畢）。

本輪重構（v2.0）目標是在前一輪基礎上，**增加第二個分類軸 setup_type**，並接入 FinMind 免費版新資料集，使策略從「技術條件滿足就 BUY」進化成「先判斷這檔股票目前處於哪種行情結構，再決定如何切入」的大多頭成長股選股思維。

## 本輪 Refinement 提升了哪些清晰度（給閱讀計畫的人參考）

原始需求涵蓋面很廣，但「業務語言」（大多頭成長股思維）與「工程語言」（欄位、函式、判斷條件）之間有一道翻譯鴻溝。本次 refinement 做了以下關鍵轉換：

1. **把「先判斷 setup_type」的業務需求，拆解成可在現有 evaluate.py 中以 if/elif 實作的決策樹**，而不是停留在「貼近法人思維」的描述層。
2. **把「不要用 signal_score 主導決策」明確化成「setup_type / buy_style 的判斷條件清單不能含 signal_score 作為輸入變數」**，讓開發者有明確的不該踩的線。
3. **把欄位命名規則拉出來獨立成一節**，避免 Python 欄位名、Sheet 欄位名、Telegram 顯示詞三者在實作時隨機命名造成後期混亂。
4. **把分階段導入方案明確化**，讓每個階段都有明確的「完成標準」與「回報內容」，而不只是「先做 A 再做 B」的順序清單。

---

## 前輪進度確認：refactor-strategy-buystyle-1.md 實作狀態

| BUG/REQ | 描述 | 狀態 |
| ------- | ---- | ---- |
| BUG-001 | README 權重 30/30/40 → 實際 20/50/30 | ✅ 已修正 |
| BUG-002 | README EPS > 5 → 實際 eps_threshold=2.0 | ✅ 已修正 |
| BUG-003 | README 3年回測 → 實際 backtest_years=2 | ✅ 已修正 |
| BUG-004 | README 持有20日 → 實際 hold_days=10 | ✅ 已修正 |
| BUG-005 | indicators.py 說明 0-100 → 實際最高 120 | ✅ 已修正 |
| BUG-006 | notify.py 硬寫舊策略規則敘述 | ✅ 已修正 |
| BUG-007 | notify.py _explain_why 比對舊門檻 | ✅ 已替換為 _explain_buy_style /_explain_watch_gap |
| BUG-008 | evaluate.py 決策在趨勢計算前執行 | ✅ 已修正，趨勢欄位現在在決策前計算 |
| REQ-003 | buy_style conservative/aggressive 欄位 | ✅ 已實作 |
| REQ-005 | signal_score 降為排序分 | ✅ 已實作，sort_score 分離 |
| REQ-010 | Telegram 固定策略說明訊息（第二則） | ✅ 已實作 |

**注意**：以下殘留問題在 v2.0 中仍需清理：

- config.py 中 min_total_score_for_buy: 65 仍是死程式碼（已有注釋說明為相容性保留，但未刪除）
- README「週期股建議：改看營收年增率」的敘述預告了 v2.0 需求，但尚未落地

---

## 1. Requirements & Constraints

### 核心功能需求

- **REQ-001**: 新增第二分類軸 setup_type，值為 first_wave / pullback / momentum，僅 BUY 與 WATCH 才有非 null 值，SKIP / ERROR 為 null。
- **REQ-002**: 分類邏輯改為：衍生欄位 → setup_type → buy_style → action → sort_score，任一層的判斷不得以 signal_score 作為輸入。
- **REQ-003**: 接入 TaiwanStockInstitutionalInvestorsBuySell（三大法人）作為 Phase 1 核心新資料。
- **REQ-004**: 接入 TaiwanStockMonthRevenue（月營收）作為 Phase 1 核心新資料。
- **REQ-005**: 接入 TaiwanStockPER（本益比）作為 Phase 2 輔助資料。
- **REQ-006**: 接入 TaiwanStockMarginPurchaseShortSale（融資融券）作為 Phase 2 輔助資料。
- **REQ-007**: Telegram 單檔標籤須能呈現「保守型BUY｜主升段回測」格式，包含 buy_style 與 setup_type 的中文顯示名。
- **REQ-008**: Sheet Signals 分頁新增 setup_type 欄位，並調整欄位順序使核心分類欄位靠前。
- **REQ-009**: fund_pass（EPS/ROE）在 Phase 1 保留作為軟性資格條件，Phase 2 可用月營收成長率部分取代。
- **REQ-010**: 突破布林上軌、RSI > 70、KD > 80 維持為風險註記，不阻斷 BUY（延續前一輪設計）。
- **REQ-011**: sort_score 計算不得納入 setup_type 加分，以避免 setup_type 隱性成為排序主決策。
- **REQ-012**: Telegram 第二則策略說明訊息需同步更新，加入三種 setup_type 的簡短說明。
- **REQ-013**: README 需同步說明新的雙軸分類架構，清理「週期股」等指向未來功能的曖昧敘述。
- **REQ-014**: `fund_pass`（EPS/ROE）在 Phase 1 保留為硬性資格條件，不在本輪破壞。Phase 2 需正式引入 `growth_pass`（月營收年增代替），並提供覆蓋率對比後再決定是否切換。
- **REQ-015**: 每檔個股 BUY 訊息中，**個股本身**需附一句 setup_type 情境說明（`_explain_setup_type`），不依賴使用者去讀第二則策略說明訊息。
- **REQ-016**: 大多頭期間操作建議段落需明確提示「積極型BUY 在多頭行情中也值得重視」，避免 conservative +10 sort 分造成使用者忽略積極型機會。

### 資料與 API 限制

- **CON-001**: FinMind 免費帳號每日約 600 次請求限制。Phase 1 新增 2 個資料集後，每股請求數從 2 次增至 4 次。50 股觀察清單 = 200 次，安全。100 股 = 400 次，仍安全。超過 150 股需注意，建議計畫中加入警示。
- **CON-002**: TaiwanStockMonthRevenue 資料每月 10 日前後更新（前一個月營收），最新資料可能有 4-6 週延遲，不適合作為「即時」訊號，應作為「趨勢佐證」使用。**[實測確認]** 2026-06-03 執行結果：5 檔測試標的 coverage 100%，最新資料為 2026-05（4 月營收），`create_time=2026-05-08`，符合「約 10 日後更新」預期。最新欄位為 `revenue`（整數，單位元）。
- **CON-003**: 不使用分點、分K、還原價、週K、月K、八大行庫、持股分級、全市場單日批次資料等付費資料集。
- **CON-004**: 現有 main.py 中每股 API 呼叫之間有 0.6 秒等待，Phase 1 新增請求後不應縮短此間隔以避免限速。

### 向後相容性要求

- **CON-005**:　selection 欄位值（BUY / WATCH / SKIP / ERROR）不變，main.py 的排序邏輯不受影響。
- **CON-006**: sheet.py 的 append_signals 函式在 setup_type 欄位加入後仍需維持冪等性。
- **CON-007**:
otify.py 的 format_message（單數）向後相容包裝函式保留不動。
- **CON-008**: 若某股票 API 回傳空 DataFrame（新資料集未有資料），系統不應中斷，應以 None 填充並跳過該資料的判斷條件。

### 設計指引

- **GUD-001**: setup_type 的判斷應完全基於「現有 + Phase 1 新增」的衍生欄位，不依賴 signal_score。
- **GUD-002**: setup_type 的規則應盡量精簡（3-5 個條件判斷），避免變成難以維護的複雜決策樹。
- **GUD-003**: Telegram 訊息的 setup_type 說明不應超過 3 行，避免訊息膨脹。
- **GUD-004**: 若 Phase 1 新資料（法人/月營收）無法取得，strategy 應 graceful degrade 到 Phase 0（只用現有資料）的決策邏輯，而非中斷。
- **GUD-005**: `sort_score` 的 conservative +10 分在大多頭期間可能讓使用者系統性忽略積極型機會。**保留現有計算邏輯不動（避免 Phase 1 引入過多變數）**，但 notify.py 的操作建議段落需加入明確的「多頭期間積極型也值得關注」提示（REQ-016 對應的實作位置）。

### 安全要求

- **SEC-001**: 新增的 API 呼叫函式不得在 log 或 Telegram 訊息中輸出 FINMIND_TOKEN 或任何 API 憑證。
- **SEC-002**: FinMind API 回傳的原始資料不應直接序列化輸出到 Telegram，需經過明確的欄位提取與格式化。

---

## 2. 現況問題摘要

直接對照現有模組說明目前策略與新需求之間的落差：

### 2.1 evaluate.py — 策略邏輯落差

| 現況 | 問題 | 新需求 |
| ---- | ---- | ------ |
| fund_pass 為二元硬性 BUY 門檻（EPS > 2.0 AND ROE > 15） | 無法區分「體質好但目前無機會」與「體質普通但正在起漲」 | fund_pass 降為資格條件，允許部分寬鬆情況進入 WATCH |
| 沒有 setup_type 欄位 | 無法區分布局時機型態 | 新增 setup_type 判斷邏輯 |
| 無法區分「剛起漲」、「拉回布局」、「追強勢」 | 對不同型態的標的給出相同格式的建議 | 三種 setup_type 對應不同風險提示 |
| 缺乏法人買賣資料 | 無法判斷主力資金是否配合 | Phase 1 接入三大法人 |
| 缺乏月營收成長資料 | 基本面只有 EPS/ROE，無法反映近期業績加速 | Phase 1 接入月營收，衍生 YoY 成長率 |
| min_total_score_for_buy: 65 在 config.py 仍存在 | 死程式碼造成誤解 | Phase 1 清理時一併移除 |

### 2.2 data.py — 資料層落差

| 現況 | 問題 | 新需求 |
| ---- | ---- | ------ |
| 只有 get_price_history（TaiwanStockPrice）| 缺乏籌碼、本益比、月營收資料 | Phase 1 新增 3 個函式 |
| 只有 get_fundamental（EPS + ROE） | 只能判斷歷史基本面，無近期業績動能 | Phase 1 新增月營收函式，Phase 2 補充 PER |
| fetch_finmind 通用函式設計良好 | 可直接複用，無需修改 | 沿用 |

### 2.3 notify.py — 訊息層落差

| 現況 | 問題 | 新需求 |
| ---- | ---- | ------ |
| 股票標籤格式：保守型BUY | 排序 79.2 | 看不出布局型態 | 格式改為：保守型BUY｜主升段回測 | 排序 79.2 |
| 第二則策略說明無 setup_type 介紹 | 接收者不知道三種型態的差別 | 第二則加入 setup_type 三行說明 |
| _format_stock_detail 無法展示 setup_type | 訊息無法傳達時機型態資訊 | 修改格式函式加入 setup_type 標籤 |

### 2.4 sheet.py — 輸出層落差

| 現況 | 問題 | 新需求 |
| ---- | ---- | ------ |
| Signals 分頁無 setup_type 欄位 | 歷史紀錄無法追蹤各型態的實際表現 | 新增 setup_type 欄位，位置在 buy_style 旁 |
| 欄位順序以技術分、回測為前段 | 核心分類欄位不靠前，影響可讀性 | 調整欄位順序（Phase 2 優化） |

### 2.5 config.py — 死程式碼

| 現況 | 問題 | 新需求 |
| ---- | ---- | ------ |
| min_total_score_for_buy: 65 有相容性注釋但未移除 | 閱讀程式碼的人可能誤認為仍在使用 | Phase 1 清理時移除 |

---

## 3. 新策略框架總覽

新的完整決策流程（以資料流方式描述）：

\\\
[資料層 data.py]
  fetch_finmind (TaiwanStockPrice)           → get_price_history()         → df_price
  fetch_finmind (TaiwanStockFinancialStatements) → get_fundamental()        → {eps, roe}
  ★fetch_finmind (TaiwanStockInstitutionalInvestorsBuySell) → get_institutional() → {net_buy_3d, net_buy_10d, inst_trend}
  ★fetch_finmind (TaiwanStockMonthRevenue)   → get_month_revenue()          → {rev_yoy, rev_mom_trend, rev_3m_accel}
  [Phase 2]
  ★fetch_finmind (TaiwanStockPER)            → get_per()                    → {per, pbr, yield_pct}
  ★fetch_finmind (TaiwanStockMarginPurchaseShortSale) → get_margin_short()  → {margin_ratio, short_ratio, margin_trend}

[指標層 indicators.py]
  add_indicators(df_price) → {ma5, ma20, ma60, bb, kd, macd, atr, rsi}
  [考慮新增] ma120 (半年線) 用於趨勢階段判斷

[決策前衍生欄位 evaluate.py — 統一計算，不分散]
  from price:  chg_5d, chg_20d, vol_ratio, pct_from_high, above_ma20, above_ma60
  ★from inst:  inst_net_buy_3d, inst_trend (正向/中性/負向)
  ★from rev:   rev_yoy_pct, rev_accel (加速/持平/減速)
  ★from ma120: above_ma120 (是否站上半年線)

[Step 1] 資格過濾 (evaluate.py)
  fund_pass (EPS/ROE 軟性) → False 時不進 BUY，可進 WATCH

[Step 2] setup_type 判斷 (evaluate.py →_determine_setup_type())
  → "momentum"   : pct_from_high >= -15 AND above_ma20 AND chg_20d > 5
  → "pullback"   : above_ma60 AND above_ma20 AND -30 <= pct_from_high < -15 AND chg_5d <= 0
  → "first_wave" : 上述不成立的其他 BUY/WATCH 候選

[Step 3] buy_style 判斷 (evaluate.py — 現有邏輯微調)
  保守型 (conservative): 現有條件 + ★ inst_trend != "negative"（法人不淨賣）
  積極型 (aggressive): 現有條件 + ★ vol_ratio >= 1.2 或 inst_net_buy_3d > 0

[Step 4] action 決定 (evaluate.py)
  BUY:   conservative_eligible OR aggressive_eligible (AND fund_pass = True)
  WATCH: fund_pass AND (趨勢有方向但條件未全) OR (技術尚可但基本面未達)
  SKIP:  其他

[Step 5] sort_score 計算 (evaluate.py)
  sort_score = signal_score + avg_bonus (avg_return > 0 時)
  ★ + inst_bonus (Phase 1: inst_net_buy_3d > 0 加 5 分)

- style_bonus (conservative +10)
  setup_type 不參與 sort_score 計算 (避免隱性主決策)

[輸出層]
  → notify.py: 標籤 "保守型BUY｜主升段回測"，setup_type 說明，風險提示
  → sheet.py:  新增 setup_type 欄位
\\\

> ★ 表示本輪新增的部分

---

## 4. 免費版資料集優先級

### Phase 1 — 建議立即納入（高價值、落地難度低）

| 優先 | 資料集 | 加入理由 | 預期策略價值 | 落地難度 | API 額外呼叫數/股 |
| ---- | ------ | -------- | ------------ | -------- | ----------------- |
| P1-1 | **TaiwanStockInstitutionalInvestorsBuySell** | 三大法人（外資/投信/自營）是台股最可靠的籌碼面代理變數，日更 | 高：作為 buy_style 主條件輔助判斷，法人淨買入可提升保守型BUY信心 | 低：結構清晰，只需取近 N 日加總 | +1 |
| P1-2 | **TaiwanStockMonthRevenue** | 月營收為唯一免費版可取得的近期業績指標，每月更新 | 中：作為基本面升級的代理變數，YoY > 0% 且近 3 月加速可取代硬性 EPS/ROE 門檻 | 中：資料有延遲（最多 5-6 週），需正確處理「最新期」的識別邏輯 | +1 |

### Phase 2 — 建議第二階段納入（價值明確但不是最緊迫）

| 優先 | 資料集 | 加入理由 | 預期策略價值 | 落地難度 | API 額外呼叫數/股 |
| ---- | ------ | -------- | ------------ | -------- | ----------------- |
| P2-1 | **TaiwanStockPER** | 本益比 / 本淨比 / 殖利率，日更，可輔助判斷估值位置 | 中：作為「位置舒服度」的估值補充，高 PBR + 近高點時加強風險提示 | 低：結構簡單 | +1 |
| P2-2 | **TaiwanStockMarginPurchaseShortSale** | 融資增加 + 股價上漲 = 散戶追高訊號（偏負面）；融券增加 + 股價上漲 = 壓力存在 | 低至中：適合作為風險指標，不適合作為主條件 | 低：結構清晰 | +1 |

### 暫不建議納入（本輪）

| 資料集 | 原因 |
| ------ | ---- |
| TaiwanStockFinancialStatements（擴充） | 目前已使用，EPS/ROE 已足夠；季報延遲問題不變，不解決核心問題 |
| TaiwanStockDividend | 殖利率可從 PER 資料集取得，不必單獨接入 |
| TaiwanStockCashFlowsStatement | 落地複雜度高，需解析多期現金流，與當前策略方向不直接相關 |
| TaiwanStockBalanceSheet | 同上，解析複雜，ROE 等指標已由 FinancialStatements 提供 |
| TaiwanStockShareholding | 更新頻率低（月/季），對日策略幫助有限 |
| TaiwanStockSecuritiesLending | 借券資料解讀複雜，與選股核心距離較遠 |

### API 呼叫數量風險告知

| 觀察清單規模 | 現有 (2呼叫/股) | Phase 1 後 (4呼叫/股) | Phase 2 後 (6呼叫/股) |
| ------------ | -------------- | -------------------- | -------------------- |
| 50 股 | 100 次 | 200 次 | 300 次 |
| 100 股 | 200 次 | 400 次 | 600 次 ⚠️ 觸上限 |
| 150 股 | 300 次 | 600 次 ⚠️ | 900 次 ❌ 超限 |

**建議**：在 Phase 2 完成後，若觀察清單超過 100 股，應在 main.py 加入呼叫次數計數與警告。

---

## 5. 新增資料欄位與衍生指標規劃

### 5.1 Phase 1 新增：TaiwanStockInstitutionalInvestorsBuySell

**data.py 新增函式：**

\\\python
def get_institutional(stock_id: str, days: int = 20) -> dict:
    """
    回傳近 N 日三大法人買賣超資料摘要。
    資料集: TaiwanStockInstitutionalInvestorsBuySell
    start_date: 近 30 個自然日前（確保取到足夠交易日）

    回傳欄位:
      inst_net_buy_3d:  float  — 近 3 交易日三大法人合計淨買入（股數，正值為淨買）
      inst_net_buy_10d: float  — 近 10 交易日三大法人合計淨買入
      inst_trend:       str    — "positive" / "neutral" / "negative"
                                 positive: 近 3 日淨買 AND 近 10 日淨買
                                 negative: 近 3 日淨賣 AND 近 10 日淨賣
                                 neutral:  其他（混合或資料不足）
      foreign_net_3d:   float  — 外資近 3 日淨買入（單獨追蹤）
    """
\\\

**evaluate.py 衍生欄位（決策前統一計算）：**

- inst_net_buy_3d: 直接使用函式回傳值
- inst_trend: 直接使用函式回傳值
- inst_available: bool，若 get_institutional 回傳空值則 False，此時跳過法人條件判斷

**在策略中的角色：**

- inst_trend == "positive" → 保守型 BUY 次級加分條件（sort_score += 5），或作為積極型 BUY 的佐證
- inst_trend == "negative" → 風險註記：「法人近期淨賣出，注意資金退潮」，但不阻斷 BUY
- inst_net_buy_3d > 0 → sort_score 加分（inst_bonus = 5）

### 5.2 Phase 1 新增：TaiwanStockMonthRevenue

**data.py 新增函式：**

\\\python
def get_month_revenue(stock_id: str, months: int = 6) -> dict:
    """
    回傳近 N 個月營收摘要。
    資料集: TaiwanStockMonthRevenue
    start_date: 近 8 個月前（確保取到 6 個月資料）

    注意: 最新月份資料通常在當月 10 日後才會出現，
          因此 6 月初取到的最新資料可能仍是 4 月份。

    回傳欄位:
      rev_latest_month:  str    — 最新有資料的年月，例如 "2026-04"
      rev_yoy_pct:       float  — 最新月 YoY 成長率（%），與去年同期比較
      rev_mom_pct:       float  — 最新月 MoM 成長率（%），與上月比較
      rev_3m_trend:      str    — "accelerating" / "stable" / "decelerating"
                                  比較近 3 月 YoY 是否遞增（加速/持平/減速）
      rev_available:     bool   — 是否有足夠資料（至少 2 個月）
    """
\\\

**evaluate.py 衍生欄位（決策前統一計算）：**
-

ev_yoy_pct: 直接使用
-

ev_3m_trend: 直接使用
-

ev_available: 若 get_month_revenue 回傳 rev_available=False 則跳過月營收條件

**在策略中的角色：**

- Phase 1：作為 fund_pass 的「加分版補充」，不取代 EPS/ROE 硬性門檻
  -

ev_yoy_pct > 0 AND rev_3m_trend == "accelerating" → sort_score += 5，並在買進理由加入「月營收年增加速」
  -

ev_yoy_pct < -10 AND rev_available → 風險註記：「近期營收衰退，留意基本面轉弱」

- Phase 2（可選）：將 fund_pass 改為 growth_pass
  - growth_pass = fund_pass OR (rev_yoy_pct > 5 AND rev_3m_trend != "decelerating")
  - 這個變更是破壞性的，需在 Phase 2 計畫中獨立評估

### 5.3 Phase 2 新增：TaiwanStockPER

**data.py 新增函式：**

\\\python
def get_per(stock_id: str) -> dict:
    """
    回傳最新本益比 / 本淨比 / 殖利率。
    資料集: TaiwanStockPER
    start_date: 近 5 個交易日（取最新一筆）

    回傳欄位:
      per:           float  — 本益比
      pbr:           float  — 本淨比（股價淨值比）
      dividend_yield: float — 殖利率（%）
      per_available: bool
    """
\\\

**在策略中的角色：**

- pbr > 5 AND pct_from_high > -10 → 風險註記：「本淨比偏高且近高點，追高風險較大」
- per < 15 AND above_ma20 → sort_score 微加分（成長股低估值）
- 不作為 BUY/WATCH 主條件（估值相對性太強，易誤殺成長股）

### 5.4 Phase 2 新增：TaiwanStockMarginPurchaseShortSale

**data.py 新增函式：**

\\\python
def get_margin_short(stock_id: str, days: int = 10) -> dict:
    """
    回傳近 N 日融資融券摘要。
    資料集: TaiwanStockMarginPurchaseShortSale
    start_date: 近 20 個自然日

    回傳欄位:
      margin_ratio_latest:  float — 最新融資使用率（%）
      margin_trend:         str   — "increasing" / "stable" / "decreasing"
      short_ratio_latest:   float — 最新融券使用率（%）
      margin_available:     bool
    """
\\\

**在策略中的角色（純風險指標）：**

- margin_ratio_latest > 80 AND margin_trend == "increasing" → 風險註記：「融資使用率高且增加，散戶槓桿追高風險」
- 不作為 BUY/WATCH 主條件

---

## 6. setup_type 判斷規劃

### 6.1 函式設計

在 evaluate.py 新增私有函式 _determine_setup_type()，在決策流程的 Step 2 呼叫。

**輸入參數（全來自衍生欄位，不含 signal_score）：**

- bove_ma20: bool
- bove_ma60: bool
- chg_5d: float
- chg_20d: float
- pct_from_high: float
- ol_ratio: float
-  ech_signals: list[str]

**判斷邏輯（優先序由上到下，第一個滿足則返回）：**

\\\
momentum（續強追蹤）:
  必要條件: pct_from_high >= -15 AND above_ma20 AND chg_20d > 5
  說明: 在高位強勢中，未大幅拉回，近月趨勢仍正向
  排除: pct_from_high < -15（已非強勢高位）

pullback（主升段回測）:
  必要條件: above_ma60 AND above_ma20 AND chg_5d <= 0 AND -35 <= pct_from_high < -15
  說明: 在主升趨勢中（站上季線），出現短期拉回，屬於「回調找位置」型態
  排除: NOT above_ma60（季線未確立，不能說是主升段）

first_wave（第一波啟動）:
  = 預設（以上不成立的所有 BUY/WATCH 候選）
  常見情境: above_ma20 但 NOT above_ma60（剛突破月線但季線未確立）
           OR above_ma20 AND above_ma60 AND chg_20d <= 5（不算強勢，可能初啟動）
           OR 有 KD 黃金交叉 / MACD 多頭訊號但位置仍低
\\\

**SKIP 與 ERROR 的 setup_type：**

- SKIP 與 ERROR 不計算 setup_type，值為 None

### 6.2 各 setup_type 的風險提示政策

| setup_type | 固定風險提示 | 情境風險提示 |
| ---------- | ------------ | ------------ |
| first_wave | 「轉強初期波動較大，分批為宜」 | NOT above_ma60 → 「季線尚未確立，趨勢完整性待驗證」 |
| pullback | 無固定提示（相對安全的入場） | chg_5d < -5 → 「短線跌幅較大，確認回測支撐再進場」 |
| momentum | 「已在相對高位，追強需控制部位」 | RSI > 70 → 「RSI 過熱，注意短線回落」；bb_upper 突破 → 「超強勢但短線過熱」 |

### 6.3 setup_type 與 buy_style 的交叉說明

| setup_type × buy_style | 情境描述 | 訊息標籤 |
| ---------------------- | -------- | -------- |
| first_wave × conservative | 罕見：需同時滿足月季線站穩，但位置或趨勢剛啟動 | 🔵 保守型BUY｜第一波啟動 |
| first_wave × aggressive | 常見：趨勢轉強初期，積極提前切入 | 🟠 積極型BUY｜第一波啟動 |
| pullback × conservative | 最理想的入場組合 | 🔵 保守型BUY｜主升段回測 |
| pullback × aggressive | 較少見：趨勢完整但選擇積極切入 | 🟠 積極型BUY｜主升段回測 |
| momentum × conservative | 強勢但保守入場，注意追高 | 🔵 保守型BUY｜續強追蹤 |
| momentum × aggressive | 強勢追擊，風險最高的組合 | 🟠 積極型BUY｜續強追蹤 |

---

## 7. buy_style 判斷規劃

### 7.1 現有邏輯的保留與微調

Phase 1 對 buy_style 判斷邏輯的調整**最小**，主要是加入法人資料作為次級條件：

**保守型 (conservative) — 調整後：**

資格條件（不變）：fund_pass AND tech_score >= 50 AND backtest_samples >= 5

主條件（不變）：bove_ma20 AND above_ma60 AND chg_20d > 0 AND pct_from_high >= -25

次級條件（新增）：

- inst_trend == "positive" → buy_reason 加入「法人近期淨買入」
-

ev_yoy_pct > 0 AND rev_available → buy_reason 加入「月營收年增正向」

風險條件（新增）：

- inst_trend == "negative" → risk_notes 加入「法人近期淨賣出」

**積極型 (aggressive) — 調整後：**

資格條件（不變）：fund_pass AND tech_score >= 45 AND backtest_samples >= 3

主條件（不變）：套路 A / B / C 任一成立

次級條件（新增）：

- inst_net_buy_3d > 0 → buy_reason 加入「近期法人淨買入」
- 積極型本來就接受更多不確定性，法人條件為加分而非必要

### 7.2 如何避免 setup_type 與 buy_style 重複表達

- **setup_type 回答「此時處於哪種行情結構」**（客觀描述價格走勢位置）
- **buy_style 回答「用什麼操作方式切入」**（主觀反映風險偏好）
- 兩者獨立計算，互不干涉輸入變數
- 在訊息中合併展示為「保守型BUY｜主升段回測」，讓接收者理解「機會型態（pullback）」與「介入方式（conservative）」的雙重資訊

---

## 8. action 與 sort_score 的角色分離規劃

### 8.1 action 決策優先序

\\\
Step 1: 資料是否足夠？
  → len(px) < 100  →  SKIP（不計算 setup_type）

Step 2: 是否符合 BUY 資格？
  → fund_pass = False  →  不可 BUY，進入 WATCH 評估
  → fund_pass = True   →  進入 buy_style 評估

Step 3: 決定 buy_style → 同時決定 action = BUY
  → conservative_eligible  →  BUY + buy_style = "conservative"
  → aggressive_eligible    →  BUY + buy_style = "aggressive"

Step 4: 若兩種 BUY 條件都不成立，評估 WATCH
  → (fund_pass AND tech_score >= 45 AND 趨勢有方向) → WATCH
  → (fund_pass = False AND tech_score >= 50)         → WATCH
  → 其他                                              → SKIP

Step 5: setup_type 在 BUY/WATCH 決定後計算（不影響 action 結果）
\\\

### 8.2 sort_score 的計算與邊界

\\\python

# 保留現有邏輯，加入 inst_bonus，setup_type 絕不參與計算

avg_bonus   = avg_return * 10 if (avg_return and avg_return > 0) else 0
style_bonus = 10 if buy_style == "conservative" else 0
inst_bonus  = 5 if inst_net_buy_3d > 0 else 0    # Phase 1 新增
sort_score  = round(signal_score + avg_bonus + style_bonus + inst_bonus, 1)
\\\

**為何 setup_type 不參與 sort_score：**

- 若 pullback 加分，則所有保守型BUY｜主升段回測的股票都會浮到頂端，不管基本面品質。
- 這會造成「最舒服的布局點 = 最高排序分」的隱性耦合，讓 sort_score 再次成為主決策。
- 正確做法：sort_score 只反映「在相同 action 內，這檔相對品質如何」。

### 8.3 action 與 signal_score 的防混淆設計

- signal_score 的變數名保留，但在 evaluate.py 輸出 dict 中加入注釋：# 排序用途，不決定 action
- sort_score 應始終 >= signal_score（因有加分項），不應存在 sort_score < signal_score 的情況（除非有 bug）
- Sheet Signals 分頁欄位順序：action → setup_type → buy_style → sort_score → signal_score（signal_score 放後面，視覺上降低其重要性）

---

## 9. Telegram 訊息設計規劃

### 9.1 修改第一則（市場總覽）

**保持現有架構，微調統計列**：
\\\
📊 *V5.0 每日選股報告* YYYY/MM/DD
掃描 N 檔 | 保守型BUY N | 積極型BUY N | WATCH N | SKIP N
                 (第一波 N / 主升 N / 續強 N)     ← 新增 setup_type 統計
\\\

### 9.2 修改第二則（策略說明）

在現有「保守型 / 積極型」說明後加入 setup_type 說明（3 行，各一句）：
\\\
📖 *今日策略說明*

🔵 保守型BUY：趨勢較完整，月季線站穩，適合分批
🟠 積極型BUY：趨勢轉強或突破初期，波動較大

📍 *布局型態說明*
🟢 第一波啟動：趨勢剛發動，可早介入但需控制部位
🔷 主升段回測：主升途中拉回，相對舒服的布局點
🚀 續強追蹤：已在相對高位，追強需控管風險
\\\

### 9.3 修改個股標籤（_format_stock_detail）

**現在**：*2308 台達電*  保守型BUY | 排序 79.2

**新格式**：
\\\
*2308 台達電*  🔵 保守型BUY｜主升段回測 | 排序 79.2
\\\

emoji 對應：

- conservative: 🔵
- aggressive: 🟠
- setup_type first_wave: 🟢（在標籤中不單獨顯示，已反映在 buy_style 的說明裡）
- setup_type pullback: 🔷（可選，但不強制加）
- setup_type momentum: 🚀（可選）

**建議：標籤只顯示「buy_style + setup_type 中文名」，不加 setup_type emoji，以控制長度。**

即：🔵 保守型BUY｜主升段回測 或 🟠 積極型BUY｜第一波啟動

### 9.4 個股「為何歸類」說明的調整

現有的 _explain_buy_style 函式回傳 buy_reason 拼接。

Phase 1 新增一行 setup_type 說明：
\\\
💡 為何歸類: 站穩月季線 / 20日趨勢向上 / 法人近期淨買入
📍 布局型態: 主升段回測（季線站穩後短線拉回，相對合理的布局點）
\\\

_explain_setup_type(setup_type) 新增小函式，提供各型態的一句話描述：
\\\python
SETUP_TYPE_EXPLAIN = {
    "first_wave": "趨勢轉強初期，可早介入但波動較大",
    "pullback":   "主升段回測，季線確立後找支撐布局",
    "momentum":   "強勢延續，在相對高位追強需控管部位",
}
\\\

### 9.5 訊息長度控制原則

- 每檔個股在 BUY 訊息中佔用行數：現有約 7 行 → 新增 1 行（布局型態說明）→ 約 8 行
- 每則 Telegram 訊息限 8 檔（chunk_size=8 不變）
- 若保守型 BUY > 8 檔，仍分批成多則（現有邏輯不變）
- **⚠️ 挑戰**：若 setup_type × buy_style 組合都要獨立一則（6種 = 6則），訊息數暴增。建議維持「先按 buy_style 分兩則，標籤內顯示 setup_type」，不引入 6 種分組。

---

## 10. 欄位命名與顯示對照規劃

### 10.1 核心分類欄位對照表

| 內部 Python 變數 | 內部值 | Sheet 欄位名 | Sheet 顯示值 | Telegram 顯示詞 | README 對外用語 |
| --------------- | ------ | ------------ | ------------ | ---------------- | --------------- |
| ction | "BUY" | ction | BUY | （不直接顯示，由 buy_style 取代） | BUY |
| ction | "WATCH" | ction | WATCH | WATCH | WATCH |
| ction | "SKIP" | ction | SKIP | SKIP | SKIP |
| buy_style | "conservative" | buy_style | conservative | 保守型BUY | 保守型BUY |
| buy_style | "aggressive" | buy_style | aggressive | 積極型BUY | 積極型BUY |
| buy_style | None | buy_style | （空） | — | — |
| setup_type | "first_wave" | setup_type | first_wave | 第一波啟動 | 第一波啟動 |
| setup_type | "pullback" | setup_type | pullback | 主升段回測 | 主升段回測 |
| setup_type | "momentum" | setup_type | momentum | 續強追蹤 | 續強追蹤 |
| setup_type | None | setup_type | （空） | — | — |
| signal_score | float | signal_score | （數字） | 不顯示 | 排序參考分 |
| sort_score | float | sort_score | （數字） | 排序 N | 排序分 |

### 10.2 Phase 1 新增欄位對照表

| 內部 Python 變數 | 來源函式 | Sheet 欄位名 | 說明 |
| --------------- | -------- | ------------ | ---- |
| inst_net_buy_3d | get_institutional() | inst_net_3d | 近 3 日法人淨買入（股數） |
| inst_trend | get_institutional() | inst_trend | positive / neutral / negative |
|
ev_yoy_pct | get_month_revenue() |
ev_yoy_pct | 月營收年增率（%） |
|
ev_3m_trend | get_month_revenue() |
ev_3m_trend | accelerating / stable / decelerating |

### 10.3 命名規則原則

- **Python 內部欄位**：snake_case，前綴 inst_ /
ev_/ per_ / margin_ 區分資料來源
- **Sheet 欄位**：與 Python 變數名相同或縮短（sheet 中 col 名不超過 12 字元）
- **Telegram 顯示**：中文，不超過 6 個中文字（標籤）或 15 個中文字（說明句）
- **README 對外**：中文，與 Telegram 顯示詞完全一致，避免同一概念出現中英混用

---

## 11. README / 對外敘述更新規劃

### 11.1 需要更新的段落與舊敘述清理

| 位置 | 舊敘述 | 新敘述 |
| ---- | ------ | ------ |
| README 選股策略解析 → 分類表 | 只有「保守型BUY / 積極型BUY / WATCH / SKIP」 | 加入 setup_type 三種型態的說明 |
| README 選股策略解析 → 評分公式區 | 有 signal_score 公式的展示說明 | 加注「signal_score 僅作排序，不決定 BUY/WATCH/SKIP」，並說明 sort_score 的組成 |
| README 自訂策略 → 週期股建議 | 「改看營收年增率」、「加入產業景氣指標」等未落地的描述 | 說明月營收已作為輔助指標接入，並說明 Phase 2 的方向 |
| README 系統架構圖 | 只有「FinMind (財報 + K線)」 | 更新為「FinMind (K線 + 財報 + 法人 + 月營收)」 |
| README Telegram 通知範例 | 標籤格式為「保守型BUY \| 排序 79.2」 | 更新為「保守型BUY｜主升段回測 \| 排序 79.2」 |

### 11.2 需要新增的 README 段落

- 「雙軸分類模型說明」：用一張 3×2 矩陣表說明 setup_type × buy_style 的交叉情境
- 「FinMind 免費版資料集列表」：列出已接入的資料集與對應用途
- 「API 請求量說明」：根據新的呼叫數說明每日限制與建議觀察清單規模

---

## 12. 受影響檔案與修改方向

| 檔案 | 修改類型 | Phase | 欄位結構變更 | 向後相容風險 |
| ---- | -------- | ----- | ------------ | ------------ |
| stock_strategies/data.py | 新增函式 | Phase 1 | 無（只新增） | 無 |
| stock_strategies/evaluate.py | 重構決策流程、新增 setup_type | Phase 1 | 新增 setup_type 欄位至輸出 dict | 低：新欄位不影響現有欄位 |
| stock_strategies/config.py | 刪除 min_total_score_for_buy，新增 Phase 1 常數 | Phase 1 | 無 | 低：死程式碼 |
| stock_strategies/notify.py | 修改格式函式、第二則訊息、個股標籤 | Phase 1 | 無（輸出格式調整） | 低：format_message 向後相容包裝保留 |
| stock_strategies/sheet.py | 新增 setup_type 欄位、新增 inst/rev 欄位 | Phase 1 | Sheet 新增欄位 | 低：append_rows 冪等，新欄位不影響舊資料列 |
| stock_strategies/indicators.py | 可選：新增 ma120 | Phase 1（可選） | 新增 ma120 欄位至 df | 低：只新增不修改 |
| stock_strategies/backtest.py | 不修改 | — | 無 | 無 |
| main.py | 不修改（排序邏輯不變） | — | 無 | 無 |
| README.md | 更新策略說明、架構圖、通知範例 | Phase 1 結束後 | 無 | 無 |

---

## 13. 建議實作順序

### Phase 1 實作步驟（建議完成後確認再進 Phase 2）

**Step 1：清理舊程式碼（0.5h）**

1. 移除 config.py 中的 min_total_score_for_buy: 65
2. 確認 evaluate.py 中沒有任何地方引用 min_total_score_for_buy（grep 確認）

**Step 2：data.py 新增兩個函式（1h）**

1. 新增 get_institutional(stock_id, days=20) — 三大法人
2. 新增 get_month_revenue(stock_id, months=6) — 月營收
3. 加入 graceful degrade 處理（空 DataFrame → 回傳含 vailable=False 的 dict）

**Step 3：evaluate.py 重構（2h）**

1. 在衍生欄位計算區新增：inst_net_buy_3d, inst_trend,
ev_yoy_pct,
ev_3m_trend
2. 新增 _determine_setup_type() 私有函式
3. 在 buy_style 決策後、輸出 dict 前呼叫_determine_setup_type()
4. 更新 conservative/aggressive 的 buy_reason 邏輯（加入法人/月營收條件）
5. 更新 sort_score 計算（加入 inst_bonus）
6. 更新輸出 dict，加入 setup_type 欄位
7. 更新 result 中 components 的資訊（加入新欄位）

**Step 4：notify.py 更新（1h）**

1. 更新 _format_stock_detail：標籤格式改為「buy_style_label｜setup_type_label」
2. 新增 _style_setup_label(style, setup_type) 輔助函式（或在 _format_stock_detail 內 inline）
3. 新增 _explain_setup_type(setup_type) 輔助函式
4. 更新第二則訊息（加入 setup_type 三行說明）
5. 更新第一則訊息統計行（加入 setup_type 分布統計）

**Step 5：sheet.py 更新（0.5h）**

1. 在 header row 新增欄位：setup_type（在 buy_style 旁）, inst_net_3d, inst_trend,
ev_yoy_pct,
ev_3m_trend
2. 更新 ppend_signals 的 rows 建構邏輯

**Step 6：手動驗證（1h）**
（詳見第 15 節）

**Step 7：README 更新（1h）**

1. 更新通知範例
2. 新增雙軸分類說明
3. 更新系統架構圖

### Phase 2 實作步驟（需 Phase 1 穩定後再進行）

1. 新增 get_per() 函式
2. 新增 get_margin_short() 函式
3. 評估 growth_pass（月營收代替 EPS/ROE）的可行性（需分析實際資料品質）
4. 加入 PER/PBR 作為風險指標
5. 加入融資使用率風險提示
6. 調整 Sheet 欄位順序（core 欄位靠前）

---

## 14. 分階段導入方案

### Phase 0（已完成，v1.0）

- 目標：buy_style 雙風格分類
- 回報：DONE，所有 BUG-001~008 已修正

### Phase 1 目標與完成標準

**目標**：

- 新增 setup_type 三分類
- 接入三大法人 + 月營收
- Telegram 顯示雙軸標籤

**完成標準**：

1. 手動執行 main.py，所有 BUY 結果都有 setup_type 非 null 值
2. Telegram 第一則訊息統計行出現 setup_type 分布
3. 個股標籤格式正確（例：🔵 保守型BUY｜主升段回測）
4. Sheet Signals 分頁有 setup_type 欄位且值正確
5. 即使 get_institutional / get_month_revenue 回傳空值，程式不 crash

**Phase 1 結束回報內容（回報給使用者）**：

- 完整 Telegram 訊息截圖（含新標籤）
- Sheet 新欄位截圖
- 各 setup_type 分布統計（本次執行中 first_wave / pullback / momentum 各幾檔）
- API 呼叫次數確認（確認未超限）
- 任何資料品質問題（例如：某資料集回傳空值的股票比例）

**Phase 1 → Phase 2 的進入條件**：

1. Phase 1 穩定運行至少 5 個交易日（無 ERROR）
2. 月營收資料的覆蓋率 > 80%（觀察清單中有月營收資料的股票比例）
3. setup_type 分布不過度偏斜（例如不是 95% 都是 first_wave）

### Phase 2 目標

**目標**：

- 接入 PER + 融資融券
- 評估 growth_pass 取代 fund_pass 的可行性（資料品質驗證後決定）
- Sheet 欄位順序優化

**Phase 2 回報**：完成後提供 growth_pass vs fund_pass 覆蓋率對比、新風險提示觸發頻率統計

---

## 15. 驗證與測試計畫

### 目前測試現況

**⚠️ 問題：目前 repo 無任何自動化測試（tests/ 目錄不存在，pyproject.toml 無 pytest 設定）。**

所有驗證目前依賴手動執行，這在重構後風險較高。

### Phase 1 最小必要手動驗證

執行順序：

1. **欄位完整性驗證**
   - 取 3-5 檔已知股票，手動呼叫 evaluate()，print 輸出 dict
   - 確認：setup_type 存在且值為三者之一；inst_trend /
ev_yoy_pct 存在

2. **Graceful degrade 驗證**
   - 取一個 FinMind 可能無法人資料的小型股，確認 evaluate() 不 crash

3. **setup_type 邊界條件驗證**
   - 找一檔 pct_from_high >= -15 AND chg_20d > 5 的股票 → 應為 momentum
   - 找一檔 bove_ma60 AND above_ma20 AND chg_5d < 0 AND pct_from_high ~ -20% → 應為 pullback
   - 確認不符合上兩項的股票 → 應為 first_wave

4. **sort_score 一致性驗證**
   - 取 10 筆結果，確認 sort_score 無小於 signal_score 的情況（因有加分無減分）
   - 確認 setup_type 未出現在 sort_score 計算中

5. **Telegram 訊息格式驗證**
   - 確認每檔 BUY 標籤格式為「buy_style_label｜setup_type_label」
   - 確認第二則訊息包含 setup_type 三行說明
   - 確認第一則統計行有 setup_type 分布

6. **Sheet 欄位驗證**
   - 確認 setup_type 欄位出現在正確位置
   - 確認 inst_net_3d / rev_yoy_pct 欄位有值

### 建議最小測試腳本（可於 Phase 1 後新增）

\\\python

# tests/test_evaluate_smoke.py

# 只做 smoke test，不需要 mock API

def test_evaluate_returns_expected_fields():
    \"\"\"測試 evaluate() 輸出 dict 包含所有必要欄位\"\"\"
    required = {"action", "buy_style", "setup_type", "sort_score", "signal_score",
                "risk_notes", "primary_risk", "trend", "components"}
    # 因需要真實 API，此 test 在 CI 中 skip，僅本機執行
    ...

def test_determine_setup_type_momentum():
    from stock_strategies.evaluate import_determine_setup_type
    result = _determine_setup_type(
        above_ma20=True, above_ma60=True, chg_5d=2.0,
        chg_20d=10.0, pct_from_high=-10.0, vol_ratio=1.1, tech_signals=[]
    )
    assert result == "momentum"

def test_determine_setup_type_pullback():
    from stock_strategies.evaluate import_determine_setup_type
    result = _determine_setup_type(
        above_ma20=True, above_ma60=True, chg_5d=-2.0,
        chg_20d=5.0, pct_from_high=-20.0, vol_ratio=0.9, tech_signals=[]
    )
    assert result == "pullback"
\\\

---

## 16. 風險與取捨

### 技術風險

| 風險 | 嚴重度 | 可能性 | 緩解方案 |
| ---- | ------ | ------ | -------- |
| 月營收資料更新延遲（最多 6 週）導致「最新月份」辨識邏輯錯誤 | 高 | 中 | get_month_revenue 中明確記錄
ev_latest_month，並在 Telegram 提示資料截止月份 |
| 三大法人資料對部分小型股或 ETF 無資料 | 中 | 高 | graceful degrade 設計，法人條件僅在 inst_available=True 時啟用 |
| FinMind API 臨時 500/429 錯誤導致整批失敗 | 高 | 低至中 | 現有  ry/except 已有部分保護；建議在 main.py 加入單股失敗不阻斷整批的邏輯 |
| setup_type 規則過於依賴 pct_from_high 導致同期大漲後所有股票都變 momentum | 中 | 中 | 使用「近 252 日高點」而非「近期高點」，並在 Phase 1 完成後觀察分布，若偏斜則調整閾值 |

### 策略風險

| 風險 | 嚴重度 | 緩解方案 |
| ---- | ------ | -------- |
| 三大法人淨買入不代表股價一定上漲（法人也會被套） | 中 | 法人條件只作次級加分，不作主條件，不阻斷 BUY |
| 月營收正向但股價已過高（估值泡沫）| 中 | Phase 2 的 PER/PBR 指標可補充此判斷；Phase 1 暫以 pct_from_high 作為位置提示 |
| setup_type 的三個類別在實際資料中分布不均（例如大多頭期間 80% 都是 momentum） | 低 | 這是正常現象（市場結構反映在分類上），但需在說明文件中告知使用者分類會隨市場環境變化 |

### 設計挑戰（已納入正式需求）

以下三項設計挑戰已正式提升為需求條目（REQ-014 / REQ-015 / REQ-016）與設計指引（GUD-005），不再只是「建議」：

1. **`fund_pass` 與大多頭成長股思維的根本衝突** → 已納入 REQ-014
   - EPS > 2.0 排除轉虧為盈初期公司，這類公司在大多頭啟動時往往最強
   - Phase 1：保留硬性條件（不破壞現有流程）
   - Phase 2：正式引入 `growth_pass = fund_pass OR (rev_yoy_pct > 5 AND rev_3m_trend != "decelerating")`，需覆蓋率數據支撐再切換
   - **[月營收覆蓋率實測]** 5 檔 100% 有資料，但需在完整觀察清單（可能包含小型股、ETF）上驗證實際覆蓋率

2. **訊息接收者不一定看完全部說明** → 已納入 REQ-015
   - 個股訊息本身需有一句 setup_type 情境說明
   - 對應實作：`_explain_setup_type(setup_type)` 函式，在 `_format_stock_detail` 中呼叫
   - 不依賴使用者去讀第二則策略說明

3. **sort_score 的 conservative +10 分在大多頭期間是否合理** → 已納入 GUD-005 + REQ-016
   - 計算邏輯 Phase 1 不動（避免引入多餘變數）
   - 但 notify.py 的操作建議段落需明確加入「多頭期間積極型BUY也值得重視」提示
   - Phase 2 後可根據回測績效決定是否調整 +10 加成的合理性

---

## 17. 最小確認執行結果（2026-06-03 完成）

已透過 `scripts/confirm_datasets.py` 實際呼叫 FinMind API 並確認，**三項全數通過，可直接進入 Phase 1 實作**。

### CONFIRM-1：TaiwanStockInstitutionalInvestorsBuySell ✅

| 項目 | 結果 |
| ---- | ---- |
| 欄位結構 | `date`, `stock_id`, `buy`, `name`, `sell` |
| `name` 列舉值 | `Dealer_Hedging`, `Dealer_self`, `Foreign_Dealer_Self`, `Foreign_Investor`, `Investment_Trust` |
| 5 檔覆蓋率 | **5/5 = 100%** |
| 最新資料日期 | 2026-06-02 |
| 2330 三大淨買 | +785,136 股 |

**`get_institutional()` 設計更新（根據實測）：**

- 淨買：`net = buy - sell`，依 `date` 分組加總
- 外資欄位名稱：`Foreign_Investor`（非 `Foreign`）
- 自營商含兩子類型：`Dealer_Hedging` + `Dealer_self`
- 三大合計排除 `Foreign_Dealer_Self`（避免與 `Foreign_Investor` 雙重計算）

### CONFIRM-2：TaiwanStockMonthRevenue ✅

| 項目 | 結果 |
| ---- | ---- |
| 欄位結構 | `date`, `stock_id`, `country`, `revenue`, `revenue_month`, `revenue_year`, `create_time` |
| 營收主欄位 | `revenue`（整數，單位：元） |
| `revenue_month` | 月份整數（例：4），**非**營收數值 |
| 最新資料月份 | 2026-05（4 月份營收） |
| 資料延遲 | 4 月份於 5/8 公告（約 8 天） |
| 5 檔覆蓋率 | **5/5 = 100%** |
| 2330 YoY（2026-05 vs 2025-05） | **+17.5%** |

**`get_month_revenue()` 設計更新（根據實測）：**

- 使用 `revenue` 欄位（非 `revenue_month`，後者是月份整數）
- 最新月份：`df.sort_values('date').iloc[-1]`
- YoY：`df.iloc[-1]['revenue'] / df.iloc[-13]['revenue'] - 1`
- Telegram 顯示 `rev_latest_month`（例：「月營收截至 2026-04」）

### CONFIRM-3：sheet.py Signals 現有欄位 ✅

現有 **25 個欄位**（順序）：

`date`, `stock_id`, `name`, `action`, `buy_style`, `buy_reason`, `signal_score`, `sort_score`, `tech_score`, `above_ma20`, `above_ma60`, `chg_20d`, `pct_from_high`, `vol_ratio`, `winrate`, `samples`, `avg_return`, `entry_price`, `stop_loss_price`, `target_price`, `rr_ratio`, `position_pct`, `primary_risk`, `risk_notes`, `tech_signals`

**Phase 1 新增 +6 欄（插入至 `buy_style` 之後）：**

| 新 # | 欄位名 | 說明 |
|------|--------|------|
| 6 | `setup_type` | first_wave / pullback / momentum / null |
| 7 | `inst_net_3d` | 近 3 日三大法人合計淨買入（股） |
| 8 | `inst_trend` | positive / neutral / negative |
| 9 | `rev_yoy_pct` | 月營收年增率（%） |
| 10 | `rev_3m_trend` | accelerating / stable / decelerating |
| 11 | `rev_latest_month` | 最新有資料月份（例：2026-04） |

合計 **31 欄**。現有舊資料列以 `append_rows` 方式追加，不受影響。

---

## 17b. 尚待手動執行的確認項目

以下兩項需使用者在本機執行（需完整環境變數，Agent 無法代勞）：

1. **基準執行（Baseline Run）**：`python main.py`，記錄重構前輸出 log，建議存成 `logs/baseline_YYYYMMDD.txt`
2. **Google Sheet 欄位手動確認**：確認 Signals 分頁是否有「凍結欄」、「資料驗證」或「公式參照」會因欄位增加而位移

> `scripts/confirm_datasets.py` 腳本已建立，後續可重複執行驗證 API 覆蓋率。

---

## 18. 相關規格 / 進一步閱讀

- [plan/refactor-strategy-buystyle-1.md](refactor-strategy-buystyle-1.md) — 前一輪重構計畫（v1.0，已完成）
- [stock_strategies/evaluate.py](../stock_strategies/evaluate.py) — 主決策邏輯
- [stock_strategies/data.py](../stock_strategies/data.py) — FinMind 資料抓取層
- [stock_strategies/notify.py](../stock_strategies/notify.py) — Telegram 格式化
- [FinMind 免費版 API 文件](https://finmindtrade.com/analysis/#/data/api) — 待確認各資料集欄位結構（外部）
