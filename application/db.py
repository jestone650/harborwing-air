"""
Database access layer.

* Settings come from environment variables / .env (never hard-coded).
* Every query uses %s placeholders -> PyMySQL sends values separately
  from the SQL text (parameterized queries, no SQL injection).
* `transaction()` groups several statements so they all succeed or all fail.
"""
import contextlib
import os

import pymysql
from dotenv import load_dotenv
from flask import g
from pymysql.cursors import DictCursor

load_dotenv()


def get_connection():
    """One connection per web request, stored on flask.g."""
    if "db" not in g:
        g.db = pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "harborwing"),
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True,          # single statements commit immediately
        )
    return g.db


def close_connection(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, params=()):
    """Run a SELECT and return a list of dict rows."""
    with get_connection().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql, params=()):
    row = query_one(sql, params)
    return next(iter(row.values())) if row else None


def execute(sql, params=()):
    """Run INSERT/UPDATE/DELETE. Returns (lastrowid, rowcount)."""
    with get_connection().cursor() as cur:
        cur.execute(sql, params)
        return cur.lastrowid, cur.rowcount


@contextlib.contextmanager
def transaction():
    """
    with transaction() as cur:
        cur.execute(...); cur.execute(...)
    -> COMMIT if the block finishes, ROLLBACK if anything raises.
    """
    conn = get_connection()
    conn.begin()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# MySQL error numbers -> messages an employee can understand
FRIENDLY_ERRORS = {
    1062: "That record already exists (duplicate value or duplicate link).",
    1451: "This record cannot be deleted or changed because other records still use it.",
    1452: "A referenced record (for example an airport, passenger or date) does not exist.",
    3819: "A business rule was violated (for example: amount must be positive, "
          "origin and destination must differ, or dates are in the wrong order).",
    1406: "One of the values is too long for its field.",
    1048: "A required field is missing.",
}


def friendly_error(exc):
    code = exc.args[0] if exc.args else None
    if code in (2003, 1045, 1049):
        return "Cannot connect to the database. Check DB_HOST, DB_USER, DB_PASSWORD and DB_NAME in .env."
    return FRIENDLY_ERRORS.get(code, f"Database error ({code}). The change was not saved.")
