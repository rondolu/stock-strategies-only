import os
import sys
from datetime import datetime

import numpy as np
import requests

from .config import CONFIG, TELEGRAM_API


def send_telegram(text: str):
    url = TELEGRAM_API.format(token=os.environ["TELEGRAM_BOT_TOKEN"])
    payload = {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": text,
        "parse_mode": "Markdown",
    }
    r = requests.post(url, json=payload, timeout=10)
    if not r.ok:
        print(f"Telegram 送失敗: {r.text}", file=sys.stderr)


def _trend_emoji(chg: float) -> str:
    if chg > 3:
        return "🔥"
    elif chg > 0:
        return "📈"
    elif chg > -3:
        return "📉"
    return "💥"


def _style_label(style: str | None) -> str:
    if style == "conservative":
        return "保守型BUY"
    if style == "aggressive":
        return "積極型BUY"
    return "BUY"


def _format_stock_detail(s: dict, show_trend: bool = True) -> list[str]:
    """格式化單檔股票的詳細資訊"""
    c = s.get("components", {})
    t = s.get("trend", {})
    lines = []
    wr = f"{c['backtest_winrate']*100:.0f}%" if c.get("backtest_winrate") else "N/A"
    style_text = _style_label(s.get("buy_style"))
    lines.append(f"*{s['stock_id']} {s['name']}*  {style_text} | 排序 {s.get('sort_score', s.get('signal_score', 'N/A'))}")
    if show_trend and t:
        ma_status = ""
        if t.get("above_ma20") and t.get("above_ma60"):
            ma_status = "站上月季線"
        elif t.get("above_ma20"):
            ma_status = "站上月線"
        else:
            ma_status = "月線下"
        vol_note = f"量能{'放大' if t.get('vol_ratio', 1) > 1.2 else '縮量' if t.get('vol_ratio', 1) < 0.8 else '持平'}"
        lines.append(
            f"{_trend_emoji(t.get('chg_5d', 0))} 5日{t.get('chg_5d', 0):+.1f}% | 20日{t.get('chg_20d', 0):+.1f}% | "
            f"距高點{t.get('pct_from_high', 0):.0f}% | {ma_status} | {vol_note}"
        )

    reasons = s.get("buy_reason", [])
    if reasons:
        lines.append(f"入選原因: {' / '.join(reasons[:3])}")
    if s.get("primary_risk"):
        lines.append(f"⚠️ 主要風險: {s['primary_risk']}")

    lines.append(
        f"進場 {s['entry_price']} → 停損 {s['stop_loss_price']} / 目標 {s['target_price']}"
    )
    lines.append(
        f"風報比 1:{s['risk_reward_ratio']} | 建議部位 {s['position_size_pct']}%"
    )
    lines.append(
        f"技術分 {c.get('tech_score', 'N/A')} | 勝率 {wr} ({c.get('backtest_samples', 0)}次) | 平均報酬 {c.get('avg_return', 'N/A')}"
    )
    return lines


def _explain_buy_style(s: dict) -> str:
    reasons = s.get("buy_reason", [])
    return " / ".join(reasons) if reasons else "符合該風格主條件"


def _explain_watch_gap(s: dict) -> str:
    c = s.get("components", {})
    t = s.get("trend", {})
    gaps = []
    if not c.get("fundamental_pass"):
        gaps.append("基本面資格待補強")
    if not t.get("above_ma20"):
        gaps.append("尚未站穩月線")
    if not t.get("above_ma60"):
        gaps.append("季線趨勢未完整")
    if t.get("chg_20d", 0) <= 0:
        gaps.append("20日方向尚未轉正")
    if (c.get("backtest_samples") or 0) < 5:
        gaps.append("回測樣本仍偏少")
    if c.get("backtest_winrate") is not None and c.get("backtest_winrate", 0) < 0.45:
        gaps.append("回測勝率仍待提升")
    if not gaps:
        return "條件接近完成，等待更佳位置"
    return " / ".join(gaps[:3])


