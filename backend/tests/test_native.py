"""Run on native PostgreSQL, never on the WebAssembly test surrogate."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from smr.db import connect
from smr.repository import claim_due,create_case,get_cases
from test_system import quote,T

pytestmark=pytest.mark.native

def test_concurrent_admission_only_one_case():
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:create_case(quote()),range(4)))
    assert sum(x is not None for x in results)==1
    assert len(get_cases())==1

def test_concurrent_claim_only_one_owner():
    create_case(quote())
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs=list(pool.map(lambda _:claim_due(T+timedelta(seconds=300)),range(4)))
    assert sum(len(x) for x in jobs)==1

def test_worker_leader_lock_excludes_other_session():
    with connect() as first,connect() as second:
        first.autocommit=True;second.autocommit=True
        assert first.execute('SELECT pg_try_advisory_lock(40405003) AS locked').fetchone()['locked']
        assert not second.execute('SELECT pg_try_advisory_lock(40405003) AS locked').fetchone()['locked']
