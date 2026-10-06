from __future__ import annotations
import sqlite3, threading, secrets, hashlib, hmac
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .config import DB_PATH, settings

_lock = threading.RLock()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def connect():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    with _lock, connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS licenses (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          license_key TEXT UNIQUE NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          created_at TEXT NOT NULL,
          expires_at TEXT,
          notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS devices (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          license_id INTEGER NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
          hwid TEXT NOT NULL,
          label TEXT NOT NULL DEFAULT '',
          role TEXT NOT NULL DEFAULT 'agent',
          last_seen TEXT,
          created_at TEXT NOT NULL,
          UNIQUE(license_id, hwid)
        );
        CREATE TABLE IF NOT EXISTS sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          license_id INTEGER NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
          session_name TEXT NOT NULL,
          token_hash TEXT UNIQUE NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT,
          active INTEGER NOT NULL DEFAULT 1,
          state_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
          event_type TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        ''')

def hash_token(token):
    return hmac.new(settings.token_secret.encode(), token.encode(), hashlib.sha256).hexdigest()

def new_license(days=0, key=None):
    key = key or ('QZK-' + '-'.join(secrets.token_hex(3).upper() for _ in range(4)))
    created = datetime.now(timezone.utc)
    exp = None if days <= 0 else (created + timedelta(days=days)).isoformat()
    with _lock, connect() as c:
        c.execute('INSERT INTO licenses(license_key,created_at,expires_at) VALUES(?,?,?)', (key,created.isoformat(),exp))
        return c.execute('SELECT * FROM licenses WHERE license_key=?',(key,)).fetchone()

def list_licenses():
    with connect() as c:
        return c.execute('SELECT * FROM licenses ORDER BY id DESC').fetchall()

def get_license(key):
    with connect() as c:
        return c.execute('SELECT * FROM licenses WHERE license_key=?',(key,)).fetchone()

def valid_license(row):
    if not row or row['status'] != 'active': return False
    if row['expires_at']:
        return datetime.fromisoformat(row['expires_at']) > datetime.now(timezone.utc)
    return True

def register_device(license_key, hwid, label='', role='agent'):
    lic = get_license(license_key)
    if not valid_license(lic): return None
    with _lock, connect() as c:
        c.execute('''INSERT INTO devices(license_id,hwid,label,role,last_seen,created_at)
                     VALUES(?,?,?,?,?,?)
                     ON CONFLICT(license_id,hwid) DO UPDATE SET label=excluded.label, role=excluded.role, last_seen=excluded.last_seen''',
                  (lic['id'],hwid,label,role,now_iso(),now_iso()))
        return c.execute('SELECT * FROM devices WHERE license_id=? AND hwid=?',(lic['id'],hwid)).fetchone()

def touch_device(license_key, hwid):
    with _lock, connect() as c:
        c.execute('UPDATE devices SET last_seen=? WHERE license_id=(SELECT id FROM licenses WHERE license_key=?) AND hwid=?',(now_iso(),license_key,hwid))

def list_devices(license_key=None):
    with connect() as c:
        if license_key:
            return c.execute('''SELECT d.*,l.license_key FROM devices d JOIN licenses l ON l.id=d.license_id WHERE l.license_key=? ORDER BY d.id DESC''',(license_key,)).fetchall()
        return c.execute('''SELECT d.*,l.license_key FROM devices d JOIN licenses l ON l.id=d.license_id ORDER BY d.id DESC''').fetchall()

def create_session(license_key, name, days=0):
    lic=get_license(license_key)
    if not valid_license(lic): return None, None
    raw=secrets.token_urlsafe(32)
    created=datetime.now(timezone.utc)
    exp=None if days<=0 else (created+timedelta(days=days)).isoformat()
    import json
    with _lock, connect() as c:
        cur=c.execute('INSERT INTO sessions(license_id,session_name,token_hash,created_at,expires_at) VALUES(?,?,?,?,?)',(lic['id'],name,hash_token(raw),created.isoformat(),exp))
        row=c.execute('SELECT * FROM sessions WHERE id=?',(cur.lastrowid,)).fetchone()
        return row, raw

def get_session(token):
    with connect() as c:
        row=c.execute('''SELECT s.*,l.license_key,l.status license_status,l.expires_at license_expires_at
                         FROM sessions s JOIN licenses l ON l.id=s.license_id WHERE s.token_hash=?''',(hash_token(token),)).fetchone()
        if not row or not row['active'] or row['license_status']!='active': return None
        if row['expires_at'] and datetime.fromisoformat(row['expires_at']) <= datetime.now(timezone.utc): return None
        if row['license_expires_at'] and datetime.fromisoformat(row['license_expires_at']) <= datetime.now(timezone.utc): return None
        return row

def save_state(session_id, state):
    import json
    with _lock, connect() as c:
        c.execute('UPDATE sessions SET state_json=? WHERE id=?',(json.dumps(state,separators=(',',':')),session_id))

def load_state(row):
    import json
    try: return json.loads(row['state_json'])
    except Exception: return {}

def add_event(session_id, event_type, payload):
    import json
    with _lock, connect() as c:
        c.execute('INSERT INTO events(session_id,event_type,payload_json,created_at) VALUES(?,?,?,?)',(session_id,event_type,json.dumps(payload,separators=(',',':')),now_iso()))
