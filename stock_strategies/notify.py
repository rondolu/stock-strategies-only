import os
import sys
import json
from datetime import datetime

import numpy as np
import requests

from .config import CONFIG, TELEGRAM_API


def _md_escape(value: object) -> str:
    """Escape dynamic text for Telegram Markdown (legacy mode)."""
    if value is None:
        return ""
    text = str(value)
    for ch in "\\`*_[]":
        text = text.replace(ch, f"\\{ch}")
    return text


def send_telegram(text: str):
    url = TELEGRAM_API.format(token=os.environ["TELEGRAM_BOT_TOKEN"])
    payload = {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": text,
        "parse_mode": "Markdown",
    }
    r = requests.post(url, json=payload, timeout=10)
    if r.ok:
        return

    err_desc = ""
    try:
        err_desc = (r.json() or {}).get("description", "")
    except (ValueError, json.JSONDecodeError):
        err_desc = r.text

    # Telegram Markdown parsing is strict; retry once as plain text to avoid delivery loss.
    if r.status_code == 400 and "can't parse entities" in err_desc.lower():
        fallback_payload = {
            "chat_id": os.environ["TELEGRAM_CHAT_ID"],
            "text": text,
        }
        r2 = requests.post(url, json=fallback_payload, timeout=10)
        if r2.ok:
            print("Telegram Markdown 解析失敗，已改用純文字送出", file=sys.stderr)
            return
        print(f"Telegram 送失敗(純文字重試後): {r2.text}", file=sys.stderr)
        return

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


def _setup_type_label(setup_type: str | None) -> str:
    mapping = {
        "first_wave": "第一波啟動",
        "pullback": "主升段回測",
        "momentum": "續強追蹤",
    }
    return mapping.get(setup_type, "型態未分類")


def _style_setup_label(style: str | None, setup_type: str | None) -> str:
    style_text = _style_label(style)
    setup_text = _setup_type_label(setup_type)
    if style == "conservative":
        return f"🔵 {style_text}｜{setup_text}"
    if style == "aggressive":
        return f"🟠 {style_text}｜{setup_text}"
    return f"{style_text}｜{setup_text}"


def _explain_setup_type(setup_type: str | None) -> str:
    mapping = {
        "first_wave": "趨勢轉強初期，可早介入但波動較大",
        "pullback": "主升段回測，季線確立後找支撐布局",
        "momentum": "強勢延續，在相對高位追強需控管部位",
    }
    return mapping.get(setup_type, "等待更多訊號確認型態")


def _format_stock_detail(s: dict, show_trend: bool = True) -> list[str]:
    """格式化單檔股票的詳細資訊"""
    c = s.get("components", {})
    t = s.get("trend", {})
    lines = []
    wr = f"{c['backtest_winrate']*100:.0f}%" if c.get("backtest_winrate") else "N/A"
    style_text = _style_setup_label(s.get("buy_style"), s.get("setup_type"))
    stock_id = _md_escape(s.get("stock_id", ""))
    stock_name = _md_escape(s.get("name", ""))
    lines.append(
        f"*{stock_id} {stock_name}*  {style_text} | 排序 {_md_escape(s.get('sort_score', s.get('signal_score', 'N/A')))}"
    )
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
        lines.append(f"入選原因: {' / '.join(_md_escape(x) for x in reasons[:3])}")
    lines.append(f"📍 布局型態: {_setup_type_label(s.get('setup_type'))}（{_explain_setup_type(s.get('setup_type'))}）")
    if s.get("primary_risk"):
        lines.append(f"⚠️ 主要風險: {_md_escape(s['primary_risk'])}")

    lines.append(
        f"進場 {_md_escape(s['entry_price'])} → 停損 {_md_escape(s['stop_loss_price'])} / 目標 {_md_escape(s['target_price'])}"
    )
    lines.append(
        f"風報比 1:{_md_escape(s['risk_reward_ratio'])} | 建議部位 {_md_escape(s['position_size_pct'])}%"
    )
    lines.append(
        f"技術分 {_md_escape(c.get('tech_score', 'N/A'))} | 勝率 {_md_escape(wr)} ({_md_escape(c.get('backtest_samples', 0))}次) | 平均報酬 {_md_escape(c.get('avg_return', 'N/A'))}"
    )
    return lines


