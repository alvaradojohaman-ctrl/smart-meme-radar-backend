import hashlib
import json
import math
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from psycopg.types.json import Jsonb
from .db import connect
from .settings import HORIZONS, TOLERANCE_SECONDS, PROTOCOL, MODEL
from .strategy import score, risk, snapshot, num


def now(): return datetime.now(timezone.utc)

def state(key, value):
    with connect() as c:
        c.execute('INSERT INTO service_state(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=now()', (key, Jsonb(value)))

def create_case(quote):
    p, t = quote.pair, quote.received_at
    address, price = p['baseToken']['address'], num(p.get('priceUsd'))
    q, r = score(p), risk(p)
    if q<75 or price<=0: return None
    with connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('solana:'+address,))
        recent = c.execute("SELECT 1 FROM cases WHERE chain='solana' AND address=%s AND entered_at>%s", (address,t-timedelta(hours=24))).fetchone()
        if recent: return None
        cid = uuid4()
        c.execute('''INSERT INTO cases(id,address,symbol,entered_at,entry_price,market,risk,group_name,reasons,snapshot,pair_address,model,protocol)
                     VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                  (cid,address,p['baseToken'].get('symbol') or '?',t,price,q,r['points'],
                   'BLOQUEADO' if r['blocked'] else 'APROBADO',Jsonb(r['reasons']),Jsonb(snapshot(p)),p['pairAddress'],MODEL,PROTOCOL))
        for horizon, seconds in HORIZONS.items():
            target = t+timedelta(seconds=seconds)
            c.execute('''INSERT INTO checkpoints(case_id,horizon,target_at,deadline_at,next_attempt_at)
                         VALUES(%s,%s,%s,%s,%s)''', (cid,horizon,target,target+timedelta(seconds=TOLERANCE_SECONDS),target))
        return cid

def claim_due(at=None, limit=12):
    at = at or now()
    with connect() as c:
        # Recovery after downtime never fetches current prices for expired horizons.
        c.execute("""UPDATE checkpoints SET status='missed', finalized_at=%s,
                     last_error=COALESCE(last_error,'window_expired'), lease_until=NULL,lease_token=NULL
                     WHERE status='pending' AND deadline_at<%s AND (lease_until IS NULL OR lease_until<%s)""", (at,at,at))
        rows = c.execute('''SELECT cp.*, ca.address, ca.entry_price FROM checkpoints cp JOIN cases ca ON ca.id=cp.case_id
                 WHERE cp.status='pending' AND cp.target_at<=%s AND cp.deadline_at>=%s AND cp.next_attempt_at<=%s
                   AND (cp.lease_until IS NULL OR cp.lease_until<%s)
                 ORDER BY cp.deadline_at,cp.id LIMIT %s FOR UPDATE OF cp SKIP LOCKED''', (at,at,at,at,limit)).fetchall()
        for row in rows:
            token = uuid4()
            c.execute('UPDATE checkpoints SET lease_until=%s,lease_token=%s WHERE id=%s', (at+timedelta(seconds=30),token,row['id']))
            row['lease_token']=token
        return rows

def finish(job, quote=None, error=None, started=None, finished=None):
    received = quote.received_at if quote else (finished or now())
    requested = quote.requested_at if quote else (started or received)
    p = quote.pair if quote else None
    price = num(p.get('priceUsd')) if p else None
    valid_price = bool(price and price>0)
    with connect() as c:
        cp = c.execute('SELECT * FROM checkpoints WHERE id=%s FOR UPDATE', (job['id'],)).fetchone()
        owns = cp['status']=='pending' and cp['lease_token']==job['lease_token']
        matches = bool(p and p.get('chainId')=='solana' and (p.get('baseToken') or {}).get('address')==job['address'] and p.get('pairAddress'))
        accepted = owns and valid_price and matches and cp['target_at']<=requested<=received<=cp['deadline_at']
        reason = error or (None if accepted else 'outside_window_or_stale_lease')
        c.execute('''INSERT INTO observations(checkpoint_id,requested_at,received_at,price,pair_address,error,accepted,payload)
                     VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',
                  (job['id'],requested,received,price if valid_price else None,p.get('pairAddress') if p else None,reason,accepted,Jsonb(p) if p else None))
        if not owns: return False
        if accepted:
            c.execute('''UPDATE checkpoints SET status='observed',observed_at=%s,delay_seconds=%s,price=%s,pct=%s,
                         pair_address=%s,source='dexscreener',attempts=attempts+1,last_error=NULL,
                         lease_until=NULL,lease_token=NULL,finalized_at=%s WHERE id=%s''',
                      (received,(received-cp['target_at']).total_seconds(),price,(price/job['entry_price']-1)*100,
                       p['pairAddress'],received,job['id']))
        elif received>cp['deadline_at']:
            c.execute("""UPDATE checkpoints SET status='missed',attempts=attempts+1,last_error=%s,
                         lease_until=NULL,lease_token=NULL,finalized_at=%s WHERE id=%s""", (reason,received,job['id']))
        else:
            delay = min(20, 2**min(cp['attempts']+1,4))
            c.execute('''UPDATE checkpoints SET attempts=attempts+1,last_error=%s,next_attempt_at=%s,
                         lease_until=NULL,lease_token=NULL WHERE id=%s''', (reason,received+timedelta(seconds=delay),job['id']))
        return accepted

