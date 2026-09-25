import secrets
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .settings import settings, PROTOCOL, MODEL
from .db import connect, migrate
from .repository import import_history, get_cases, comparison

@asynccontextmanager
async def lifespan(app):
    settings.validate()
    migrate()
    yield

app=FastAPI(title='Smart Meme Radar',version='0.4E',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.add_middleware(CORSMiddleware,allow_origins=list(settings.origins),allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])
auth=HTTPBearer(auto_error=False)
def authorized(credentials: HTTPAuthorizationCredentials=Depends(auth)):
    if not credentials or not secrets.compare_digest(credentials.credentials,settings.api_key):
        raise HTTPException(401,'Clave incorrecta o ausente')

@app.get('/healthz')
def health():
    try:
        with connect() as c: c.execute('SELECT 1')
        return {'status':'ok','version':'0.4E'}
    except Exception: return JSONResponse({'status':'database_unavailable'},status_code=503)

@app.get('/readyz')
def ready():
    with connect() as c:
        row=c.execute("SELECT updated_at FROM service_state WHERE key='worker'").fetchone()
        fresh=bool(row and (datetime.now(timezone.utc)-row['updated_at']).total_seconds()<120)
        return JSONResponse({'collector_fresh':fresh},status_code=200 if fresh else 503)

@app.get('/api/status',dependencies=[Depends(authorized)])
def status():
    with connect() as c:
        services=c.execute('SELECT * FROM service_state').fetchall()
        worker=next((x for x in services if x['key']=='worker'),None)
        return dict(version='0.4E',model=MODEL,protocol=PROTOCOL,
                    worker_fresh=bool(worker and (datetime.now(timezone.utc)-worker['updated_at']).total_seconds()<120),
                    services=services, paper=c.execute('SELECT * FROM paper_account').fetchone(),
                    historical_count=c.execute('SELECT COUNT(*) AS n FROM historical_cases').fetchone()['n'],
                    case_count=c.execute('SELECT COUNT(*) AS n FROM cases').fetchone()['n'])

@app.get('/api/cases',dependencies=[Depends(authorized)])
def cases(limit:int=Query(500,ge=1,le=1000),offset:int=Query(0,ge=0)):
    return get_cases(limit,offset)

@app.get('/api/comparison',dependencies=[Depends(authorized)])
def compare(): return comparison()

@app.get('/api/history',dependencies=[Depends(authorized)])
def history():
    with connect() as c:
        row=c.execute('SELECT payload FROM historical_imports').fetchone()
        return row['payload'] if row else None

@app.post('/api/history/import',dependencies=[Depends(authorized)])
async def history_import(request:Request):
    # Enforce size while reading even without a Content-Length header.
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>5_000_000: raise HTTPException(413,'Archivo demasiado grande')
    try:
        payload=json.loads(body)
        if not isinstance(payload,dict): raise ValueError('Se esperaba un objeto JSON')
        return import_history(payload)
    except (ValueError,TypeError,KeyError) as e: raise HTTPException(422,str(e)) from e

@app.get('/api/export',dependencies=[Depends(authorized)])
def export():
    # Single repeatable-read snapshot: no mixed backup as worker commits.
    with connect() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        tables=['cases','checkpoints','observations','historical_imports','historical_cases','paper_account','service_state','schema_versions']
        return {'format':'smr-v04e-audit-1','exported_at':datetime.now(timezone.utc),
                'tables':{table:c.execute('SELECT * FROM '+table).fetchall() for table in tables}}
