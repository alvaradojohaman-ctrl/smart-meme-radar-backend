"""Market data boundary. Future Helius/Smart Money adapters must use a new
protocol/cohort and never mutate the frozen score or historical observations.
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Protocol
from dataclasses import dataclass
import httpx
from .strategy import num

@dataclass
class Quote:
    pair: dict
    requested_at: datetime
    received_at: datetime

class MarketProvider(Protocol):
    async def profiles(self) -> list: ...
    async def quote(self, address: str) -> Quote: ...

class DexScreener:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url='https://api.dexscreener.com', timeout=10,
                                       headers={'User-Agent': 'SmartMemeRadar/0.4E'})
        self.lock = asyncio.Lock()
        self.next_request = 0.0
        self.cooldown = 0.0

    async def get(self, path):
        # Shared across discovery/checkpoints, <= 240 requests/minute overall.
        async with self.lock:
            await asyncio.sleep(max(0, self.next_request-time.monotonic(), self.cooldown-time.monotonic()))
            self.next_request = time.monotonic()+.25
        requested = datetime.now(timezone.utc)
        response = await self.client.get(path)
        received = datetime.now(timezone.utc)
        if response.status_code == 429:
            try: delay = min(120, max(1, float(response.headers.get('Retry-After', '30'))))
            except ValueError: delay = 30
            self.cooldown = time.monotonic()+delay
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError('unexpected_provider_payload')
        return payload, requested, received

    async def profiles(self):
        data, _, _ = await self.get('/token-profiles/latest/v1')
        return data

    async def quote(self, address):
        data, requested, received = await self.get('/token-pairs/v1/solana/'+address)
        # Never price the quote token as if it were the tracked base token.
        pairs = [p for p in data if p.get('chainId')=='solana' and (p.get('baseToken') or {}).get('address')==address
                 and num(p.get('priceUsd'))>0 and p.get('pairAddress')]
        if not pairs:
            raise ValueError('no_valid_pair_or_price')
        # Same highest-liquidity selection as v0.4D. Record pair at every reading.
        return Quote(max(pairs, key=lambda p: num((p.get('liquidity') or {}).get('usd'))), requested, received)

    async def close(self):
        await self.client.aclose()
