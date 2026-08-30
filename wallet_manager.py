"""
Telesyph Wallet Manager

Each user gets wallets per chain:
- Solana (SOL + SPL tokens)
- Ethereum (ETH + ERC-20)
- Base (ETH + ERC-20)
- BSC (BNB + BEP-20)
- Robinhood Chain (ETH-based)

Wallets are derived from a master seed using BIP-44.
User's Telegram ID = their identity.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime

from config import WALLETS_DIR

# ============================================================
# HD Wallet Derivation (BIP-44)
# ============================================================

def _derive_wallet(user_id: int, chain: str) -> dict:
    """Derive a deterministic wallet for a user on a chain."""
    from mnemonic import Mnemonic
    from bip44 import Wallet

    # Deterministic seed from user_id + chain
    seed_phrase = f"telesyph user {user_id} chain {chain} secure 2026"
    mnemo = Mnemonic("english")
    words = mnemo.to_mnemonic(
        hashlib.sha256(seed_phrase.encode()).digest()
    )

    wallet = Wallet(words)
    # BIP-44 paths per chain
    paths = {
        "solana": "m/44'/501'/0'/0'",
        "ethereum": "m/44'/60'/0'/0/0",
        "base": "m/44'/60'/0'/0/0",       # same as ETH (L2)
        "bsc": "m/44'/60'/0'/0/0",         # same as ETH
        "robinhood": "m/44'/60'/0'/0/0",   # same as ETH (L2)
    }
    path = paths.get(chain, "m/44'/60'/0'/0/0")

    # Get keys from path
    private_key = wallet.derive_secret_key(path=path).hex()
    public_key = wallet.derive_public_key(path=path).hex()

    # For address: use public key directly
    address = public_key

    return {
        "chain": chain,
        "address": address,
        "private_key": private_key,
        "created_at": datetime.now().isoformat(),
    }


# ============================================================
# Wallet CRUD
# ============================================================

def create_wallet(user_id: int, chain: str = "solana") -> dict:
    """Create or return existing wallet for user on chain."""
    wallet_file = WALLETS_DIR / f"{user_id}.json"

    # Load existing wallets
    wallets = {}
    if wallet_file.exists():
        wallets = json.loads(wallet_file.read_text())

    # Return existing if already created
    if chain in wallets:
        return {"status": "exists", "wallet": wallets[chain]}

    # Derive new wallet
    wallet = _derive_wallet(user_id, chain)
    wallets[chain] = wallet
    wallet_file.write_text(json.dumps(wallets, indent=2))

    return {"status": "created", "wallet": wallet}


def get_wallets(user_id: int) -> dict:
    """Get all wallets for a user."""
    wallet_file = WALLETS_DIR / f"{user_id}.json"
    if not wallet_file.exists():
        return {}
    return json.loads(wallet_file.read_text())


def get_wallet(user_id: int, chain: str) -> dict | None:
    """Get wallet for specific chain."""
    wallets = get_wallets(user_id)
    return wallets.get(chain)


def get_address(user_id: int, chain: str) -> str | None:
    """Get wallet address for chain."""
    wallet = get_wallet(user_id, chain)
    return wallet["address"] if wallet else None


def get_all_addresses(user_id: int) -> dict:
    """Get all wallet addresses for a user."""
    wallets = get_wallets(user_id)
    return {chain: w["address"] for chain, w in wallets.items()}


# ============================================================
# Supported Chains
# ============================================================

SUPPORTED_CHAINS = {
    "solana": {
        "name": "Solana",
        "symbol": "SOL",
        "explorer": "https://solscan.io",
        "rpc": "https://api.mainnet-beta.solana.com",
    },
    "ethereum": {
        "name": "Ethereum",
        "symbol": "ETH",
        "explorer": "https://etherscan.io",
        "rpc": "https://eth.llamarpc.com",
    },
    "base": {
        "name": "Base",
        "symbol": "ETH",
        "explorer": "https://basescan.org",
        "rpc": "https://mainnet.base.org",
    },
    "bsc": {
        "name": "BNB Smart Chain",
        "symbol": "BNB",
        "explorer": "https://bscscan.com",
        "rpc": "https://bsc-dataseed.binance.org",
    },
    "robinhood": {
        "name": "Robinhood Chain",
        "symbol": "ETH",
        "explorer": "https://robinhood.com/chain",
        "rpc": "https://rpc.robinhood.com",
    },
}


def get_supported_chains_text() -> str:
    """Human-readable list of supported chains."""
    lines = ["Supported chains:\n"]
    for key, chain in SUPPORTED_CHAINS.items():
        lines.append(f"  {chain['name']} ({key}) — {chain['symbol']}")
    return "\n".join(lines)
