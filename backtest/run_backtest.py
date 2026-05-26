"""
回测脚本 — 拉取过去 14 天历史数据，逐日运行 AI Signal 评分，对比实际价格走势
"""
import asyncio
import json
import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 添加父目录到 path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from sources.coingecko import get_coin_history
from sources.defillama import (
    get_perp_volume_history, get_funding_rate,
    get_open_interest, get_stablecoin_summary,
)
from sources.binance import get_oi_history
from engine.signal import score_signals


TRACKED_COINS   = ["bitcoin", "ethereum", "solana"]
TRACKED_PERPS   = ["hyperliquid", "gmx", "dydx"]
BACKTEST_DAYS   = 14
OUTPUT_DIR      = Path(__file__).parent / "results"


async def fetch_historical_data() -> dict:
    """拉取所有历史数据"""
    print("Fetching historical data...")

    # 并行拉取
    results = await asyncio.gather(
        *[get_coin_history(coin, days=BACKTEST_DAYS+2) for coin in TRACKED_COINS],
        *[get_perp_volume_history(slug, days=BACKTEST_DAYS+2) for slug in TRACKED_PERPS],
        *[get_funding_rate(slug) for slug in TRACKED_PERPS],
        return_exceptions=True,
    )

    n_coins = len(TRACKED_COINS)
    n_perps = len(TRACKED_PERPS)

    coin_histories  = {TRACKED_COINS[i]: results[i]
                       for i in range(n_coins) if not isinstance(results[i], Exception)}
    perp_volumes    = {TRACKED_PERPS[i]: results[n_coins + i]
                       for i in range(n_perps) if not isinstance(results[n_coins + i], Exception)}
    funding_history = {TRACKED_PERPS[i]: results[n_coins + n_perps + i]
                       for i in range(n_perps) if not isinstance(results[n_coins + n_perps + i], Exception)}

    print(f"  Coin histories: {list(coin_histories.keys())}")
    print(f"  Perp volumes:   {list(perp_volumes.keys())}")
    return {
        "coin_histories": coin_histories,
        "perp_volumes":   perp_volumes,
        "funding":        funding_history,
    }


def build_daily_snapshot(data: dict, target_date: str) -> dict:
    """
    从历史数据中提取某一天的快照，模拟当天的信号输入。
    """
    # BTC 24h change
    btc_history = data["coin_histories"].get("bitcoin", [])
    btc_change  = 0.0
    for i, d in enumerate(btc_history):
        if d["date"] == target_date and i > 0:
            prev_price = btc_history[i-1]["price"]
            curr_price = d["price"]
            if prev_price:
                btc_change = (curr_price - prev_price) / prev_price
            break

    # 构造模拟 price_anomalies
    price_anomalies = []
    if abs(btc_change) > 0.05:
        price_anomalies.append({
            "symbol": "BTC",
            "change": btc_change * 100,
            "tags": [f"BTC {btc_change*100:+.1f}% 24h"],
        })

    # 构造模拟 funding_anomalies（简化：用历史 funding 数据）
    funding_anomalies = []
    for slug, fr_data in data["funding"].items():
        for fr_entry in fr_data:
            if isinstance(fr_entry, dict):
                date_field = fr_entry.get("date", "") or fr_entry.get("timestamp", "")
                if target_date in str(date_field):
                    rate = float(fr_entry.get("fundingRate", 0) or 0)
                    if abs(rate) > 0.0001:
                        funding_anomalies.append({
                            "symbol": slug.upper(),
                            "fr": rate,
                            "tags": [f"FR {rate*100:.4f}%"],
                            "severity": "medium",
                        })

    # DEX volumes (简化)
    dex_volumes = []
    for slug, vol_data in data["perp_volumes"].items():
        for v in vol_data:
            if v.get("date") == target_date:
                dex_volumes.append({
                    "name": slug,
                    "vol_24h": v.get("volume", 0),
                    "avg_7d": v.get("volume", 0),  # 简化：不计算 7d avg
                    "ratio": 1.0,
                    "tags": [],
                })

    return {
        "date": target_date,
        "btc_change": btc_change,
        "price_anomalies": price_anomalies,
        "funding_anomalies": funding_anomalies,
        "dex_volumes": dex_volumes,
    }


