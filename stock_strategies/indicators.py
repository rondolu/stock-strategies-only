import pandas as pd
import numpy as np


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["ma5"] = df["close"].rolling(5).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()

    df["bb_mid"] = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std

    low_min = df["low"].rolling(9).min()
    high_max = df["high"].rolling(9).max()
    rsv = (df["close"] - low_min) / (high_max - low_min) * 100
    df["k"] = rsv.ewm(com=2).mean()
    df["d"] = df["k"].ewm(com=2).mean()

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["dif"] = ema12 - ema26
    df["dea"] = df["dif"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["dif"] - df["dea"]

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss))

    return df


def tech_score_at(row: pd.Series) -> dict:
    """對一天計算技術分 (0-120，含 RSI 最高 20 分加分)"""
    score = 0
    signals = []

    if pd.notna(row["ma20"]) and pd.notna(row["ma60"]):
        if row["close"] > row["ma20"] > row["ma60"]:
            score += 25
            signals.append("均線多頭")
        elif row["close"] > row["ma20"]:
            score += 12

    if pd.notna(row["bb_lower"]) and pd.notna(row["bb_mid"]):
        dist = (row["close"] - row["bb_lower"]) / row["bb_lower"]
        if 0 < dist < 0.03:
            score += 25
            signals.append("布林下軌反彈")
        elif row["close"] < row["bb_mid"]:
            score += 10

    if pd.notna(row["k"]) and pd.notna(row["d"]):
        if row["k"] > row["d"] and row["k"] < 80:
            score += 25
            signals.append("KD黃金交叉")
        elif row["k"] > row["d"]:
            score += 10

    if pd.notna(row["macd_hist"]):
        if row["macd_hist"] > 0 and row["dif"] > row["dea"]:
            score += 25
            signals.append("MACD多頭")
        elif row["macd_hist"] > 0:
            score += 10

    if pd.notna(row.get("rsi")) and 30 < row["rsi"] < 70:
        score += 20
        signals.append("RSI 中性區")    
        

    return {"score": score, "signals": signals}
