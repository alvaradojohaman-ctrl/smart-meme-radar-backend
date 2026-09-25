import asyncio
import json
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
import pytest
import httpx
from fastapi.testclient import TestClient
from psycopg.errors import RaiseException
from smr.db import connect,migrate
from smr.providers import Quote,DexScreener
from smr.repository import create_case,claim_due,finish,import_history,get_cases,comparison
from smr.strategy import score,risk
from smr.settings import HORIZONS,settings
from smr.worker import collect_once,discover_once
from smr.api import app

T=datetime(2026,1,1,tzinfo=timezone.utc)
ADDRESS='A'*32

def pair(address=ADDRESS,price='1'):
    return dict(chainId='solana',baseToken=dict(address=address,symbol='TEST'),pairAddress='pair1',priceUsd=price,
                liquidity={'usd':100000},marketCap=200000,volume={'h24':200000},txns={'h1':{'buys':100,'sells':20}},priceChange={'h1':20})
def quote(t=T,price='1'): return Quote(pair(price=price),t-timedelta(seconds=1),t)
def new_case(): return create_case(quote())
def cp(horizon='5m'):
    with connect() as c: return c.execute('SELECT * FROM checkpoints WHERE horizon=%s',(horizon,)).fetchone()
def history():
    # Synthetic fixtures only, never presented as the user's 68 real cases.
    rows=[dict(id=f'synthetic-{i}',address=ADDRESS,time=1700000000000+i,symbol='SYNTHETIC',group='APROBADO',
               market=80,risk=0,entryPrice=1,snapshot={},checkpoints={'5m':{'pct':None},'15m':{'pct':'—'},'30m':{'pct':0},'1h':{'pct':-5}}) for i in range(68)]
    return dict(format='smr-v04d-export-1',rawCases=json.dumps(rows),rawCapital='8500',rawLegacy='[]')

def test_all_six_schedules_and_model():
    new_case(); row=get_cases()[0]
    assert row['model']=='v04d-frozen' and len(row['checkpoints'])==6
    for x in row['checkpoints']:
        assert (x['target_at']-T).total_seconds()==HORIZONS[x['horizon']]
        assert (x['deadline_at']-x['target_at']).total_seconds()==60

def test_dedup_and_24h_new_case():
    assert new_case()
    assert create_case(quote(T+timedelta(hours=23))) is None
    assert create_case(quote(T+timedelta(hours=24)))
    assert len(get_cases())==2

@pytest.mark.parametrize('horizon,seconds',list(HORIZONS.items()))
def test_each_horizon_independent(horizon,seconds):
    new_case(); at=T+timedelta(seconds=seconds)
    jobs=claim_due(at)
    job=next(x for x in jobs if x['horizon']==horizon)
    assert finish(job,quote(at+timedelta(seconds=2),price='1.2'))
    row=cp(horizon)
    assert row['pct']==pytest.approx(20) and row['delay_seconds']==2
    assert row['status']=='observed'

@pytest.mark.parametrize('delay,accepted',[(0,True),(60,True),(61,False),(18000,False)])
def test_window_edges(delay,accepted):
    new_case(); job=claim_due(T+timedelta(minutes=5))[0]
    received=T+timedelta(minutes=5,seconds=delay)
    q=Quote(pair(),T+timedelta(minutes=5),received)
    assert finish(job,q)==accepted
    row=cp()
    assert row['status']==('observed' if accepted else 'missed')
    if not accepted: assert row['price'] is None and row['pct'] is None and row['observed_at'] is None

def test_no_early_reading_and_retry():
    new_case(); assert claim_due(T+timedelta(seconds=299))==[]
    job=claim_due(T+timedelta(seconds=300))[0]
    assert not finish(job,Quote(pair(),T+timedelta(seconds=299),T+timedelta(seconds=301)))
    job=claim_due(T+timedelta(seconds=304))[0]
    assert finish(job,quote(T+timedelta(seconds=305)))

