"""Database boundary: local SQLite or transactional PostgreSQL on Vercel."""
import os
import pathlib
import re
import sqlite3

BASE = pathlib.Path(__file__).resolve().parent
ID_TABLES = {'users', 'patients', 'consents', 'photos', 'appointments', 'products',
             'lots', 'movements', 'procedures', 'packages', 'redemptions',
             'promotions', 'finance', 'audit', 'source_stock', 'login_attempts'}

class ConfigurationError(RuntimeError):
    pass

class SQLite(sqlite3.Connection):
    def __exit__(self, kind, value, traceback):
        try:
            return super().__exit__(kind, value, traceback)
        finally:
            self.close()

class Record(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

class Result:
    def __init__(self, cursor, inserted=False):
        self.cursor = cursor
        self.lastrowid = cursor.fetchone()['id'] if inserted else None

    def fetchone(self):
        row = self.cursor.fetchone()
        return Record(row) if row is not None else None

    def __iter__(self):
        return (Record(row) for row in self.cursor)

class Postgres:
    """Preserve the application's parameterized queries and transaction boundaries.

    A database advisory transaction lock serializes clinic operations across workers.
    This conservative approach protects FEFO, appointment and package read/write flows.
    It is intended for a small clinic; partition locking before scaling to high traffic.
    """
    def __init__(self, url):
        import psycopg
        from psycopg.rows import dict_row
        self.driver = psycopg
        # Require TLS for remote services; allow local PostgreSQL only during tests.
        from urllib.parse import urlparse
        local = urlparse(url).hostname in {'localhost', '127.0.0.1', '::1'}
        self.conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=10,
                                   sslmode='disable' if local else 'require', prepare_threshold=None)
        self.locked = False

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()

    def execute(self, query, args=()):
        if not self.locked:
            self.conn.execute("SET LOCAL lock_timeout = '10s'")
            self.conn.execute("SET LOCAL statement_timeout = '20s'")
            self.conn.execute('SELECT pg_advisory_xact_lock(891204765)')
            self.locked = True
        if 'sqlite_master' in query:
            query = "SELECT table_name AS name FROM information_schema.tables WHERE table_schema=current_schema() AND table_name='source_stock'"
        # Current application SQL uses positional placeholders and has no literal '?'.
        query = query.replace('?', '%s')
        query = re.sub(r'(?<!["\w])end(?!["\w])', '"end"', query, flags=re.I)
        match = re.match(r'\s*INSERT\s+INTO\s+(\w+)', query, re.I)
        inserted = bool(match and match.group(1).lower() in ID_TABLES and 'RETURNING' not in query.upper())
        if inserted:
            query = query.rstrip(';') + ' RETURNING id'
        try:
            return Result(self.conn.execute(query, args), inserted)
        except self.driver.IntegrityError as exc:
            raise sqlite3.IntegrityError('Constraint violation') from exc

    def commit(self):
        self.conn.commit()
        self.locked = False

    def executescript(self, script):
        for statement in script.split(';'):
            if statement.strip():
                self.execute(statement)

def connect():
    url = os.environ.get('DATABASE_URL', '').strip()
    if url:
        return Postgres(url)
    if os.environ.get('VERCEL') or os.environ.get('YUNA_CLOUD') == '1':
        raise ConfigurationError('ยังไม่ได้ตั้งค่า DATABASE_URL สำหรับฐานข้อมูลออนไลน์')
    db = pathlib.Path(os.environ.get('YUNA_DB', str(BASE / 'data' / 'clinic.db')))
    conn = sqlite3.connect(db, timeout=10, factory=SQLite)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def initialize():
    if not os.environ.get('DATABASE_URL'):
        if os.environ.get('VERCEL') or os.environ.get('YUNA_CLOUD') == '1':
            raise ConfigurationError('ต้องตั้งค่า DATABASE_URL ก่อนสร้างฐานข้อมูลออนไลน์')
        pathlib.Path(os.environ.get('YUNA_DB', str(BASE/'data'/'clinic.db'))).parent.mkdir(parents=True, exist_ok=True)
    schema = 'schema.postgres.sql' if os.environ.get('DATABASE_URL') else 'schema.sql'
    with connect() as conn:
        conn.executescript((BASE / schema).read_text(encoding='utf-8'))