def _sector_summary(signals: list[dict], watchlist: list[dict]) -> list[str]:
    """類股強弱分析"""
    cat_map = {str(w["stock_id"]): w.get("category", "其他") for w in watchlist}
    sectors = {}
    for s in signals:
        cat = cat_map.get(s["stock_id"], "其他")
        if cat not in sectors:
            sectors[cat] = {"stocks": [], "chg_5d": [], "buy_c": 0, "buy_a": 0, "watch": 0}
        sectors[cat]["stocks"].append(s)
        t = s.get("trend", {})
        if t.get("chg_5d") is not None:
            sectors[cat]["chg_5d"].append(t["chg_5d"])
        if s.get("action") == "BUY":
            if s.get("buy_style") == "conservative":
                sectors[cat]["buy_c"] += 1
            elif s.get("buy_style") == "aggressive":
                sectors[cat]["buy_a"] += 1
        elif s.get("action") == "WATCH":
            sectors[cat]["watch"] += 1

    ranked = sorted(
        sectors.items(),
        key=lambda x: np.mean(x[1]["chg_5d"]) if x[1]["chg_5d"] else 0,
        reverse=True,
    )

    lines = []
    for cat, d in ranked:
        avg = np.mean(d["chg_5d"]) if d["chg_5d"] else 0
        emoji = _trend_emoji(avg)
        total = len(d["stocks"])
        lines.append(
            f"{emoji} *{cat}* ({total}檔) 5日均漲{avg:+.1f}% | "
            f"保守型BUY {d['buy_c']} / 積極型BUY {d['buy_a']} / WATCH {d['watch']}"
        )
    return lines


def _market_sentiment(signals: list[dict]) -> str:
    """判斷市場氛圍"""
    valid = [s for s in signals if s.get("trend")]
    if not valid:
        return "無法判斷"
    up = sum(1 for s in valid if s["trend"].get("chg_5d", 0) > 0)
    above_ma20 = sum(1 for s in valid if s["trend"].get("above_ma20"))
    pct_up = up / len(valid) * 100
    pct_ma20 = above_ma20 / len(valid) * 100

    if pct_up > 70 and pct_ma20 > 60:
        return "🟢 偏多 — 多數標的上漲且站穩月線，可積極佈局"
    elif pct_up > 50:
        return "🟡 中性偏多 — 漲多跌少但力道分歧，選股不選市"
    elif pct_up > 30:
        return "🟠 中性偏空 — 多數標的走弱，保守觀望為主"
    else:
        return "🔴 偏空 — 普遍下跌，建議空手等待"


