from datetime import datetime
from typing import Optional

import pandas as pd

from .config import CONFIG
from .data import get_fundamental, get_institutional, get_month_revenue, get_price_history
from .indicators import add_indicators, tech_score_at
from .backtest import backtest


def _determine_setup_type(
    above_ma20: bool,
    above_ma60: bool,
    chg_5d: float,
    chg_20d: float,
    pct_from_high: float,
) -> str:
    if pct_from_high >= -15 and above_ma20 and chg_20d > 5:
        return "momentum"
    if above_ma60 and above_ma20 and chg_5d <= 0 and -35 <= pct_from_high < -15:
        return "pullback"
    return "first_wave"


def _pick_primary_risk(risk_notes: list[str], fallback: str = "尚未觀察到明顯風險") -> str:
    if not risk_notes:
        return fallback
    priority_keywords = [
        "短線波動較大",
        "基本面未過門檻",
        "歷史勝率",
        "回測樣本",
        "回測平均報酬",
        "布林上軌",
        "RSI",
        "KD",
        "量能",
        "距高點",
    ]
    for keyword in priority_keywords:
        for note in risk_notes:
            if keyword in note:
                return note
    return risk_notes[0]


def evaluate(stock_id: str, name: str) -> Optional[dict]:
    result = {
        "stock_id": stock_id,
        "name": name,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "risk_notes": [],
    }

    try:
        fund = get_fundamental(stock_id)
        eps_vals = list(fund["eps"].values())
        roe_vals = list(fund["roe"].values())
        fund_pass = (
            len(eps_vals) >= 2
            and len(roe_vals) >= 2
            and min(eps_vals) > CONFIG["eps_threshold"]
            and min(roe_vals) > CONFIG["roe_threshold"]
        )

        px = get_price_history(stock_id, CONFIG["backtest_years"])
        if len(px) < 100:
            result["action"] = "SKIP"
            result["risk_notes"].append("價格資料不足")
            return result

        px = add_indicators(px)
        latest = px.iloc[-1]
        ts = tech_score_at(latest)
        bt = backtest(px)
        inst = get_institutional(stock_id)
        rev = get_month_revenue(stock_id)

        chg_5d = (latest["close"] / px.iloc[-6]["close"] - 1) * 100 if len(px) >= 6 else 0
        chg_20d = (latest["close"] / px.iloc[-21]["close"] - 1) * 100 if len(px) >= 21 else 0
        vol_5 = px["volume"].iloc[-5:].mean()
        vol_20 = px["volume"].iloc[-20:].mean()
        vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 1
        high_252 = px["high"].iloc[-252:].max() if len(px) >= 252 else px["high"].max()
        pct_from_high = (latest["close"] / high_252 - 1) * 100
        above_ma20 = latest["close"] > latest["ma20"] if pd.notna(latest["ma20"]) else False
        above_ma60 = latest["close"] > latest["ma60"] if pd.notna(latest["ma60"]) else False

        fund_score = 100 if fund_pass else 40
        tech_score = ts["score"]
        raw_winrate = bt.get("winrate")
        winrate = raw_winrate if raw_winrate is not None else 0.5
        samples = bt.get("samples", 0)
        avg_return = bt.get("avg_return")
        inst_available = bool(inst.get("available"))
        inst_net_buy_3d = float(inst.get("inst_net_buy_3d", 0.0))
        inst_trend = inst.get("inst_trend", "neutral")
        rev_available = bool(rev.get("available"))
        rev_yoy_pct = rev.get("rev_yoy_pct")
        rev_3m_trend = rev.get("rev_3m_trend", "stable")
        rev_latest_month = rev.get("rev_latest_month")
        bt_score = winrate * 100

        # signal_score 只用於排序，不作為主決策依據。
        signal_score = round(
            0.2 * fund_score + 0.5 * tech_score + 0.3 * bt_score, 1
        )

        action = "SKIP"
        buy_style = None
        buy_reason: list[str] = []

        entry = float(latest["close"])
        stop_price = round(entry * (1 - CONFIG["stop_loss"]), 2)
        target_price = round(entry * (1 + CONFIG["target_return"]), 2)
        rr = round(CONFIG["target_return"] / CONFIG["stop_loss"], 2)
        position_pct = min(2.0 / (CONFIG["stop_loss"] * 100) * 100, 20.0)

        risk_notes = result["risk_notes"]

        if samples < 8:
            risk_notes.append(f"回測樣本僅 {samples} 次，統計弱")
        if not fund_pass:
            risk_notes.append("基本面未過門檻")
        if raw_winrate is not None and raw_winrate < 0.5:
            risk_notes.append(f"歷史勝率 {raw_winrate*100:.0f}% 低於五成")
        if avg_return is not None and avg_return <= 0:
            risk_notes.append("回測平均報酬為負，參考價值有限")
        if pd.notna(latest.get("bb_upper")) and latest["close"] > latest["bb_upper"]:
            risk_notes.append("短線過熱，接近布林上軌")
        if pd.notna(latest.get("rsi")) and latest["rsi"] > 70:
            risk_notes.append("RSI 過熱區，注意短線回落")
        if pd.notna(latest.get("k")) and latest["k"] > 80:
            risk_notes.append("KD 高檔，注意回落")
        if vol_ratio < 0.8:
            risk_notes.append("量能萎縮，動能疑慮")
        if pct_from_high < -40:
            risk_notes.append("距高點逾 40%，需確認非下跌途中")
        if inst_available and inst_trend == "negative":
            risk_notes.append("法人近期淨賣出，留意資金退潮")
        if rev_available and rev_yoy_pct is not None and rev_yoy_pct < -10:
            risk_notes.append("近期月營收年減幅較大，留意基本面轉弱")

        conservative_eligible = (
            fund_pass
            and tech_score >= 50
            and samples >= 5
            and above_ma20
            and above_ma60
            and chg_20d > 0
            and pct_from_high >= -25
        )

        strength_signals = {"均線多頭", "KD黃金交叉", "MACD多頭"}
        strength_hits = len(strength_signals.intersection(set(ts.get("signals", []))))
        aggressive_guard = not (
            (not above_ma20 and not above_ma60)
            or pct_from_high < -50
            or (raw_winrate is not None and raw_winrate < 0.35)
        )
        agg_pattern_a = above_ma20 and chg_20d > -5 and vol_ratio >= 1.2
        agg_pattern_b = strength_hits >= 2 and chg_5d > 0
        agg_pattern_c = vol_ratio >= 1.5 and chg_5d > 2
        aggressive_eligible = (
            fund_pass
            and tech_score >= 45
            and samples >= 3
            and aggressive_guard
            and (agg_pattern_a or agg_pattern_b or agg_pattern_c)
        )

        if conservative_eligible:
            action = "BUY"
            buy_style = "conservative"
            buy_reason = ["站穩月線與季線", "20日趨勢向上", "位置相對合理，適合分批"]
            if vol_ratio >= 1.0:
                buy_reason.append("量能平穩或放大")
            if raw_winrate is not None and raw_winrate >= 0.55:
                buy_reason.append("回測勝率具優勢")
            if inst_available and inst_trend == "positive":
                buy_reason.append("法人近期淨買入")
            if rev_available and rev_yoy_pct is not None and rev_yoy_pct > 0:
                buy_reason.append("月營收年增為正")
        elif aggressive_eligible:
            action = "BUY"
            buy_style = "aggressive"
            buy_reason = ["趨勢轉強或接近突破", "可提早切入但需控管部位"]
            if agg_pattern_a:
                buy_reason.append("站上月線且量能放大")
            if agg_pattern_b:
                buy_reason.append("多項技術訊號共振")
            if agg_pattern_c:
                buy_reason.append("短線量價突破")
            if inst_available and inst_net_buy_3d > 0:
                buy_reason.append("近期法人偏多")
            if rev_available and rev_yoy_pct is not None and rev_yoy_pct > 0:
                buy_reason.append("月營收維持年增")
            risk_notes.append("積極型BUY 短線波動較大，建議小部位或分批")
            if not above_ma60:
                risk_notes.append("未站上季線，趨勢尚未完整確立")
        else:
            watch = (
                (fund_pass and (not above_ma20 or chg_20d <= 0) and tech_score >= 45)
                or (
                    fund_pass
                    and tech_score >= 40
                    and (samples < 5 or (raw_winrate is not None and raw_winrate < 0.45))
                )
                or ((not fund_pass) and tech_score >= 50)
            )
            action = "WATCH" if watch else "SKIP"

        setup_type = None
        if action in ("BUY", "WATCH"):
            setup_type = _determine_setup_type(
                above_ma20=bool(above_ma20),
                above_ma60=bool(above_ma60),
                chg_5d=float(chg_5d),
                chg_20d=float(chg_20d),
                pct_from_high=float(pct_from_high),
            )

        avg_bonus = (avg_return * 10) if (avg_return is not None and avg_return > 0) else 0
        style_bonus = 10 if buy_style == "conservative" else 0
        inst_bonus = 5 if inst_available and inst_net_buy_3d > 0 else 0
        sort_score = round(signal_score + avg_bonus + style_bonus + inst_bonus, 1)

        primary_risk = _pick_primary_risk(risk_notes)

        result.update({
            "action": action,
            "setup_type": setup_type,
            "buy_style": buy_style,
            "buy_reason": buy_reason,
            "primary_risk": primary_risk,
            "signal_score": signal_score,
            "sort_score": sort_score,
            "inst_net_3d": round(inst_net_buy_3d, 0),
            "inst_trend": inst_trend,
            "rev_yoy_pct": round(rev_yoy_pct, 2) if rev_yoy_pct is not None else None,
            "rev_3m_trend": rev_3m_trend,
            "rev_latest_month": rev_latest_month,
            "components": {
                "fundamental_pass": fund_pass,
                "eps_min": min(eps_vals) if eps_vals else None,
                "roe_min": min(roe_vals) if roe_vals else None,
                "tech_score": tech_score,
                "tech_signals": ts["signals"],
                "backtest_winrate": raw_winrate,
                "backtest_samples": samples,
                "avg_return": avg_return,
                "inst_available": inst_available,
                "rev_available": rev_available,
            },
            "trend": {
                "chg_5d": round(chg_5d, 2),
                "chg_20d": round(chg_20d, 2),
                "vol_ratio": round(vol_ratio, 2),
                "pct_from_high": round(pct_from_high, 1),
                "above_ma20": bool(above_ma20),
                "above_ma60": bool(above_ma60),
            },
            "entry_price": entry,
            "stop_loss_price": stop_price,
            "target_price": target_price,
            "risk_reward_ratio": rr,
            "position_size_pct": round(position_pct, 1),
        })
        return result

    except Exception as e:
        result["action"] = "ERROR"
        result["risk_notes"].append(f"錯誤: {str(e)[:80]}")
        return result
