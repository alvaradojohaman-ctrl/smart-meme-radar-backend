import os
import pytest
os.environ.setdefault('API_KEY','test-key-only-0123456789abcdefghijk')
from smr.db import connect,migrate

@pytest.fixture(autouse=True)
def database():
    if not os.getenv('DATABASE_URL'):
        pytest.fail('Set DATABASE_URL to a disposable PostgreSQL database; tests destroy its public schema')
    if os.getenv('SMR_TEST_DATABASE')!='yes':
        pytest.fail('Set SMR_TEST_DATABASE=yes to authorize resetting the test database')
    with connect() as c:
        c.execute('DROP SCHEMA public CASCADE')
        c.execute('CREATE SCHEMA public')
    migrate()
