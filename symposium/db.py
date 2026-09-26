"""Thin data-access layer over mysql-connector-python with a connection pool.

Every query goes through parameterised statements (%s placeholders) so user
input can never be interpreted as SQL (prevents SQL injection).
"""
from contextlib import contextmanager

import mysql.connector
from mysql.connector import errorcode, pooling


class DatabaseError(Exception):
    """User-friendly database error raised to the UI layer."""


def friendly_error(err: mysql.connector.Error) -> str:
    """Translate MySQL error codes into messages a normal user understands."""
    if getattr(err, "sqlstate", None) == "45000":        # SIGNAL from triggers / procedures
        return err.msg
    code = getattr(err, "errno", None)
    if code == errorcode.ER_DUP_ENTRY:
        msg = err.msg.lower()
        if "email" in msg:
            return "An account with this e-mail already exists."
        if "event_name" in msg:
            return "An event with this name already exists."
        if "uq_reg_user_event" in msg:
            return "You are already registered for this event."
        if "primary" in msg and "event_result" in msg:
            return "That position has already been awarded for this event."
        return "This record already exists (duplicate value)."
    if code in (errorcode.ER_ROW_IS_REFERENCED, errorcode.ER_ROW_IS_REFERENCED_2):
        return "This record is in use by other records and cannot be deleted."
    if code in (errorcode.ER_NO_REFERENCED_ROW, errorcode.ER_NO_REFERENCED_ROW_2):
        return "A referenced record does not exist."
    if code == errorcode.ER_CHECK_CONSTRAINT_VIOLATED:
        return f"Invalid value - a data rule was violated.\n({err.msg})"
    if code == errorcode.ER_ACCESS_DENIED_ERROR:
        return "MySQL rejected the username or password."
    if code == errorcode.ER_BAD_DB_ERROR:
        return "The database does not exist yet. Initialise it from the setup screen."
    if code in (2003, 2005):
        return "Cannot reach the MySQL server. Is it running?"
    return f"Database error: {err.msg}"


class Database:
    def __init__(self, params: dict, pool_size: int = 5):
        self.params = params
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name="symposium_pool",
                pool_size=pool_size,
                autocommit=False,
                **params,
            )
        except mysql.connector.Error as err:
            raise DatabaseError(friendly_error(err)) from err

    @contextmanager
    def cursor(self, dictionary: bool = True):
        """Yield a cursor inside a transaction: commit on success, rollback on error."""
        conn = self._pool.get_connection()
        cur = conn.cursor(dictionary=dictionary)
        try:
            yield cur
            conn.commit()
        except mysql.connector.Error as err:
            conn.rollback()
            raise DatabaseError(friendly_error(err)) from err
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()          # returns the connection to the pool

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        with self.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            cur.fetchall()        # drain any remaining rows
            return row

    def scalar(self, sql: str, params: tuple = ()):
        row = self.fetch_one(sql, params)
        return next(iter(row.values())) if row else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Run INSERT/UPDATE/DELETE. Returns lastrowid for inserts, else rowcount."""
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid or cur.rowcount

    def call_proc(self, name: str, args: tuple) -> tuple:
        with self.cursor(dictionary=False) as cur:
            return cur.callproc(name, args)

    def read_only_query(self, sql: str) -> tuple[list[str], list[tuple]]:
        """Run an ad-hoc query in a READ ONLY transaction (for the SQL console)."""
        conn = self._pool.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("START TRANSACTION READ ONLY")
            cur.execute(sql)
            if cur.description is None:
                return [], []
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(1000)
            cur.fetchall()
            return cols, rows
        except mysql.connector.Error as err:
            raise DatabaseError(friendly_error(err)) from err
        finally:
            try:
                conn.rollback()
            finally:
                cur.close()
                conn.close()


_db: Database | None = None


def init(params: dict) -> Database:
    global _db
    _db = Database(params)
    return _db


def get() -> Database:
    if _db is None:
        raise DatabaseError("Database is not initialised.")
    return _db


def test_connection(params: dict, with_database: bool = True) -> tuple[bool, str]:
    p = dict(params)
    if not with_database:
        p.pop("database", None)
    try:
        conn = mysql.connector.connect(connection_timeout=5, **p)
        version = conn.get_server_info()
        conn.close()
        return True, f"Connected to MySQL {version}"
    except mysql.connector.Error as err:
        return False, friendly_error(err)


def schema_ready(params: dict) -> bool:
    try:
        conn = mysql.connector.connect(connection_timeout=5, **params)
        cur = conn.cursor()
        cur.execute("SHOW TABLES LIKE 'app_user'")
        ok = cur.fetchone() is not None
        conn.close()
        return ok
    except mysql.connector.Error:
        return False
