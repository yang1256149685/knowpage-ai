import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def db_path():
    return Path(os.getenv('KNOWPAGE_DB', 'data/knowpage.db'))


@contextmanager
def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    with connect() as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > 1:
            raise RuntimeError('Database schema is newer than this application')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','reader')));
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,title TEXT NOT NULL,category TEXT NOT NULL,filename TEXT NOT NULL,text TEXT NOT NULL,hash TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,ordinal INTEGER NOT NULL,text TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,question TEXT NOT NULL,answer TEXT NOT NULL,mode TEXT NOT NULL,sources TEXT NOT NULL,created_at TEXT NOT NULL);
        PRAGMA user_version=1;
        ''')