def get_next_day_return(coin_history: list[dict], target_date: str) -> float:
    """获取下一个交易日的实际收益率（用于验证信号）"""
    for i, d in enumerate(coin_history):
        if d["date"] == target_date and i + 1 < len(coin_history):
            curr = d["price"]
            nxt  = coin_history[i+1]["price"]
            if curr:
                return (nxt - curr) / curr
    return 0.0


async def run_backtest():
    """运行完整回测"""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 拉取历史数据（一次性）
    data        = await fetch_historical_data()
    btc_history = data["coin_histories"].get("bitcoin", [])

    if not btc_history:
        print("ERROR: Could not fetch Bitcoin history. Aborting.")
        return

    # 生成目标日期列表
    today     = datetime.now(tz=timezone.utc).date()
    dates     = []
    for i in range(BACKTEST_DAYS, 0, -1):
        d = today - timedelta(days=i)
        dates.append(d.strftime("%Y-%m-%d"))

    print(f"\nRunning backtest for {len(dates)} days: {dates[0]} → {dates[-1]}\n")

    # 获取稳定币快照（简化：用当前值）
    try:
        stablecoin = await get_stablecoin_summary()
    except Exception:
        stablecoin = {"total_mcap": 0, "change_7d": 0, "coins": []}

    rows = []
    correct_count = 0

    for date_str in dates:
        snapshot = build_daily_snapshot(data, date_str)

        # 运行信号评分
        signal = score_signals(
            funding_anomalies=snapshot["funding_anomalies"],
            price_anomalies=snapshot["price_anomalies"],
            stablecoin=stablecoin,
            dex_volumes=snapshot["dex_volumes"],
            kol_sentiment="neutral",   # 回测中无 KOL 数据
        )

        # 获取下一日实际涨跌
        next_day_return = get_next_day_return(btc_history, date_str)

        # 判断信号是否正确
        if signal["bullish"] > signal["bearish"] and next_day_return > 0:
            correct = True
        elif signal["bearish"] > signal["bullish"] and next_day_return < 0:
            correct = True
        elif signal["bullish"] == signal["bearish"]:
            correct = None  # Neutral — 跳过
        else:
            correct = False

        if correct is not None:
            if correct:
                correct_count += 1
            rows.append({
                "date":           date_str,
                "signal":         "bullish" if signal["bullish"] > signal["bearish"] else "bearish",
                "bullish_count":  signal["bullish"],
                "bearish_count":  signal["bearish"],
                "neutral_count":  signal["neutral"],
                "next_day_btc":   f"{next_day_return*100:.2f}%",
                "correct":        "✅" if correct else "❌",
                "reasons":        "; ".join(
                    signal["reasons"]["bullish"] + signal["reasons"]["bearish"]
                )[:100],
            })

            status = "✅" if correct else "❌"
            print(f"  {date_str}: {signal['bullish']}B/{signal['bearish']}Be | "
                  f"BTC next day {next_day_return*100:+.2f}% {status}")

    # ── 输出报告 ─────────────────────────────────────────────────────────────
    total_scored = len([r for r in rows if r["correct"] in ("✅", "❌")])
    accuracy     = correct_count / total_scored * 100 if total_scored else 0

    print(f"\n{'='*50}")
    print(f"BACKTEST RESULTS ({dates[0]} → {dates[-1]})")
    print(f"{'='*50}")
    print(f"Total scored days: {total_scored}")
    print(f"Correct signals:   {correct_count}")
    print(f"Accuracy:          {accuracy:.1f}%")
    print(f"(Note: Neutral days excluded from accuracy)")

    # 保存 CSV
    csv_path = OUTPUT_DIR / f"backtest_{today.strftime('%Y%m%d')}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV saved: {csv_path}")

    # 保存 JSON
    json_path = OUTPUT_DIR / f"backtest_{today.strftime('%Y%m%d')}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "date_from": dates[0],
                "date_to":   dates[-1],
                "total_days": len(dates),
                "scored_days": total_scored,
                "correct": correct_count,
                "accuracy_pct": round(accuracy, 1),
            },
            "rows": rows,
        }, f, indent=2, ensure_ascii=False)
    print(f"JSON saved: {json_path}\n")


if __name__ == "__main__":
    asyncio.run(run_backtest())
