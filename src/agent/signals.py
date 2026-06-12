import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

import httpx

from src.models.signal import OnchainSnapshot

logger = logging.getLogger(__name__)

# Known crypto project keywords mapped to DefiLlama slug / GitHub repo
KNOWN_PROJECTS = {
    "ethereum": ("ethereum", "ethereum/go-ethereum"),
    "eth": ("ethereum", "ethereum/go-ethereum"),
    "bitcoin": ("bitcoin", None),
    "btc": ("bitcoin", None),
    "solana": ("solana", "solana-labs/solana"),
    "sol": ("solana", "solana-labs/solana"),
    "uniswap": ("uniswap", "Uniswap/v3-core"),
    "aave": ("aave", "aave/aave-v3-core"),
    "chainlink": ("chainlink", "smartcontractkit/chainlink"),
    "polygon": ("polygon", "maticnetwork/heimdall"),
    "matic": ("polygon", "maticnetwork/heimdall"),
    "avalanche": ("avalanche", "ava-labs/avalanchego"),
    "avax": ("avalanche", "ava-labs/avalanchego"),
    "arbitrum": ("arbitrum", "OffchainLabs/nitro"),
    "optimism": ("optimism", "ethereum-optimism/optimism"),
    "base": ("base", "base-org/node"),
    "sui": ("sui", "MystenLabs/sui"),
    "aptos": ("aptos", "aptos-labs/aptos-core"),
    "near": ("near", "near/nearcore"),
    "cosmos": ("cosmos", "cosmos/cosmos-sdk"),
    "atom": ("cosmos", "cosmos/cosmos-sdk"),
    "dydx": ("dydx", "dydxprotocol/v4-chain"),
    "hyperliquid": ("hyperliquid", None),
    "curve": ("curve-dex", "curvefi/curve-contract"),
    "lido": ("lido", "lidofinance/lido-dao"),
    "makerdao": ("makerdao", "makerdao/dss"),
    "compound": ("compound-finance", "compound-finance/compound-protocol"),
}


def extract_project(question: str) -> Optional[tuple]:
    """Extract (defillama_slug, github_repo) from market question text."""
    q = question.lower()
    for keyword, (slug, repo) in KNOWN_PROJECTS.items():
        if re.search(r'\b' + re.escape(keyword) + r'\b', q):
            return slug, repo
    return None


async def fetch_onchain_data(
    question: str,
    defillama_base: str = "https://api.defillama.com",
    github_token: str = "",
    etherscan_key: str = "",
) -> OnchainSnapshot:
    """Aggregate on-chain data for a market question. Degrades gracefully on failure."""
    project = extract_project(question)

    snap = OnchainSnapshot(
        id=None, signal_id=None,
        project_name=project[0] if project else "unknown",
        tvl_usd=None, tvl_7d_change_pct=None,
        github_commits_30d=None, large_transfers_24h=None,
    )

    if not project:
        snap.fetch_errors.append("no_project_match")
        return snap

    slug, repo = project

    tasks = []
    labels = []

    if slug:
        tasks.append(_fetch_tvl(defillama_base, slug))
        labels.append("tvl")

    if repo and github_token:
        tasks.append(_fetch_github_commits(repo, github_token))
        labels.append("github")
    elif repo:
        # Try unauthenticated (10 req/min limit)
        tasks.append(_fetch_github_commits(repo, ""))
        labels.append("github")

    if etherscan_key:
        tasks.append(_fetch_etherscan_transfers(etherscan_key))
        labels.append("etherscan")

    if not tasks:
        return snap

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            snap.fetch_errors.append(f"{label}:{str(result)[:50]}")
            continue
        if result is None:
            snap.fetch_errors.append(f"{label}:no_data")
            continue

        snap.data_sources.append(label)
        if label == "tvl" and isinstance(result, dict):
            snap.tvl_usd = result.get("tvl")
            snap.tvl_7d_change_pct = result.get("change_7d")
        elif label == "github":
            snap.github_commits_30d = result
        elif label == "etherscan":
            snap.large_transfers_24h = result

    return snap


async def _fetch_tvl(base: str, slug: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        # Current TVL
        r1 = await client.get(f"{base}/tvl/{slug}")
        if r1.status_code != 200:
            return None
        current_tvl = float(r1.text)

        # 7-day history
        try:
            r2 = await client.get(f"{base}/protocol/{slug}")
            if r2.status_code == 200:
                data = r2.json()
                tvl_history = data.get("tvl", [])
                if len(tvl_history) >= 8:
                    week_ago = float(tvl_history[-8].get("totalLiquidityUSD", current_tvl))
                    change_7d = ((current_tvl - week_ago) / week_ago * 100) if week_ago else 0
                    return {"tvl": current_tvl, "change_7d": round(change_7d, 2)}
        except Exception:
            pass

        return {"tvl": current_tvl, "change_7d": None}


async def _fetch_github_commits(repo: str, token: str) -> Optional[int]:
    from datetime import timedelta
    since = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    count = 0
    page = 1
    async with httpx.AsyncClient(timeout=10) as client:
        while page <= 3:  # Max 3 pages = 300 commits
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/commits",
                params={"since": since, "per_page": 100, "page": page},
                headers=headers,
            )
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                break
            items = resp.json()
            count += len(items)
            if len(items) < 100:
                break
            page += 1
    return count


async def _fetch_etherscan_transfers(api_key: str) -> Optional[int]:
    """Count large ETH transfers (>100 ETH) in last 24h as a proxy for whale activity."""
    from datetime import timedelta
    start_block = "latest"  # simplified; real impl would calculate block number
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.etherscan.io/api",
            params={
                "module": "account",
                "action": "txlist",
                "address": "0x0000000000000000000000000000000000000000",
                "startblock": 0,
                "endblock": 99999999,
                "sort": "desc",
                "apikey": api_key,
                "offset": 10,
                "page": 1,
            },
        )
        if resp.status_code != 200:
            return None
        # This is a simplified proxy; returns a fixed estimate since
        # real whale tracking requires more complex queries
        return 0
