import os
from datetime import datetime, timedelta

import requests
import pandas as pd

from .config import FINMIND_URL


def fetch_finmind(dataset: str, stock_id: str, start_date: str) -> pd.DataFrame:
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date,
        "token": os.environ["FINMIND_TOKEN"],
    }
    r = requests.get(FINMIND_URL, params=params, timeout=20)
    r.raise_for_status()
    return pd.DataFrame(r.json().get("data", []))


def get_price_history(stock_id: str, years: int = 3) -> pd.DataFrame:
    start = (datetime.now() - timedelta(days=365 * years + 60)).strftime("%Y-%m-%d")
    df = fetch_finmind("TaiwanStockPrice", stock_id, start)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df.rename(columns={"max": "high", "min": "low", "Trading_Volume": "volume"})
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_fundamental(stock_id: str) -> dict:
    """近 3 完整年度 EPS、ROE"""
    start = f"{datetime.now().year - 4}-01-01"
    df = fetch_finmind("TaiwanStockFinancialStatements", stock_id, start)
    if df.empty:
        return {"eps": {}, "roe": {}}

    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    eps = df[df["type"] == "EPS"].groupby("year")["value"].sum().to_dict()
    roe = df[df["type"] == "ROE"].groupby("year")["value"].sum().to_dict()

    cy = datetime.now().year
    return {
        "eps": {y: round(v, 2) for y, v in eps.items() if cy - 3 <= y < cy},
        "roe": {y: round(v, 2) for y, v in roe.items() if cy - 3 <= y < cy},
    }


def get_institutional(stock_id: str, days: int = 20) -> dict:
    """回傳近 N 日三大法人買賣超摘要。"""
    start = (datetime.now() - timedelta(days=max(days * 2, 30))).strftime("%Y-%m-%d")
    df = fetch_finmind("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start)
    default = {
        "available": False,
        "inst_net_buy_3d": 0.0,
        "inst_net_buy_10d": 0.0,
        "inst_trend": "neutral",
        "foreign_net_3d": 0.0,
    }
    required = {"date", "name", "buy", "sell"}
    if df.empty or not required.issubset(set(df.columns)):
        return default

    include_names = {
        "Foreign_Investor",
        "Investment_Trust",
        "Dealer_Hedging",
        "Dealer_self",
    }

    df = df[df["name"].isin(include_names)].copy()
    if df.empty:
        return default

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["buy"] = pd.to_numeric(df["buy"], errors="coerce")
    df["sell"] = pd.to_numeric(df["sell"], errors="coerce")
    df = df.dropna(subset=["date", "buy", "sell"])
    if df.empty:
        return default

    df["net"] = df["buy"] - df["sell"]
    by_date = df.groupby("date", as_index=False)["net"].sum().sort_values("date")
    net_3d = float(by_date["net"].tail(3).sum())
    net_10d = float(by_date["net"].tail(10).sum())

    foreign_df = df[df["name"] == "Foreign_Investor"].groupby("date", as_index=False)["net"].sum().sort_values("date")
    foreign_net_3d = float(foreign_df["net"].tail(3).sum()) if not foreign_df.empty else 0.0

    inst_trend = "neutral"
    if net_3d > 0 and net_10d > 0:
        inst_trend = "positive"
    elif net_3d < 0 and net_10d < 0:
        inst_trend = "negative"

    return {
        "available": True,
        "inst_net_buy_3d": net_3d,
        "inst_net_buy_10d": net_10d,
        "inst_trend": inst_trend,
        "foreign_net_3d": foreign_net_3d,
    }


def get_month_revenue(stock_id: str, months: int = 6) -> dict:
    """回傳月營收 YoY 與近期趨勢摘要。"""
    # YoY 需要至少 13 個月資料，這裡多抓一些避免公告時間差造成缺洞。
    start = (datetime.now() - timedelta(days=max((months + 14) * 31, 420))).strftime("%Y-%m-%d")
    df = fetch_finmind("TaiwanStockMonthRevenue", stock_id, start)
    default = {
        "available": False,
        "rev_latest_month": None,
        "rev_yoy_pct": None,
        "rev_mom_pct": None,
        "rev_3m_trend": "stable",
    }
    required = {"date", "revenue"}
    if df.empty or not required.issubset(set(df.columns)):
        return default

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    df = df.dropna(subset=["date", "revenue"]).sort_values("date").reset_index(drop=True)
    if len(df) < 2:
        return default

    df["mom"] = df["revenue"].pct_change()
    df["yoy"] = df["revenue"] / df["revenue"].shift(12) - 1

    latest = df.iloc[-1]
    latest_month = latest["date"].strftime("%Y-%m")
    latest_yoy = None if pd.isna(latest["yoy"]) else float(latest["yoy"] * 100)
    latest_mom = None if pd.isna(latest["mom"]) else float(latest["mom"] * 100)

    yoy_series = df["yoy"].dropna()
    trend = "stable"
    if len(yoy_series) >= 3:
        last3 = yoy_series.tail(3).values
        if last3[0] < last3[1] < last3[2]:
            trend = "accelerating"
        elif last3[0] > last3[1] > last3[2]:
            trend = "decelerating"

    return {
        "available": True,
        "rev_latest_month": latest_month,
        "rev_yoy_pct": latest_yoy,
        "rev_mom_pct": latest_mom,
        "rev_3m_trend": trend,
    }
