from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from .settings import settings

def connect():
    return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=10, prepare_threshold=None)

def migrate():
    with connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(40405001)')
        c.execute(Path(__file__).with_name('schema.sql').read_text())

if __name__ == '__main__':
    settings.validate()
    migrate()
    print('Schema v1 ready')
