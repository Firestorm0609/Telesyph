"""
TelePay Configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Paths
# ============================================================
BASE_DIR = Path(__file__).parent
WALLETS_DIR = BASE_DIR / "user_data" / "wallets"
PORTFOLIOS_DIR = BASE_DIR / "user_data" / "portfolios"
WALLETS_DIR.mkdir(parents=True, exist_ok=True)
PORTFOLIOS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# Telegram
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

# ============================================================
# AI Provider (Mistral)
# ============================================================
MISTRAL_API_KEYS = [k.strip() for k in os.getenv("MISTRAL_API_KEYS", "").split(",") if k.strip()]
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")

# ============================================================
# RPC Endpoints
# ============================================================
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
ETH_RPC = os.getenv("ETH_RPC", "https://eth.llamarpc.com")
BASE_RPC = os.getenv("BASE_RPC", "https://mainnet.base.org")
BSC_RPC = os.getenv("BSC_RPC", "https://bsc-dataseed.binance.org")

# ============================================================
# DEX APIs
# ============================================================
JUPITER_API = "https://quote-api.jup.ag/v6"
UNISWAP_API = "https://gateway.thegraph.com"

# ============================================================
# Scanner APIs (free, no key needed)
# ============================================================
COINGECKO_API = "https://api.coingecko.com/api/v3"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"
BIRDEYE_API = "https://public-api.birdeye.so"