def test_restart_expiration_no_backfill():
    new_case(); assert claim_due(T+timedelta(days=2))==[]
    assert all(x['status']=='missed' and x['pct'] is None for x in get_cases()[0]['checkpoints'])
    assert all(x['n']==0 and x['mean_pct'] is None and x['winners_pct'] is None for x in comparison())

def test_retry_error_then_success():
    new_case();job=claim_due(T+timedelta(seconds=300))[0]
    finish(job,error='HTTPStatusError',finished=T+timedelta(seconds=301))
    assert not claim_due(T+timedelta(seconds=302))
    job=claim_due(T+timedelta(seconds=304))[0]
    assert finish(job,quote(T+timedelta(seconds=305),price='.8'))
    assert cp()['attempts']==2 and cp()['pct']==pytest.approx(-20)

def test_lease_recovery_and_stale_completion():
    new_case();first=claim_due(T+timedelta(seconds=300))[0]
    assert claim_due(T+timedelta(seconds=301))==[]
    second=claim_due(T+timedelta(seconds=331))[0]
    assert not finish(first,quote(T+timedelta(seconds=332)))
    assert finish(second,quote(T+timedelta(seconds=333)))
    assert not finish(second,quote(T+timedelta(seconds=334),price='2'))
    assert cp()['price']==1

def test_import_roundtrip_missing_unchanged_and_idempotent():
    payload=history(); assert import_history(payload)['imported']==68
    assert import_history(payload)['existing']==68
    with connect() as c:
        row=c.execute('SELECT * FROM historical_imports').fetchone()
        assert row['raw_cases']==payload['rawCases'] and row['payload']==payload
        assert c.execute('SELECT COUNT(*) n FROM historical_cases').fetchone()['n']==68
        assert float(c.execute('SELECT capital_gtq FROM paper_account').fetchone()['capital_gtq'])==8500
        assert c.execute('SELECT COUNT(*) n FROM checkpoints').fetchone()['n']==0
    assert comparison()==[]
    with pytest.raises(RaiseException):
        with connect() as c: c.execute("UPDATE historical_cases SET payload='{}'")

def test_import_count_and_conflict():
    payload=history();bad=payload.copy();bad['rawCases']='[]'
    with pytest.raises(ValueError):import_history(bad)
    import_history(payload)
    rows=json.loads(payload['rawCases']);rows[0]['symbol']='CHANGED';payload['rawCases']=json.dumps(rows)
    with pytest.raises(ValueError):import_history(payload)

@pytest.mark.asyncio
async def test_not_in_discovery_but_tracked(monkeypatch):
    new_case()
    calls=[]
    class Fake:
        async def profiles(self): return []
        async def quote(self,address):
            calls.append(address);return quote(T+timedelta(seconds=302))
    await discover_once(Fake())
    import smr.worker as worker
    monkeypatch.setattr(worker,'claim_due',lambda:claim_due(T+timedelta(seconds=300)))
    await collect_once(Fake())
    assert calls==[ADDRESS] and cp()['status']=='observed'

@pytest.mark.asyncio
async def test_provider_filter_and_pair_selection():
    provider=DexScreener()
    wrong=pair('B'*32,price='999')
    other=pair(price='2');other['liquidity']['usd']=200000;other['pairAddress']='pair2'
    async def handler(request):return httpx.Response(200,json=[wrong,pair(),other])
    await provider.client.aclose()
    provider.client=httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='https://api.dexscreener.com')
    q=await provider.quote(ADDRESS)
    assert q.pair['priceUsd']=='2' and q.pair['pairAddress']=='pair2'
    await provider.close()

@pytest.mark.asyncio
async def test_provider_429_and_no_pair():
    provider=DexScreener()
    async def handler(request):return httpx.Response(429,headers={'Retry-After':'1'})
    await provider.client.aclose();provider.client=httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='https://api.dexscreener.com')
    with pytest.raises(httpx.HTTPStatusError):await provider.quote(ADDRESS)
    assert provider.cooldown>0
    await provider.close()

