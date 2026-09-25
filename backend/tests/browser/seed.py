"""Only run against a disposable database. Creates visibly synthetic cases."""
import os
from datetime import datetime,timezone,timedelta
from smr.db import migrate
from smr.providers import Quote
from smr.repository import create_case,claim_due,finish,state
if os.environ.get('SMR_TEST_DATABASE')!='yes':raise SystemExit('Disposable test database required')
migrate()
now=datetime.now(timezone.utc)
def p(symbol):return dict(chainId='solana',baseToken=dict(address='A'*32,symbol=symbol),pairAddress='test-pair',priceUsd='1',liquidity={'usd':100000},marketCap=200000,volume={'h24':200000},txns={'h1':{'buys':100,'sells':20}},priceChange={'h1':20})
old=now-timedelta(hours=25);create_case(Quote(p('<img src=x onerror=alert(1)>'),old-timedelta(seconds=1),old))
claim_due(now)
t=now-timedelta(seconds=305);create_case(Quote(p('SIMULADO'),t-timedelta(seconds=1),t))
job=claim_due(now)[0];latest=p('SIMULADO');latest['priceUsd']='1.1';finish(job,Quote(latest,now,now+timedelta(seconds=1)))
state('worker',{'status':'running'});state('discovery',{'status':'ok'});state('radar',{'pairs':[p('SIMULADO')]})
print('Synthetic browser fixtures ready')
