"""Data-access layer: connection pool, automatic reconnect, friendly errors.

All SQL uses %s placeholders (no string building with user input).
"""
import logging
import threading
import time
from contextlib import contextmanager

import mysql.connector
from mysql.connector import errorcode, pooling
from mysql.connector.errors import PoolError

log = logging.getLogger(__name__)

TRANSIENT = {2006, 2013, 2055, 2003, 2014}      # server gone away / lost connection / cannot connect


class DatabaseError(Exception):
    """An error safe to show to the user."""


def friendly_error(err: mysql.connector.Error) -> str:
    if getattr(err, "sqlstate", None) == "45000":         # SIGNAL from triggers / procedures
        return err.msg
    code = getattr(err, "errno", None)
    msg = (err.msg or "").lower()
    if code == errorcode.ER_DUP_ENTRY:
        if "uq_user_email" in msg:
            return "An account with this e-mail already exists."
        if "uq_event_name" in msg:
            return "An event with this name already exists."
        if "uq_reg_user_event" in msg:
            return "You are already registered for this event."
        if "uq_payment_utr" in msg:
            return "This UPI reference number has already been used."
        if "uq_coupon_code" in msg:
            return "A coupon with this code already exists."
        if "primary" in msg and "event_result" in msg:
            return "That position has already been awarded for this event."
        return "This record already exists."
    if code in (errorcode.ER_ROW_IS_REFERENCED, errorcode.ER_ROW_IS_REFERENCED_2):
        return "This record is used elsewhere and cannot be deleted."
    if code in (errorcode.ER_NO_REFERENCED_ROW, errorcode.ER_NO_REFERENCED_ROW_2):
        return "A referenced record does not exist."
    if code == errorcode.ER_CHECK_CONSTRAINT_VIOLATED:
        return "One of the values is not allowed. Please check the form."
    if code in TRANSIENT:
        return "The database is temporarily unavailable. Please try again in a moment."
    log.error("Unhandled MySQL error %s: %s", code, err.msg)
    return "A database error occurred. Please try again."


class Database:
    def __init__(self, params: dict, pool_size: int = 10, name: str = "main"):
        self.params = params
        self.pool_size = pool_size
        self.name = name
        self._lock = threading.Lock()
        self._pool = None
        self._make_pool()

    def _make_pool(self):
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name=f"sym_{self.name}_{id(self)}", pool_size=self.pool_size,
                pool_reset_session=True, autocommit=False, time_zone="+05:30",
                connection_timeout=10, **self.params)
        except mysql.connector.Error as err:
            self._pool = None
            raise DatabaseError(friendly_error(err)) from err

    def _connection(self):
        """Get a live pooled connection, rebuilding the pool / reconnecting if MySQL restarted."""
        last = None
        for attempt in range(8):
            try:
                with self._lock:
                    if self._pool is None:
                        self._make_pool()
                    conn = self._pool.get_connection()
                if not conn.is_connected():
                    conn.reconnect(attempts=2, delay=1)
                return conn
            except PoolError as err:                        # pool exhausted - wait briefly
                last = err
                time.sleep(0.1 * (attempt + 1))
            except (mysql.connector.Error, DatabaseError) as err:
                last = err
                log.warning("DB connection attempt %s failed: %s", attempt + 1, err)
                with self._lock:
                    self._pool = None
                time.sleep(0.5 * (attempt + 1))
        if isinstance(last, mysql.connector.Error):
            raise DatabaseError(friendly_error(last)) from last
        raise DatabaseError("The database is temporarily unavailable. Please try again in a moment.")

    @contextmanager
    def transaction(self, dictionary: bool = True):
        """Yields a cursor; commits on success, rolls back on any error."""
        conn = self._connection()
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
            try:
                cur.close()
            finally:
                conn.close()

    # -- helpers ---------------------------------------------------------
    def all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.transaction() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        with self.transaction() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            cur.fetchall()
            return row

    def value(self, sql: str, params: tuple = ()):
        row = self.one(sql, params)
        return next(iter(row.values())) if row else None

    def run(self, sql: str, params: tuple = ()) -> int:
        """INSERT/UPDATE/DELETE - returns lastrowid for inserts, else affected rows."""
        with self.transaction() as cur:
            cur.execute(sql, params)
            return cur.lastrowid or cur.rowcount

    def call(self, proc: str, args: tuple) -> tuple:
        with self.transaction(dictionary=False) as cur:
            return cur.callproc(proc, args)

    def read_only_query(self, sql: str, limit: int = 500) -> tuple[list[str], list[tuple]]:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute("SET SESSION MAX_EXECUTION_TIME = 5000")
            cur.execute("START TRANSACTION READ ONLY")
            cur.execute(sql)
            if cur.description is None:
                return [], []
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(limit)
            cur.fetchall()
            return cols, rows
        except mysql.connector.Error as err:
            if getattr(err, "errno", None) in (errorcode.ER_TABLEACCESS_DENIED_ERROR,
                                               errorcode.ER_COLUMNACCESS_DENIED_ERROR):
                raise DatabaseError("Access denied - that table or column is private.") from err
            raise DatabaseError(err.msg) from err
        finally:
            try:
                conn.rollback()
            finally:
                cur.close()
                conn.close()

    def ping(self) -> bool:
        try:
            return self.value("SELECT 1") == 1
        except DatabaseError:
            return False


_main: Database | None = None
_readonly: Database | None = None


def init(params: dict, readonly_params: dict | None = None) -> None:
    global _main, _readonly
    _main = Database(params, name="main")
    _readonly = None
    if readonly_params and readonly_params.get("password"):
        try:
            _readonly = Database(readonly_params, pool_size=2, name="ro")
        except DatabaseError as exc:
            log.warning("Read-only DB user unavailable: %s", exc)


def get() -> Database:
    if _main is None:
        raise DatabaseError("Database is not configured.")
    return _main


def readonly() -> Database | None:
    return _readonly
