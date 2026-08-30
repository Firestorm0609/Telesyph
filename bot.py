#!/usr/bin/env python3
"""
Telesyph — Telegram Memecoin Trading Bot

Users can:
- Create wallets on 5 chains
- Send crypto to their wallets
- Buy/sell memecoins via DEX
- Check prices, rug check, trending tokens
- Track portfolio and trade history
"""

import sys
import json
import logging
from openai import OpenAI

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_TOKEN, MISTRAL_API_KEYS, MISTRAL_MODEL
from wallet_manager import (
    create_wallet, get_wallets, get_wallet, get_address,
    get_all_addresses, get_supported_chains_text, SUPPORTED_CHAINS,
)
from trading_engine import (
    jupiter_quote, jupiter_swap, get_token_price,
    get_trending_solana, get_trending_ethereum, rug_check,
)
from portfolio import (
    add_position, remove_position, get_positions,
    get_portfolio_summary, get_trade_history,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = open("system_prompt.txt").read()


# ============================================================
# Mistral Key Rotator
# ============================================================

class KeyRotator:
    def __init__(self, keys):
        self.keys = keys
        self.current = 0

    def get_client(self):
        if not self.keys:
            return None
        return OpenAI(
            api_key=self.keys[self.current],
            base_url="https://api.mistral.ai/v1",
            max_retries=0,
            timeout=15.0,
        )

    def rotate(self):
        if len(self.keys) > 1:
            old = self.current
            self.current = (self.current + 1) % len(self.keys)
            logger.info(f"Rotated key: {old} -> {self.current}")

    def mark_error(self):
        self.rotate()


# ============================================================
# Tool Definitions
# ============================================================

TOOLS = [
    {"type": "function", "function": {"name": "create_wallet", "description": "Create a wallet for user on a chain. Chains: solana, ethereum, base, bsc, robinhood", "parameters": {"type": "object", "properties": {"chain": {"type": "string"}}, "required": ["chain"]}}},
    {"type": "function", "function": {"name": "get_wallets", "description": "Get all user wallets and addresses", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_wallet_address", "description": "Get deposit address for a specific chain", "parameters": {"type": "object", "properties": {"chain": {"type": "string"}}, "required": ["chain"]}}},
    {"type": "function", "function": {"name": "get_supported_chains", "description": "List all supported blockchains", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_token_price", "description": "Get token price, volume, liquidity, 24h change. Give token contract address.", "parameters": {"type": "object", "properties": {"token_address": {"type": "string"}, "chain": {"type": "string"}}, "required": ["token_address"]}}},
    {"type": "function", "function": {"name": "get_trending", "description": "Get trending tokens on a chain. Chain: solana or ethereum", "parameters": {"type": "object", "properties": {"chain": {"type": "string"}}, "required": ["chain"]}}},
    {"type": "function", "function": {"name": "rug_check", "description": "Analyze token safety — checks liquidity, volume, volatility. Give token contract address.", "parameters": {"type": "object", "properties": {"token_address": {"type": "string"}, "chain": {"type": "string"}}, "required": ["token_address"]}}},
    {"type": "function", "function": {"name": "get_swap_quote", "description": "Get a swap quote. For Solana: give input_mint and output_mint addresses. For EVM: give token_in and token_out addresses.", "parameters": {"type": "object", "properties": {"input_token": {"type": "string"}, "output_token": {"type": "string"}, "amount": {"type": "number"}, "chain": {"type": "string"}}, "required": ["input_token", "output_token", "amount", "chain"]}}},
    {"type": "function", "function": {"name": "get_portfolio", "description": "Show user's portfolio and holdings", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_trade_history", "description": "Show recent trades", "parameters": {"type": "object", "properties": {"n": {"type": "number"}}}}},
    {"type": "function", "function": {"name": "record_buy", "description": "Record a buy trade in portfolio. Call AFTER executing a swap.", "parameters": {"type": "object", "properties": {"chain": {"type": "string"}, "symbol": {"type": "string"}, "amount": {"type": "number"}, "price_usd": {"type": "number"}, "token_address": {"type": "string"}}, "required": ["chain", "symbol", "amount", "price_usd"]}}},
    {"type": "function", "function": {"name": "record_sell", "description": "Record a sell trade in portfolio. Call AFTER executing a swap.", "parameters": {"type": "object", "properties": {"chain": {"type": "string"}, "symbol": {"type": "string"}, "amount": {"type": "number"}, "price_usd": {"type": "number"}}, "required": ["chain", "symbol", "amount", "price_usd"]}}},
    {"type": "function", "function": {"name": "search_token", "description": "Search for a token by name or symbol to find its contract address", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
]


# ============================================================
# Tool Execution (all synchronous)
# ============================================================

def execute_tool(name, args, user_id):
    if name == "create_wallet":
        chain = args.get("chain", "solana").lower()
        result = create_wallet(user_id, chain)
        if result["status"] == "created":
            wallet = result["wallet"]
            return (
                f"{SUPPORTED_CHAINS[chain]['name']} wallet created!\n\n"
                f"Address: {wallet['address']}\n\n"
                f"Send {SUPPORTED_CHAINS[chain]['symbol']} to this address to start trading."
            )
        else:
            return f"You already have a {chain} wallet: {result['wallet']['address']}"

    elif name == "get_wallets":
        wallets = get_wallets(user_id)
        if not wallets:
            return "No wallets yet. Say 'create wallet solana' to get started!"
        lines = ["Your wallets:\n"]
        for chain, w in wallets.items():
            info = SUPPORTED_CHAINS.get(chain, {})
            lines.append(f"  {info.get('name', chain)} ({chain})")
            lines.append(f"    {w['address']}\n")
        return "\n".join(lines)

    elif name == "get_wallet_address":
        chain = args.get("chain", "solana").lower()
        addr = get_address(user_id, chain)
        if addr:
            return f"{SUPPORTED_CHAINS[chain]['name']} deposit address:\n{addr}\n\nSend {SUPPORTED_CHAINS[chain]['symbol']} here to trade."
        return f"No {chain} wallet. Say 'create wallet {chain}' first."

    elif name == "get_supported_chains":
        return get_supported_chains_text()

    elif name == "get_token_price":
        token_address = args.get("token_address", "")
        chain = args.get("chain", "solana")
        result = get_token_price(token_address, chain)
        if "error" in result:
            return f"Token not found: {result['error']}"
        change = float(result.get("change_24h", "0"))
        emoji = "+" if change >= 0 else ""
        return (
            f"{result['name']} ({result['symbol']})\n"
            f"Price: ${result['price_usd']}\n"
            f"24h: {emoji}{change}%\n"
            f"Volume: ${result['volume_24h']:,.0f}\n"
            f"Liquidity: ${result['liquidity']:,.0f}\n"
            f"DEX: {result['dex']}\n"
            f"Chain: {result['chain']}"
        )

    elif name == "get_trending":
        chain = args.get("chain", "solana").lower()
        if chain == "solana":
            tokens = get_trending_solana()
        else:
            tokens = get_trending_ethereum()
        if not tokens:
            return "No trending tokens found."
        lines = [f"Trending on {chain}:\n"]
        for i, t in enumerate(tokens[:10], 1):
            change = float(t.get("change_24h", "0"))
            emoji = "+" if change >= 0 else ""
            lines.append(f"  {i}. {t['symbol']} — ${t['price']} ({emoji}{change}%)")
            lines.append(f"     Vol: ${t['volume']:,.0f} | {t['address'][:20]}...")
        return "\n".join(lines)

    elif name == "rug_check":
        token_address = args.get("token_address", "")
        chain = args.get("chain", "solana")
        result = rug_check(token_address, chain)
        if result["risk"] == "unknown":
            return f"Rug check: {result['message']}"
        risk_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}
        lines = [
            f"Rug Check: {result['name']} ({result['symbol']})\n",
            f"Risk: {risk_emoji.get(result['risk'], '⚪')} {result['risk']} ({result['score']}/100)",
            f"Price: ${result['price']}",
            f"Liquidity: ${result['liquidity']:,.0f}",
            f"Volume 24h: ${result['volume_24h']:,.0f}",
        ]
        if result["warnings"]:
            lines.append("\nWarnings:")
            for w in result["warnings"]:
                lines.append(f"  ⚠️ {w}")
        return "\n".join(lines)

    elif name == "get_swap_quote":
        input_token = args.get("input_token", "")
        output_token = args.get("output_token", "")
        amount = args.get("amount", 0)
        chain = args.get("chain", "solana")
        amount_lamports = int(amount * 1e9) if chain == "solana" else int(amount * 1e18)
        if chain == "solana":
            quote = jupiter_quote(input_token, output_token, amount_lamports)
        else:
            quote = uniswap_quote(input_token, output_token, amount_lamports, chain)
        if "error" in quote:
            return f"Quote failed: {quote['error']}"
        if "outAmount" in quote:
            out_amount = int(quote["outAmount"]) / 1e6
            return (
                f"Swap Quote ({chain}):\n"
                f"  Input: {amount} tokens\n"
                f"  Output: ~{out_amount:.2f} tokens\n"
                f"  Price impact: {quote.get('priceImpactPct', '0')}%"
            )
        return json.dumps(quote)[:500]

    elif name == "get_portfolio":
        return get_portfolio_summary(user_id)

    elif name == "get_trade_history":
        n = int(args.get("n", 10))
        return get_trade_history(user_id, n)

    elif name == "record_buy":
        add_position(
            user_id,
            args.get("chain", "solana"),
            args.get("symbol", "???"),
            float(args.get("amount", 0)),
            float(args.get("price_usd", 0)),
            args.get("token_address", ""),
        )
        return "Trade recorded in portfolio."

    elif name == "record_sell":
        remove_position(
            user_id,
            args.get("chain", "solana"),
            args.get("symbol", "???"),
            float(args.get("amount", 0)),
            float(args.get("price_usd", 0)),
        )
        return "Trade recorded in portfolio."

    elif name == "search_token":
        query = args.get("query", "")
        import httpx
        url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
        with httpx.Client(timeout=10) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])[:5]
            else:
                pairs = []
        if not pairs:
            return f"No tokens found for '{query}'"
        lines = [f"Search results for '{query}':\n"]
        for p in pairs:
            base = p.get("baseToken", {})
            change = float(p.get("priceChange", {}).get("h24", "0"))
            emoji = "+" if change >= 0 else ""
            lines.append(
                f"  {base.get('symbol', '?')} ({base.get('name', '?')})\n"
                f"    Chain: {p.get('chainId', '?')}\n"
                f"    Price: ${p.get('priceUsd', '0')}\n"
                f"    24h: {emoji}{change}%\n"
                f"    Address: {base.get('address', '?')[:30]}..."
            )
        return "\n".join(lines)

    return f"Unknown tool: {name}"


# ============================================================
# Trading Agent
# ============================================================

class TelesyphAgent:
    def __init__(self):
        self.rotator = KeyRotator(MISTRAL_API_KEYS)
        self.user_histories = {}

    def _get_history(self, user_id):
        if user_id not in self.user_histories:
            self.user_histories[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        history = self.user_histories[user_id]
        if len(history) > 12:
            system = history[0]
            kept = history[-10:]
            dropped = history[1:-10]
            topics = []
            for msg in dropped:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if content:
                        first = content.split(".")[0].split("?")[0].strip()[:60]
                        if first:
                            topics.append(first)
            summary = " then ".join(topics[-3:]) if topics else ""
            history.clear()
            history.append(system)
            if summary:
                history.append({"role": "user", "content": f"[Context: {summary}]"})
            history.extend(kept)
        return history

    def handle_message(self, user_id, message):
        history = self._get_history(user_id)
        history.append({"role": "user", "content": message})

        for attempt in range(3):
            try:
                client = self.rotator.get_client()
                if not client:
                    return "No API keys available"

                response = client.chat.completions.create(
                    model=MISTRAL_MODEL,
                    messages=history,
                    tools=TOOLS,
                    tool_choice="auto",
                    max_tokens=2000,
                    temperature=0.7,
                    timeout=15.0,
                )

                for step in range(30):
                    msg = response.choices[0].message
                    if not msg.tool_calls:
                        history.append({"role": "assistant", "content": msg.content or ""})
                        return msg.content or "(No response)"

                    tool_calls_data = []
                    for tc in msg.tool_calls:
                        args = tc.function.arguments
                        if len(args) > 500:
                            args = args[:500]
                        tool_calls_data.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": args}
                        })

                    history.append({
                        "role": "assistant",
                        "content": (msg.content or "")[:500],
                        "tool_calls": tool_calls_data,
                    })

                    for tc in msg.tool_calls:
                        tool_name = tc.function.name
                        try:
                            tool_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                        except json.JSONDecodeError:
                            tool_args = {}

                        result = execute_tool(tool_name, tool_args, user_id)
                        if len(result) > 1000:
                            result = result[:1000] + "... (truncated)"
                        history.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })

                    try:
                        response = client.chat.completions.create(
                            model=MISTRAL_MODEL,
                            messages=history,
                            tools=TOOLS,
                            tool_choice="auto",
                            max_tokens=2000,
                            temperature=0.7,
                            timeout=15.0,
                        )
                    except Exception as e:
                        logger.warning(f"LLM call failed: {e}")
                        self.rotator.mark_error()
                        break

                return "(Max steps reached)"

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                self.rotator.mark_error()
                continue

        return "(All attempts failed)"


# ============================================================
# Telegram Bot
# ============================================================

agent = TelesyphAgent()


async def cmd_start(update, context):
    user_id = update.effective_user.id
    result = create_wallet(user_id, "solana")
    wallet = result["wallet"]
    addr = wallet["address"]
    await update.message.reply_text(
        f"Welcome to Telesyph!\n\n"
        f"Your Solana wallet is ready:\n{addr}\n\n"
        f"Send SOL here to start trading memecoins.\n\n"
        f"Commands:\n"
        f"/wallets — All your wallet addresses\n"
        f"/portfolio — Your holdings\n"
        f"/trending — Hot tokens\n"
        f"/help — All commands\n\n"
        f"Or just chat: buy WIF, sell SOL, rug check [address]"
    )


async def cmd_wallets(update, context):
    user_id = update.effective_user.id
    wallets = get_wallets(user_id)
    if not wallets:
        await update.message.reply_text("No wallets yet. Say 'create wallet ethereum' to add one.")
        return
    lines = ["Your wallets:\n"]
    for chain, w in wallets.items():
        info = SUPPORTED_CHAINS.get(chain, {})
        lines.append(f"{info.get('name', chain)}:")
        lines.append(f"  {w['address']}\n")
    await update.message.reply_text("\n".join(lines))


async def cmd_portfolio(update, context):
    await update.message.reply_text(get_portfolio_summary(update.effective_user.id))


async def cmd_trending(update, context):
    chain = context.args[0] if context.args else "solana"
    if chain == "solana":
        tokens = get_trending_solana()
    else:
        tokens = get_trending_ethereum()
    if not tokens:
        await update.message.reply_text("No trending tokens found.")
        return
    lines = [f"Trending on {chain}:\n"]
    for i, t in enumerate(tokens[:10], 1):
        change = float(t.get("change_24h", "0"))
        emoji = "+" if change >= 0 else ""
        lines.append(f"{i}. {t['symbol']} — ${t['price']} ({emoji}{change}%)")
    await update.message.reply_text("\n".join(lines))


async def cmd_trades(update, context):
    n = int(context.args[0]) if context.args else 10
    await update.message.reply_text(get_trade_history(update.effective_user.id, n))


async def cmd_help(update, context):
    await update.message.reply_text(
        "Telesyph Commands:\n\n"
        "/start — Create wallet & welcome\n"
        "/wallets — All wallet addresses\n"
        "/portfolio — Your holdings\n"
        "/trending [chain] — Hot tokens (solana/ethereum)\n"
        "/trades [n] — Trade history\n"
        "/help — This message\n\n"
        "Or just chat naturally:\n"
        "buy 0.5 SOL of WIF\n"
        "sell all PEPE\n"
        "price [token address]\n"
        "rug check [token address]\n"
        "create wallet ethereum\n"
        "what's trending on solana?"
    )


async def handle_message(update, context):
    user_id = update.effective_user.id
    message = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        response = agent.handle_message(user_id, message)
    except Exception as e:
        logger.error(f"Error: {e}")
        response = f"Error: {str(e)}"
    if len(response) > 4000:
        response = response[:4000] + "\n\n... (truncated)"
    await update.message.reply_text(response)


async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Create wallet & welcome"),
        BotCommand("wallets", "All wallet addresses"),
        BotCommand("portfolio", "Your holdings"),
        BotCommand("trending", "Hot tokens"),
        BotCommand("trades", "Trade history"),
        BotCommand("help", "All commands"),
    ])


def main():
    if not TELEGRAM_TOKEN:
        print("ERROR: Set TELEGRAM_TOKEN in .env")
        sys.exit(1)
    if not MISTRAL_API_KEYS:
        print("ERROR: Set MISTRAL_API_KEYS in .env")
        sys.exit(1)
    print(f"Telesyph starting with {len(MISTRAL_API_KEYS)} Mistral keys...")
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("wallets", cmd_wallets))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("trending", cmd_trending))
    app.add_handler(CommandHandler("trades", cmd_trades))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Telesyph is live!")
    app.run_polling()


if __name__ == "__main__":
    main()