def import_history(payload):
    if payload.get('format')!='smr-v04d-export-1':
        raise ValueError('Formato de exportación no reconocido')
    raw = payload.get('rawCases')
    if not isinstance(raw,str): raise ValueError('Falta rawCases original')
    cases = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('JSON no finito')))
    if not isinstance(cases,list) or len(cases)!=68:
        raise ValueError('Se requieren exactamente los 68 casos históricos; no se importó nada')
    ids=[]
    for row in cases:
        if not isinstance(row,dict) or not all(k in row for k in ('id','address','time','snapshot','checkpoints')):
            raise ValueError('Caso histórico incompleto; no se importó nada')
        if not isinstance(row['id'],str) or not isinstance(row['address'],str): raise ValueError('ID/dirección inválidos')
        ids.append(row['id'])
    if len(set(ids))!=68: raise ValueError('Hay IDs duplicados')
    raw_legacy = payload.get('rawLegacy')
    if raw_legacy is not None:
        if not isinstance(raw_legacy,str) or not isinstance(json.loads(raw_legacy),list):
            raise ValueError('Historial anterior inválido')
    capital = payload.get('rawCapital')
    if capital is not None:
        try: cap = float(capital)
        except (TypeError,ValueError): raise ValueError('Capital virtual inválido')
        if not math.isfinite(cap) or cap<0: raise ValueError('Capital virtual inválido')
    digest = hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    with connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(40405002)')
        existing=c.execute('SELECT id,raw_cases FROM historical_imports').fetchone()
        if existing:
            if json.loads(existing['raw_cases'])==cases:
                return dict(imported=0, existing=68, batch_id=existing['id'])
            raise ValueError('La cohorte histórica ya está congelada; el nuevo archivo es diferente')
        c.execute('INSERT INTO historical_imports(id,case_count,payload,raw_cases) VALUES(%s,68,%s,%s)', (digest,Jsonb(payload),raw))
        for i,row in enumerate(cases):
            c.execute('INSERT INTO historical_cases(id,batch_id,ordinal,payload) VALUES(%s,%s,%s,%s)', (row['id'],digest,i,Jsonb(row)))
        if capital is not None:
            c.execute('UPDATE paper_account SET capital_gtq=%s WHERE id=1', (cap,))
    return dict(imported=68, existing=0, batch_id=digest)

def get_cases(limit=500, offset=0):
    with connect() as c:
        rows=c.execute('SELECT * FROM cases ORDER BY entered_at DESC,id LIMIT %s OFFSET %s', (limit,offset)).fetchall()
        for row in rows:
            row['checkpoints']=c.execute('SELECT * FROM checkpoints WHERE case_id=%s ORDER BY target_at', (row['id'],)).fetchall()
        return rows

def comparison():
    with connect() as c:
        return c.execute('''SELECT cp.horizon,c.group_name,COUNT(*) AS scheduled,
           COUNT(*) FILTER(WHERE cp.status='observed') AS n,
           COUNT(*) FILTER(WHERE cp.status='missed') AS missed,
           COUNT(*) FILTER(WHERE cp.status='pending') AS pending,
           AVG(cp.pct) FILTER(WHERE cp.status='observed') AS mean_pct,
           AVG(CASE WHEN cp.pct>0 THEN 100.0 ELSE 0.0 END) FILTER(WHERE cp.status='observed') AS winners_pct
           FROM checkpoints cp JOIN cases c ON c.id=cp.case_id GROUP BY cp.horizon,c.group_name''').fetchall()
