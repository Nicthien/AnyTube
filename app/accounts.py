"""Private account lifecycle. No public registration; tokens are hashed at rest."""
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from app.store import connect, owner

router = APIRouter()
passwords = PasswordHasher()
DUMMY = passwords.hash(secrets.token_urlsafe(32))
COOKIE = 'anytube_session'


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def initialize_accounts(app):
    with connect() as db:
        if not db.execute('SELECT 1 FROM users').fetchone():
            token = secrets.token_urlsafe(32)
            db.execute("INSERT OR REPLACE INTO settings VALUES ('setup_token',?)", (digest(token),))
            app.state.setup_token = token
            logging.getLogger('anytube').warning('Installation AnyTube : jeton à usage unique %s', token)
        else:
            app.state.setup_token = None


def authenticate(request):
    token = request.cookies.get(COOKIE, '')
    if not token:
        return None
    with connect() as db:
        row = db.execute('SELECT u.* FROM users u JOIN sessions s ON s.owner=u.id WHERE s.token=? AND s.expires>? AND u.disabled=0', (digest(token), time.time())).fetchone()
    return dict(row) if row else None


def public_user(user):
    return {key:user[key] for key in ('id','name','admin','quota')}


def session(response, user, request):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (digest(token), user, time.time()+30*86400, time.time()))
    secure = os.environ.get('ANYTUBE_PUBLIC_URL', '').startswith('https://') or request.url.scheme == 'https'
    response.set_cookie(COOKIE, token, max_age=30*86400, httponly=True, secure=secure, samesite='strict', path='/')


