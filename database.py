"""Storage connections. Supabase is authoritative when SUPABASE_DB_URL is set."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class DatabaseError(RuntimeError):
    pass


class PostgresConnection:
    # Only trusted, internal SQL is accepted; values always stay parameterized.
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        return self.connection.execute(sql.replace('?', '%s'), params or None)

    def executemany(self, sql, rows):
        cursor = self.connection.cursor()
        cursor.executemany(sql.replace('?', '%s'), rows)
        return cursor


class Database:
    def __init__(self, path, config):
        self.path = Path(path)
        self.remote = bool(config.get('SUPABASE_DB_URL', '').strip())
        self.pool = None
        if self.remote:
            try:
                import certifi
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool
            except ImportError:
                raise DatabaseError('Installe les dépendances : .venv/bin/python -m pip install -r requirements.txt') from None
            url = config['SUPABASE_DB_URL'].strip()
            if not url.startswith(('postgresql://', 'postgres://')):
                raise DatabaseError('SUPABASE_DB_URL doit être une URL PostgreSQL.')
            # Verify the server identity. Never silently fall back to local storage.
            self.pool = ConnectionPool(url, min_size=0, max_size=4, open=True, timeout=20,
                kwargs={'row_factory': dict_row, 'connect_timeout': 10,
                        'sslmode': 'verify-full',
                        'sslrootcert': str((Path(__file__).resolve().parent / config['SUPABASE_SSLROOTCERT']).resolve()) if config.get('SUPABASE_SSLROOTCERT') else certifi.where(),
                        'application_name': 'ad-analyser', 'prepare_threshold': None})
            try:
                with self.connect() as db:
                    row = db.execute('SELECT version FROM schema_migrations WHERE version=1').fetchone()
                    if not row:
                        raise DatabaseError('Migration Supabase manquante : appliquer le fichier SQL du projet.')
            except Exception:
                self.pool.close()
                raise DatabaseError('Connexion Supabase impossible ou tables absentes. Vérifie la connexion et la migration SQL.') from None

    @contextmanager
    def connect(self):
        if self.remote:
            try:
                with self.pool.connection() as conn:
                    conn.execute('SET LOCAL search_path TO ad_pipeline, pg_catalog')
                    conn.execute('SET LOCAL extra_float_digits TO 3')
                    conn.execute("SET LOCAL statement_timeout TO '30s'")
                    yield PostgresConnection(conn)
            except (ValueError, DatabaseError):
                raise
            except Exception as exc:
                # Driver errors can contain hosts, credentials or input data.
                from psycopg import Error
                from psycopg_pool import PoolTimeout
                if isinstance(exc, (Error, PoolTimeout)):
                    raise DatabaseError('Opération Supabase interrompue. Vérifie la connexion puis réessaie.') from None
                raise
        else:
            db = sqlite3.connect(self.path, timeout=30)
            db.row_factory = sqlite3.Row
            try:
                with db:
                    yield db
            finally:
                db.close()

    def close(self):
        if self.pool:
            self.pool.close()
