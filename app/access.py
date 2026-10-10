"""Expiring, revocable sessions for one trusted testing group."""
import hashlib
import hmac
import secrets
import time
import uuid
from . import store


def digest(value,key):
    return hmac.new(key.encode(),value.encode(),hashlib.sha256).hexdigest()


def issue(name,key,ttl=86400):
    token=secrets.token_urlsafe(32)
    identity=uuid.uuid4().hex
    with store.db() as c:
        c.execute('DELETE FROM sessions WHERE expires_at<=?',(time.time(),))
        c.execute('INSERT INTO sessions(token_hash,reviewer_id,name,expires_at) VALUES(?,?,?,?)',(digest(token,key),identity,name,time.time()+ttl))
    return token,{'id':identity,'name':name}


def resolve(token,key):
    if not token:return None
    with store.db() as c:
        row=c.execute('SELECT reviewer_id,name FROM sessions WHERE token_hash=? AND expires_at>?',(digest(token,key),time.time())).fetchone()
    return {'id':row['reviewer_id'],'name':row['name']} if row else None


def revoke(token,key):
    with store.db() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(digest(token,key),))