def rate_limit(request):
    key = request.client.host if request.client else 'unknown'
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM attempts WHERE until<?', (time.time(),))
        row = db.execute('SELECT count FROM attempts WHERE key=?', (key,)).fetchone()
        if row and row['count'] >= 20:
            raise HTTPException(429, 'Trop de tentatives. Réessayez dans 15 minutes.')
        db.execute('INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key,time.time()+900))


def require_admin():
    with connect() as db:
        user = db.execute('SELECT * FROM users WHERE id=? AND admin=1 AND disabled=0', (owner(),)).fetchone()
    if not user:
        raise HTTPException(403, 'Accès administrateur requis.')


class Credentials(BaseModel):
    name: str = Field(min_length=2,max_length=80,pattern=r'^[\w .@-]+$')
    password: str = Field(min_length=12,max_length=200)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError('Le nom doit contenir au moins deux caractères.')
        return value


class Enrollment(Credentials):
    token: str = Field(min_length=1,max_length=150)


@router.get('/api/account/me')
def me(request: Request):
    user = authenticate(request)
    with connect() as db:
        setup = not bool(db.execute('SELECT 1 FROM users').fetchone())
    return {'user':public_user(user) if user else None,'setup_required':setup,'preferences':json.loads(user['prefs']) if user else {}}


@router.post('/api/account/setup')
def setup(body: Enrollment, request: Request, response: Response):
    rate_limit(request)
    encoded = passwords.hash(body.password)
    user = secrets.token_hex(16)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        token = db.execute("SELECT value FROM settings WHERE key='setup_token'").fetchone()
        if db.execute('SELECT 1 FROM users').fetchone() or not token or not secrets.compare_digest(token['value'], digest(body.token)):
            raise HTTPException(400, 'Jeton invalide ou installation déjà terminée.')
        db.execute('INSERT INTO users(id,name,password,admin) VALUES (?,?,?,1)',(user,body.name.strip(),encoded))
        db.execute("UPDATE sources SET owner=? WHERE owner=''",(user,))
        db.execute("DELETE FROM settings WHERE key='setup_token'")
    session(response,user,request)
    request.app.state.setup_token = None
    return {'ok':True}


@router.post('/api/account/join')
def join(body: Enrollment, request: Request, response: Response):
    rate_limit(request)
    encoded = passwords.hash(body.password)
    user = secrets.token_hex(16)
    try:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            invitation = db.execute('SELECT token FROM invitations WHERE token=? AND expires>?',(digest(body.token),time.time())).fetchone()
            if not invitation:
                raise HTTPException(400,'Invitation invalide ou expirée.')
            db.execute('INSERT INTO users(id,name,password) VALUES (?,?,?)',(user,body.name.strip(),encoded))
            db.execute('DELETE FROM invitations WHERE token=?',(digest(body.token),))
    except sqlite3.IntegrityError:
        raise HTTPException(409,'Ce nom est déjà utilisé.')
    session(response,user,request)
    return {'ok':True}


@router.post('/api/account/login')
def login(body: Credentials, request: Request, response: Response):
    rate_limit(request)
    with connect() as db:
        row = db.execute('SELECT * FROM users WHERE name=? COLLATE NOCASE',(body.name.strip(),)).fetchone()
    try:
        valid = passwords.verify(row['password'] if row else DUMMY, body.password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or not row or row['disabled']:
        raise HTTPException(401,'Identifiants incorrects.')
    session(response,row['id'],request)
    return {'ok':True}


@router.post('/api/account/logout')
def logout(request: Request, response: Response):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE token=?',(digest(request.cookies.get(COOKIE,'')),))
    response.delete_cookie(COOKIE,path='/')
    return {'ok':True}


@router.post('/api/admin/invitations')
def invitation():
    require_admin()
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('INSERT INTO invitations VALUES (?,?,?)',(digest(token),time.time()+7*86400,time.time()))
    return {'token':token,'expires_in_days':7}


@router.delete('/api/account/sessions')
def revoke_sessions(response: Response):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE owner=?',(owner(),))
    response.delete_cookie(COOKIE,path='/')
    return {'ok':True}


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=12,max_length=200)


@router.post('/api/account/password')
def change_password(body: PasswordChange,request: Request,response: Response):
    rate_limit(request)
    with connect() as db:
        row = db.execute('SELECT password FROM users WHERE id=?',(owner(),)).fetchone()
        try:
            passwords.verify(row['password'],body.current_password)
        except (VerificationError, InvalidHashError):
            raise HTTPException(400,'Mot de passe actuel incorrect.')
        db.execute('UPDATE users SET password=? WHERE id=?',(passwords.hash(body.new_password),owner()))
        db.execute('DELETE FROM sessions WHERE owner=?',(owner(),))
    session(response,owner(),request)
    return {'ok':True}


class Preferences(BaseModel):
    theme: str = Field(default='dark',pattern='^(dark|light)$')
    sponsor: bool = True
    selected: list[str] | None = Field(default=None,max_length=100)
    ranking: str = Field(default='default',pattern='^(default|trending|views|recent)$')


@router.put('/api/account/preferences')
def preferences(body: Preferences):
    with connect() as db:
        db.execute('UPDATE users SET prefs=? WHERE id=?',(body.model_dump_json(),owner()))
    return {'ok':True}


@router.get('/api/admin/users')
def users():
    require_admin()
    with connect() as db:
        return {'items':[dict(row) for row in db.execute('SELECT id,name,admin,disabled,quota FROM users ORDER BY name')]}


class UserEdit(BaseModel):
    disabled: bool
    quota: int = Field(ge=500*1024*1024,le=100*1024**4)


@router.patch('/api/admin/users/{key}')
async def edit_user(key: str,body: UserEdit):
    require_admin()
    if key == owner() and body.disabled:
        raise HTTPException(400,'Vous ne pouvez pas désactiver votre propre compte.')
    with connect() as db:
        allocated = 0
        for row in db.execute('SELECT payload FROM media WHERE owner=?', (key,)):
            job = json.loads(row['payload'])
            if job.get('destination') == 'library':
                allocated += job.get('size',0) if job['status'] == 'ready' else job.get('reserved',0) if job['status'] == 'preparing' else 0
        if body.quota < allocated:
            raise HTTPException(409, 'Quota inférieur aux vidéos conservées et aux préparations réservées. Libérez de l’espace avant de le réduire.')
        if not db.execute('UPDATE users SET disabled=?,quota=? WHERE id=?',(body.disabled,body.quota,key)).rowcount:
            raise HTTPException(404,'Compte introuvable.')
        if body.disabled:
            db.execute('DELETE FROM sessions WHERE owner=?',(key,))
    return {'ok':True}
