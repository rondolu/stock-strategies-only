import os
import json

import gspread
from google.oauth2.service_account import Credentials


def get_gsheet():
    creds_json = os.environ["GOOGLE_CREDS_JSON"]
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(os.environ["GOOGLE_SHEET_ID"])


def read_watchlist() -> list[dict]:
    """從 Google Sheet Watchlist 分頁讀股票清單"""
    sh = get_gsheet()
    ws = sh.worksheet("Watchlist")
    rows = ws.get_all_records()
    # 正規化欄位名稱：去除首尾空白並轉小寫，避免 Google Sheet 標題有多餘空格或大小寫不一致
    rows = [{k.strip().lower(): v for k, v in r.items()} for r in rows]
    enabled = [
        r for r in rows
        if str(r.get("enabled", "")).upper() in ("TRUE", "1", "YES")
    ]
    return enabled


def append_signals(signals: list[dict]):
    """把結果寫回 Signals 分頁"""
    if not signals:
        return

    headers = [
        "date", "stock_id", "name", "action",
        "buy_style", "setup_type", "inst_net_3d", "inst_trend", "rev_yoy_pct", "rev_3m_trend", "rev_latest_month",
        "buy_reason",
        "signal_score", "sort_score", "tech_score",
        "above_ma20", "above_ma60", "chg_20d", "pct_from_high", "vol_ratio",
        "winrate", "samples", "avg_return",
        "entry_price", "stop_loss_price", "target_price", "rr_ratio", "position_pct",
        "primary_risk", "risk_notes", "tech_signals",
    ]

    sh = get_gsheet()
    try:
        ws = sh.worksheet("Signals")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Signals", rows=1000, cols=max(40, len(headers)))
        ws.append_row(headers)

    if ws.col_count < len(headers):
        ws.add_cols(len(headers) - ws.col_count)

    existing_header = ws.row_values(1)
    if existing_header != headers:
        ws.update(f"A1:{gspread.utils.rowcol_to_a1(1, len(headers)).split('1')[0]}1", [headers])

    rows = []
    for s in signals:
        c = s.get("components", {})
        t = s.get("trend", {})
        rows.append([
            s.get("date", ""),
            s.get("stock_id", ""),
            s.get("name", ""),
            s.get("action", ""),
            s.get("buy_style", ""),
            s.get("setup_type", ""),
            s.get("inst_net_3d", ""),
            s.get("inst_trend", ""),
            s.get("rev_yoy_pct", ""),
            s.get("rev_3m_trend", ""),
            s.get("rev_latest_month", ""),
            ", ".join(s.get("buy_reason", [])),
            s.get("signal_score", ""),
            s.get("sort_score", ""),
            c.get("tech_score", ""),
            t.get("above_ma20", ""),
            t.get("above_ma60", ""),
            t.get("chg_20d", ""),
            t.get("pct_from_high", ""),
            t.get("vol_ratio", ""),
            c.get("backtest_winrate", ""),
            c.get("backtest_samples", ""),
            c.get("avg_return", ""),
            s.get("entry_price", ""),
            s.get("stop_loss_price", ""),
            s.get("target_price", ""),
            s.get("risk_reward_ratio", ""),
            s.get("position_size_pct", ""),
            s.get("primary_risk", ""),
            " / ".join(s.get("risk_notes", [])),
            ", ".join(c.get("tech_signals", [])),
        ])
    ws.append_rows(rows)