def _chunk_items(items: list[dict], chunk_size: int = 8) -> list[list[dict]]:
    if not items:
        return []
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def format_messages(signals: list[dict], watchlist: list[dict] = None) -> list[str]:
    """產生多則 Telegram 訊息"""
    buys = [s for s in signals if s.get("action") == "BUY"]
    conservative_buys = [s for s in buys if s.get("buy_style") == "conservative"]
    aggressive_buys = [s for s in buys if s.get("buy_style") == "aggressive"]
    watches = [s for s in signals if s.get("action") == "WATCH"]
    skips = [s for s in signals if s.get("action") in ("SKIP", "ERROR")]
    today = datetime.now().strftime("%Y/%m/%d")
    total = len(signals)
    messages = []

    # === 第一則：市場總覽 + 類股強弱 ===
    msg1 = []
    msg1.append(f"📊 每日選股報告* {today}")
    msg1.append(
        f"掃描 {total} 檔 | 保守型BUY {len(conservative_buys)} | 積極型BUY {len(aggressive_buys)} | WATCH {len(watches)} | SKIP {len(skips)}"
    )
    msg1.append("")

    msg1.append("🌡️ *市場氛圍*")
    msg1.append(_market_sentiment(signals))
    valid = [s for s in signals if s.get("trend")]
    if valid:
        avg_5d = np.mean([s["trend"]["chg_5d"] for s in valid])
        up_count = sum(1 for s in valid if s["trend"]["chg_5d"] > 0)
        above_ma20 = sum(1 for s in valid if s["trend"]["above_ma20"])
        msg1.append(
            f"池內均漲 {avg_5d:+.1f}% | {up_count}/{len(valid)} 檔上漲 | "
            f"{above_ma20}/{len(valid)} 檔站上月線"
        )
    msg1.append("")

    if watchlist:
        msg1.append("📡 *類股強弱排名*")
        msg1.extend(_sector_summary(signals, watchlist))
        msg1.append("")

    msg1.append("📋 *策略規則*")
    msg1.append(
        "分類以趨勢/位置/量價/回測品質為主，基本面作為資格條件\n"
        "signal_score 僅作排序參考，不直接決定 BUY/WATCH\n"
        f"停損{CONFIG['stop_loss']*100:.0f}% / 停利{CONFIG['target_return']*100:.0f}% / 持有{CONFIG['hold_days']}日"
    )
    messages.append("\n".join(msg1))

    # === 第二則：固定策略說明 ===
    msg2 = []
    msg2.append("📖 *今日策略說明*")
    msg2.append("")
    msg2.append("🔵 *保守型BUY*：趨勢較完整，重視站穩月季線與20日方向，適合分批布局")
    msg2.append("🟠 *積極型BUY*：趨勢轉強或接近突破，可提早切入，但短線波動較大")
    msg2.append("")
    msg2.append("💡 每檔都會提供：入選主因 + 最主要風險 + 進出場參考")
    messages.append("\n".join(msg2))

    # === 第三則：保守型BUY ===
    conservative_chunks = _chunk_items(conservative_buys)
    if conservative_chunks:
        for idx, chunk in enumerate(conservative_chunks, 1):
            msg3 = []
            suffix = f" #{idx}" if len(conservative_chunks) > 1 else ""
            msg3.append(f"🔵 *保守型BUY ({len(conservative_buys)})*{suffix}")
            msg3.append("趨勢較完整，適合分批布局")
            msg3.append("")
            for s in chunk:
                msg3.extend(_format_stock_detail(s))
                msg3.append(f"💡 為何歸類: {_explain_buy_style(s)}")
                msg3.append("")
            messages.append("\n".join(msg3))
    else:
        messages.append("🔵 *保守型BUY*\n今日無符合趨勢完整條件的標的")

    # === 第四則：積極型BUY ===
    aggressive_chunks = _chunk_items(aggressive_buys)
    if aggressive_chunks:
        for idx, chunk in enumerate(aggressive_chunks, 1):
            msg4 = []
            suffix = f" #{idx}" if len(aggressive_chunks) > 1 else ""
            msg4.append(f"🟠 *積極型BUY ({len(aggressive_buys)})*{suffix}")
            msg4.append("⚠️ 積極型標的短線波動較大，建議小部位或分批")
            msg4.append("")
            for s in chunk:
                msg4.extend(_format_stock_detail(s))
                msg4.append(f"💡 為何歸類: {_explain_buy_style(s)}")
                msg4.append("")
            messages.append("\n".join(msg4))
    else:
        messages.append("🟠 *積極型BUY*\n今日無符合趨勢轉強條件的標的")

    # === 第五則：WATCH + 操作建議 ===
    msg5 = []
    msg5.append("🧠 *WATCH 與今日操作建議*")
    msg5.append("")

    if watches:
        top_watches = watches[:6]
        rest_watches = watches[6:]
        msg5.append(f"🟡 *WATCH TOP {len(top_watches)}*")
        for s in top_watches:
            msg5.append(f"• *{s['stock_id']} {s['name']}*：{_explain_watch_gap(s)}")
        msg5.append("")

        if rest_watches:
            msg5.append(f"📎 其他觀察 {len(rest_watches)} 檔")
            rest_line = ", ".join(
                [f"{s['stock_id']}{s['name']}({s.get('sort_score', s.get('signal_score', 0))})" for s in rest_watches]
            )
            msg5.append(rest_line)
            msg5.append("")

    msg5.append("📌 *操作方向*")
    sentiment = _market_sentiment(signals)
    if "偏多" in sentiment and "中性" not in sentiment:
        msg5.append("• 市場偏多，可挑選保守型BUY分批進場")
        msg5.append("• 積極型BUY僅做小部位試單")
    elif "偏多" in sentiment:
        msg5.append("• 市場中性偏多，選股不選市")
        msg5.append("• 優先等回測品質較佳的標的回測支撐")
    elif "偏空" in sentiment and "中性" not in sentiment:
        msg5.append("• 市場偏空，建議空手觀望")
        msg5.append("• 僅追蹤WATCH清單，等待轉強")
    else:
        msg5.append("• 市場中性偏空，控制總部位在半倉以下")
        msg5.append("• 僅做高勝率且風險可控機會")
    msg5.append("")
    msg5.append("_以上為系統自動分析，僅供參考，投資決策請自行判斷_")
    messages.append("\n".join(msg5))

    return messages


def format_message(signals: list[dict]) -> str:
    """向後相容"""
    return format_messages(signals)[0]
