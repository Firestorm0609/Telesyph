"""
TelePay Trading Engine

Multi-chain DEX integration:
- Jupiter (Solana) — best aggregator
- Uniswap (Ethereum, Base)
- PancakeSwap (BSC)

Handles: quote, swap, price check, token info
"""

import json
import httpx
from typing import Optional

from config import JUPITER_API, DEXSCREENER_API, COINGECKO_API


# ============================================================
# Jupiter (Solana)
# ============================================================

async def jupiter_quote(input_mint: str, output_mint: str, amount: int, slippage: int = 1) -> dict:
    """Get a swap quote from Jupiter."""
    url = f"{JUPITER_API}/quote"
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": slippage * 100,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text}


async def jupiter_swap(quote: dict, user_public_key: str) -> dict:
    """Build a swap transaction from Jupiter quote."""
    url = f"{JUPITER_API}/swap"
    payload = {
        "quoteResponse": quote,
        "userPublicKey": user_public_key,
        "wrapAndUnwrapSol": True,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text}


# ============================================================
# Uniswap (Ethereum, Base, BSC via universal router)
# ============================================================

async def uniswap_quote(token_in: str, token_out: str, amount: int, chain: str = "ethereum") -> dict:
    """Get quote from Uniswap (via 0x API as aggregator)."""
    # Use 0x API for quotes across chains
    chain_ids = {"ethereum": 1, "base": 8453, "bsc": 56}
    chain_id = chain_ids.get(chain, 1)

    url = f"https://api.0x.org/swap/permit2/quote"
    params = {
        "chainId": chain_id,
        "sellToken": token_in,
        "buyToken": token_out,
        "sellAmount": str(amount),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text}


# ============================================================
# Token Price (multi-chain via DexScreener)
# ============================================================

async def get_token_price(token_address: str, chain: str = "solana") -> dict:
    """Get token price from DexScreener."""
    # Map chain names to DexScreener chain IDs
    chain_map = {
        "solana": "solana",
        "ethereum": "ethereum",
        "base": "base",
        "bsc": "bsc",
        "robinhood": "solana",  # Robinhood Chain tokens on Solana
    }
    dex_chain = chain_map.get(chain, "solana")

    url = f"{DEXSCREENER_API}/tokens/{token_address}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            pairs = data.get("pairs", [])
            if pairs:
                pair = pairs[0]
                return {
                    "name": pair.get("baseToken", {}).get("name", "Unknown"),
                    "symbol": pair.get("baseToken", {}).get("symbol", "???"),
                    "price_usd": pair.get("priceUsd", "0"),
                    "price_native": pair.get("priceNative", "0"),
                    "change_24h": pair.get("priceChange", {}).get("h24", "0"),
                    "volume_24h": pair.get("volume", {}).get("h24", 0),
                    "liquidity": pair.get("liquidity", {}).get("usd", 0),
                    "pair_address": pair.get("pairAddress", ""),
                    "dex": pair.get("dexId", ""),
                    "chain": pair.get("chainId", dex_chain),
                }
        return {"error": "Token not found"}


# ============================================================
# Trending Tokens
# ============================================================

async def get_trending_solana() -> list:
    """Get trending tokens on Solana from DexScreener."""
    # Search for memecoins specifically
    url = f"{DEXSCREENER_API}/search?q=memecoin&chainId=solana"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            pairs = data.get("pairs", [])[:15]
            # Filter out wrapped SOL and stablecoins
            skip = {"So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}
            seen = set()
            result = []
            for p in pairs:
                addr = p.get("baseToken", {}).get("address", "")
                if addr in skip or addr in seen:
                    continue
                seen.add(addr)
                result.append({
                    "name": p.get("baseToken", {}).get("name", "?"),
                    "symbol": p.get("baseToken", {}).get("symbol", "?"),
                    "price": p.get("priceUsd", "0"),
                    "change_24h": p.get("priceChange", {}).get("h24", "0"),
                    "volume": p.get("volume", {}).get("h24", 0),
                    "address": addr,
                    "chain": p.get("chainId", "solana"),
                })
                if len(result) >= 10:
                    break
            return result
    return []


async def get_trending_ethereum() -> list:
    """Get trending tokens on Ethereum from DexScreener."""
    url = f"{DEXSCREENER_API}/search?q=memecoin&chainId=ethereum"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "ethereum"][:15]
            # Skip WETH and USDC
            skip = {"0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"}
            seen = set()
            result = []
            for p in pairs:
                addr = p.get("baseToken", {}).get("address", "")
                if addr in skip or addr in seen:
                    continue
                seen.add(addr)
                result.append({
                    "name": p.get("baseToken", {}).get("name", "?"),
                    "symbol": p.get("baseToken", {}).get("symbol", "?"),
                    "price": p.get("priceUsd", "0"),
                    "change_24h": p.get("priceChange", {}).get("h24", "0"),
                    "volume": p.get("volume", {}).get("h24", 0),
                    "address": addr,
                })
                if len(result) >= 10:
                    break
            return result
    return []


# ============================================================
# Rug Check (basic)
# ============================================================

async def rug_check(token_address: str, chain: str = "solana") -> dict:
    """Basic rug check using DexScreener data."""
    price_data = await get_token_price(token_address, chain)

    if "error" in price_data:
        return {"risk": "unknown", "message": "Token not found on any DEX"}

    risk_score = 0
    warnings = []

    # Liquidity check
    liq = price_data.get("liquidity", 0)
    if liq < 1000:
        risk_score += 40
        warnings.append("Very low liquidity (<$1k)")
    elif liq < 10000:
        risk_score += 20
        warnings.append("Low liquidity (<$10k)")
    elif liq < 100000:
        risk_score += 10
        warnings.append("Moderate liquidity (<$100k)")

    # Volume check
    vol = price_data.get("volume_24h", 0)
    if vol < 100:
        risk_score += 30
        warnings.append("Almost no trading volume")
    elif vol < 1000:
        risk_score += 15
        warnings.append("Low volume (<$1k/day)")

    # Price change check
    change = abs(float(price_data.get("change_24h", "0")))
    if change > 50:
        risk_score += 20
        warnings.append(f"Extreme volatility ({change:.0f}% 24h)")

    # Determine risk level
    if risk_score >= 60:
        risk = "HIGH"
    elif risk_score >= 30:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "risk": risk,
        "score": risk_score,
        "warnings": warnings,
        "name": price_data.get("name", "?"),
        "symbol": price_data.get("symbol", "?"),
        "price": price_data.get("price_usd", "0"),
        "liquidity": liq,
        "volume_24h": vol,
    }
