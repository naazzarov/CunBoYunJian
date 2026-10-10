import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import os

DATA=Path(os.getenv('CLIPFORGE_DATA','data')).resolve()
DATA.mkdir(parents=True,exist_ok=True)

@contextmanager
def db():
    conn=sqlite3.connect(DATA/'workspace.sqlite3',timeout=30)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback(); raise
    finally: conn.close()

def init():
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS knowledge(id INTEGER PRIMARY KEY,title TEXT NOT NULL,content TEXT NOT NULL,kind TEXT NOT NULL,category TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,title TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,progress INTEGER DEFAULT 0,error TEXT,config TEXT NOT NULL,duration REAL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,plan TEXT DEFAULT '[]',snapshot TEXT DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),clip_index INTEGER NOT NULL,decision TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(job_id,clip_index));
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,reviewer_id TEXT NOT NULL,name TEXT NOT NULL,expires_at REAL NOT NULL);
        ''')

        # Preserve existing reviews while removing the old one-review-per-clip constraint.
        columns={row['name'] for row in c.execute('PRAGMA table_info(feedback)')}
        if 'reviewer_id' not in columns:
            c.execute('ALTER TABLE feedback RENAME TO feedback_legacy')
            c.execute("CREATE TABLE feedback(id INTEGER PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),clip_index INTEGER NOT NULL,decision TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,reviewer_id TEXT NOT NULL DEFAULT 'legacy',reviewer_name TEXT NOT NULL DEFAULT 'Previous reviewer',UNIQUE(job_id,clip_index,reviewer_id))")
            c.execute('INSERT INTO feedback(id,job_id,clip_index,decision,note,created_at) SELECT id,job_id,clip_index,decision,note,created_at FROM feedback_legacy')
            c.execute('DROP TABLE feedback_legacy')

def update(job_id,**values):
    with db() as c: c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',list(values.values())+[job_id])

def job(job_id):
    with db() as c: r=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not r: return None
    value=dict(r)
    for k in ['config','plan','snapshot']: value[k]=json.loads(value[k])
    return value

def cards():
    with db() as c: return [dict(r) for r in c.execute('SELECT * FROM knowledge ORDER BY id DESC')]