def test_api_auth_import_export_and_health():
    with TestClient(app) as client:
        assert client.get('/healthz').status_code==200
        assert client.get('/readyz').status_code==503
        assert client.get('/api/cases').status_code==401
        headers={'Authorization':'Bearer '+settings.api_key}
        assert client.post('/api/history/import',json=history(),headers=headers).json()['imported']==68
        assert client.get('/api/history',headers=headers).json()==history()
        assert client.get('/api/status',headers=headers).json()['historical_count']==68
        assert len(client.get('/api/export',headers=headers).json()['tables']['historical_cases'])==68
        assert client.post('/api/history/import',json=history()).status_code==401
        assert client.get('/api/cases?limit=1001',headers=headers).status_code==422
        cors=client.options('/api/cases',headers={'Origin':'https://evil.invalid','Access-Control-Request-Method':'GET'})
        assert cors.status_code==400

def test_migration_rerun_preserves_data():
    new_case();migrate();assert len(get_cases())==1

def test_python_matches_original_javascript():
    rng=random.Random(404)
    pairs=[]
    for _ in range(1000):
        p=pair();p.update(liquidity={'usd':rng.uniform(0,300000)},marketCap=rng.uniform(0,10000000),
                         volume={'h24':rng.uniform(0,200000)},priceChange={'h1':rng.uniform(-100,200)},
                         txns={'h1':{'buys':rng.randrange(0,200),'sells':rng.randrange(0,200)}});pairs.append(p)
    pairs.extend([{},pair(),dict(liquidity={'usd':9999},marketCap=1000000,txns={'h1':{'buys':0,'sells':20}},priceChange={'h1':-35})])
    root=Path(__file__).resolve().parents[2]
    js=(root/'archive/v04d/index.html').read_text().split('function risk(')[1].split('function pct(')[0]
    js='const clamp=(x,a,b)=>Math.max(a,Math.min(b,x)); function risk('+js
    js+=';let s="";process.stdin.on("data",x=>s+=x);process.stdin.on("end",()=>console.log(JSON.stringify(JSON.parse(s).map(p=>({score:score(p),risk:risk(p)})))));'
    expected=json.loads(subprocess.check_output(['node','-e',js],input=json.dumps(pairs).encode()))
    assert expected==[dict(score=score(p),risk=risk(p)) for p in pairs]

def test_wrong_address_cannot_fill_checkpoint():
    new_case();job=claim_due(T+timedelta(seconds=300))[0]
    q=Quote(pair('B'*32),T+timedelta(seconds=301),T+timedelta(seconds=302))
    assert not finish(job,q)
    assert cp()['pct'] is None

def test_missing_does_not_dilute_comparison():
    new_case();job=claim_due(T+timedelta(seconds=300))[0]
    assert finish(job,quote(T+timedelta(seconds=302),price='1.1'))
    claim_due(T+timedelta(days=2))
    rows=comparison()
    measured=next(x for x in rows if x['horizon']=='5m')
    missing=next(x for x in rows if x['horizon']=='15m')
    assert measured['n']==1 and measured['mean_pct']==pytest.approx(10)
    assert missing['n']==0 and missing['missed']==1 and missing['mean_pct'] is None

@pytest.mark.asyncio
async def test_provider_absent_or_invalid_prices():
    provider=DexScreener()
    async def handler(request):return httpx.Response(200,json=[pair(price='0'),pair(price='NaN'),pair('B'*32)])
    await provider.client.aclose();provider.client=httpx.AsyncClient(transport=httpx.MockTransport(handler),base_url='https://api.dexscreener.com')
    with pytest.raises(ValueError):await provider.quote(ADDRESS)
    await provider.close()
