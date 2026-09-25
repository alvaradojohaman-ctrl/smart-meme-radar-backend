import asyncio
import logging
import re
from datetime import datetime, timezone
from .db import connect, migrate
from .settings import settings
from .providers import DexScreener
from .repository import claim_due, finish, create_case, state, now
from .strategy import score, num

log = logging.getLogger('smr.worker')
ADDRESS = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')

async def process(job, provider):
    start = now()
    try:
        quote = await provider.quote(job['address'])
    except Exception as e:
        # Do not persist credentials/URLs from arbitrary exception text.
        finish(job,error=type(e).__name__,started=start)
        log.warning('quote_failed checkpoint=%s type=%s',job['id'],type(e).__name__)
    else:
        finish(job,quote=quote)

async def collect_once(provider):
    jobs = claim_due()
    await asyncio.gather(*(process(job,provider) for job in jobs))
    return len(jobs)

async def checkpoints_loop(provider, leader):
    while True:
        leader.execute('SELECT 1')  # Lost lock connection => stop; supervisor restarts.
        count = await collect_once(provider)
        state('worker', {'status':'running','claimed_last_cycle':count})
        await asyncio.sleep(2)

async def discover_once(provider):
    profiles = await provider.profiles()
    addresses=list(dict.fromkeys(p.get('tokenAddress') for p in profiles
                if p.get('chainId')=='solana' and ADDRESS.fullmatch(p.get('tokenAddress') or '')))[:24]
    quotes=[]
    errors=0
    for i in range(0,len(addresses),6):
        results=await asyncio.gather(*(provider.quote(a) for a in addresses[i:i+6]),return_exceptions=True)
        for result in results:
            if isinstance(result,Exception): errors+=1
            elif num((result.pair.get('liquidity') or {}).get('usd'))>0: quotes.append(result)
    quotes.sort(key=lambda q:score(q.pair),reverse=True)
    quotes=quotes[:20]
    for quote in quotes: create_case(quote)
    state('radar', {'pairs':[q.pair for q in quotes], 'errors':errors,
                    'observed_at':now().isoformat(), 'scope':'latest 24 profiles / top 20 by frozen score'})
    state('discovery', {'status':'ok' if not errors else 'partial','errors':errors})

async def discovery_loop(provider):
    while True:
        try: await discover_once(provider)
        except Exception as e:
            log.exception('discovery_failed')
            state('discovery', {'status':'error','error':type(e).__name__})
        await asyncio.sleep(settings.discovery_seconds)

async def main():
    settings.validate()
    migrate()
    # Single leader prevents doubled discovery/rate limits. API is a separate process.
    with connect() as leader:
        leader.autocommit=True
        if not leader.execute('SELECT pg_try_advisory_lock(40405003) AS locked').fetchone()['locked']:
            raise RuntimeError('Another collector is active; run exactly one worker')
        provider=DexScreener()
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(checkpoints_loop(provider,leader))
                tg.create_task(discovery_loop(provider))
        finally: await provider.close()

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(main())