def _explain_buy_style(s: dict) -> str:
    reasons = s.get("buy_reason", [])
    return " / ".join(_md_escape(x) for x in reasons) if reasons else "符合該風格主條件"


def _explain_watch_gap(s: dict) -> str:
    c = s.get("components", {})
    t = s.get("trend", {})
    met = []
    gaps = []

    if c.get("fundamental_pass"):
        met.append("基本面資格")
    else:
        gaps.append("基本面資格待補強")

    if t.get("above_ma20"):
        met.append("站穩月線")
    else:
        gaps.append("尚未站穩月線")

    if t.get("above_ma60"):
        met.append("站穩季線")
    else:
        gaps.append("季線趨勢未完整")

    if t.get("chg_20d", 0) > 0:
        met.append("20日方向轉正")
    else:
        gaps.append("20日方向尚未轉正")

    if (c.get("backtest_samples") or 0) >= 5:
        met.append("回測樣本充足")
    else:
        gaps.append("回測樣本仍偏少")

    winrate = c.get("backtest_winrate")
    if winrate is not None and winrate >= 0.45:
        met.append("回測勝率達標")
    else:
        gaps.append("回測勝率仍待提升")

    met_text = " / ".join(met[:3]) if met else "尚無明確優勢"
    if not gaps:
        return f"已滿足：{met_text}｜待補強：無（條件完整）"

    gap_text = " / ".join(gaps[:3])
    return f"已滿足：{met_text}｜待補強：{gap_text}"


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
        safe_cat = _md_escape(cat)
        lines.append(
            f"{emoji} *{safe_cat}* ({total}檔) 5日均漲{avg:+.1f}% | "
            f"保守型BUY {_md_escape(d['buy_c'])} / 積極型BUY {_md_escape(d['buy_a'])} / WATCH {_md_escape(d['watch'])}"
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
    setup_candidates = [s for s in signals if s.get("action") in ("BUY", "WATCH")]
    setup_first_wave = sum(1 for s in setup_candidates if s.get("setup_type") == "first_wave")
    setup_pullback = sum(1 for s in setup_candidates if s.get("setup_type") == "pullback")
    setup_momentum = sum(1 for s in setup_candidates if s.get("setup_type") == "momentum")
    today = datetime.now().strftime("%Y/%m/%d")
    total = len(signals)
    messages = []

    # === 第一則：市場總覽 + 類股強弱 ===
    msg1 = []
    msg1.append(f"📊 *V4.0 每日選股報告* {today}")
    msg1.append(
        f"掃描 {total} 檔 | 保守型BUY {len(conservative_buys)} | 積極型BUY {len(aggressive_buys)} | WATCH {len(watches)} | SKIP {len(skips)}"
    )
    msg1.append(
        f"型態分布(BUY+WATCH)：第一波 {setup_first_wave} / 主升回測 {setup_pullback} / 續強 {setup_momentum}"
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
    msg2.append("📍 *布局型態說明*")
    msg2.append("🟢 第一波啟動：趨勢剛發動，可早介入但需控制部位")
    msg2.append("🔷 主升段回測：主升途中拉回，相對舒服的布局點")
    msg2.append("🚀 續強追蹤：已在相對高位，追強需嚴守風險")
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
                msg3.append(f"🧩 條件檢核: {_explain_watch_gap(s)}")
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
                msg4.append(f"🧩 條件檢核: {_explain_watch_gap(s)}")
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
            msg5.append(
                f"• *{_md_escape(s['stock_id'])} {_md_escape(s['name'])}*：{_explain_watch_gap(s)}"
            )
        msg5.append("")

        if rest_watches:
            msg5.append(f"📎 其他觀察 {len(rest_watches)} 檔")
            rest_line = ", ".join(
                [
                    f"{_md_escape(s['stock_id'])}{_md_escape(s['name'])}({_md_escape(s.get('sort_score', s.get('signal_score', 0)))})"
                    for s in rest_watches
                ]
            )
            msg5.append(rest_line)
            msg5.append("")

    msg5.append("📌 *操作方向*")
    sentiment = _market_sentiment(signals)
    if "偏多" in sentiment and "中性" not in sentiment:
        msg5.append("• 市場偏多，可挑選保守型BUY分批進場")
        msg5.append("• 積極型BUY在多頭行情也值得重視，可用小部位分批參與")
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
