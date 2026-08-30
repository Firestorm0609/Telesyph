"""
Telesyph Portfolio Manager

Tracks user holdings per chain.
All balances tracked in USD + native token amounts.
"""

import json
from pathlib import Path
from datetime import datetime

from config import PORTFOLIOS_DIR


def _portfolio_file(user_id: int) -> Path:
    return PORTFOLIOS_DIR / f"{user_id}.json"


def _load(user_id: int) -> dict:
    f = _portfolio_file(user_id)
    if f.exists():
        return json.loads(f.read_text())
    return {"user_id": user_id, "positions": {}, "trades": [], "created_at": datetime.now().isoformat()}


def _save(user_id: int, data: dict):
    _portfolio_file(user_id).write_text(json.dumps(data, indent=2))


def add_position(user_id: int, chain: str, symbol: str, amount: float, price_usd: float, token_address: str = ""):
    """Add or update a position."""
    data = _load(user_id)
    key = f"{chain}:{symbol.upper()}"
    if key in data["positions"]:
        pos = data["positions"][key]
        # Average up/down
        old_value = pos["amount"] * pos["avg_price"]
        new_value = amount * price_usd
        total_amount = pos["amount"] + amount
        pos["amount"] = total_amount
        pos["avg_price"] = (old_value + new_value) / total_amount if total_amount > 0 else 0
        pos["current_price"] = price_usd
    else:
        data["positions"][key] = {
            "chain": chain,
            "symbol": symbol.upper(),
            "amount": amount,
            "avg_price": price_usd,
            "current_price": price_usd,
            "token_address": token_address,
            "added_at": datetime.now().isoformat(),
        }

    # Record trade
    data["trades"].append({
        "type": "BUY",
        "chain": chain,
        "symbol": symbol.upper(),
        "amount": amount,
        "price_usd": price_usd,
        "total_usd": amount * price_usd,
        "timestamp": datetime.now().isoformat(),
    })
    # Keep last 100 trades
    data["trades"] = data["trades"][-100:]
    _save(user_id, data)


def remove_position(user_id: int, chain: str, symbol: str, amount: float, price_usd: float):
    """Remove from a position (sell)."""
    data = _load(user_id)
    key = f"{chain}:{symbol.upper()}"
    if key not in data["positions"]:
        return {"error": f"No {symbol.upper()} position on {chain}"}

    pos = data["positions"][key]
    if amount >= pos["amount"]:
        del data["positions"][key]
    else:
        pos["amount"] -= amount

    # Record trade
    data["trades"].append({
        "type": "SELL",
        "chain": chain,
        "symbol": symbol.upper(),
        "amount": amount,
        "price_usd": price_usd,
        "total_usd": amount * price_usd,
        "timestamp": datetime.now().isoformat(),
    })
    data["trades"] = data["trades"][-100:]
    _save(user_id, data)
    return {"status": "sold"}


def get_positions(user_id: int) -> dict:
    """Get all positions for a user."""
    data = _load(user_id)
    return data.get("positions", {})


def get_portfolio_summary(user_id: int) -> str:
    """Human-readable portfolio summary."""
    data = _load(user_id)
    positions = data.get("positions", {})
    trades = data.get("trades", [])

    if not positions:
        return "No positions yet. Send crypto to your wallet to start trading!"

    total_value = 0
    lines = ["Portfolio:\n"]
    for key, pos in positions.items():
        value = pos["amount"] * pos["current_price"]
        pnl = (pos["current_price"] - pos["avg_price"]) * pos["amount"]
        pnl_pct = ((pos["current_price"] / pos["avg_price"]) - 1) * 100 if pos["avg_price"] > 0 else 0
        emoji = "+" if pnl >= 0 else ""
        lines.append(
            f"  {pos['symbol']} ({pos['chain']})\n"
            f"    {pos['amount']:.6f} x ${pos['current_price']:.6f} = ${value:.2f}\n"
            f"    PnL: {emoji}${pnl:.2f} ({emoji}{pnl_pct:.1f}%)"
        )
        total_value += value

    lines.append(f"\nTotal value: ${total_value:.2f}")
    lines.append(f"Total trades: {len(trades)}")
    return "\n".join(lines)


def get_trade_history(user_id: int, n: int = 10) -> str:
    """Show recent trades."""
    data = _load(user_id)
    trades = data.get("trades", [])[-n:]

    if not trades:
        return "No trades yet."

    lines = ["Recent trades:\n"]
    for t in reversed(trades):
        emoji = "+" if t["type"] == "BUY" else "-"
        lines.append(
            f"  {emoji} {t['type']} {t['amount']:.6f} {t['symbol']} "
            f"@ ${t['price_usd']:.6f} = ${t['total_usd']:.2f} ({t['chain']})"
        )
    return "\n".join(lines)
