import json
import os
import time
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.store import connect, data_dir, owner
from app.accounts import require_admin

router = APIRouter()
DEFAULT_LIMITS = {'cache_bytes':10*1024**3,'cache_hours':24,'preparations':1,'media_bytes':500*1024**2,'max_height':720}


def media_root():
    path = Path(os.environ.get('ANYTUBE_MEDIA', str(data_dir() / 'media'))).resolve()
    path.mkdir(parents=True,exist_ok=True)
    return path


def job_folder(job):
    return media_root() / job.get('destination','cache') / job['owner'] / job['id']


def job_file(job):
    name = job.get('filename', 'video.mp4')
    if name not in ('video.mp4', 'audio.m4a'):
        raise ValueError('Nom de fichier média invalide.')
    return job_folder(job) / name


def persist(job):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO media VALUES (?,?,?)',(job['id'],job['owner'],json.dumps(job)))


def remove_record(key):
    with connect() as db:
        db.execute('DELETE FROM media WHERE id=?',(key,))


def restore_jobs():
    with connect() as db:
        entries = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM media')]
    for job in entries:
        if job['status'] == 'preparing':
            job.update(status='error',error='Préparation interrompue par un redémarrage. Vous pouvez réessayer.')
            shutil.rmtree(job_folder(job), ignore_errors=True)
            persist(job)
        elif job['status'] == 'ready' and not job_file(job).is_file():
            job.update(status='error',error='Fichier absent du stockage.')
            persist(job)
    return {job['id']:job for job in entries}


def limits():
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key='limits'").fetchone()
    return {**DEFAULT_LIMITS, **(json.loads(row['value']) if row else {})}


class Limits(BaseModel):
    cache_bytes: int = Field(default=10*1024**3,ge=500*1024**2,le=100*1024**4)
    cache_hours: int = Field(default=24,ge=1,le=720)
    preparations: int = Field(default=1,ge=1,le=4)
    media_bytes: int = Field(default=500*1024**2,ge=1024**2,le=10*1024**3)
    max_height: int = Field(default=720,ge=144,le=2160)


@router.get('/api/admin/limits')
def get_limits():
    require_admin()
    return limits()


@router.put('/api/admin/limits')
async def set_limits(body: Limits):
    require_admin()
    with connect() as db:
        allocated = 0
        for row in db.execute('SELECT payload FROM media'):
            job = json.loads(row['payload'])
            if job.get('destination','cache') == 'cache':
                allocated += job.get('size',0) if job['status'] == 'ready' else job.get('reserved',0) if job['status'] == 'preparing' else 0
        if body.cache_bytes < allocated:
            raise HTTPException(409, 'Limite inférieure au cache utilisé et aux préparations réservées. Libérez le cache avant de la réduire.')
        db.execute("INSERT OR REPLACE INTO settings VALUES ('limits',?)",(body.model_dump_json(),))
    return limits()


class Personal(BaseModel):
    url: str = Field(min_length=1,max_length=2000,pattern=r'^https?://')
    title: str = Field(default='',max_length=500)
    favorite: bool | None = None
    position: float | None = Field(default=None,ge=0,le=10000000,allow_inf_nan=False)


@router.put('/api/personal')
def save_personal(body: Personal):
    with connect() as db:
        db.execute('INSERT INTO personal(owner,url,title,updated) VALUES (?,?,?,?) ON CONFLICT(owner,url) DO UPDATE SET title=excluded.title,updated=excluded.updated',(owner(),body.url,body.title,time.time()))
        if body.favorite is not None:
            db.execute('UPDATE personal SET favorite=? WHERE owner=? AND url=?',(body.favorite,owner(),body.url))
        if body.position is not None:
            db.execute('UPDATE personal SET position=? WHERE owner=? AND url=?',(body.position,owner(),body.url))
    return {'ok':True}


@router.get('/api/personal')
def personal():
    with connect() as db:
        return {'items':[dict(row) for row in db.execute('SELECT url,title,favorite,position,updated FROM personal WHERE owner=? ORDER BY updated DESC LIMIT 1000',(owner(),))]}


@router.delete('/api/personal')
def clear_history():
    with connect() as db:
        db.execute('DELETE FROM personal WHERE owner=? AND favorite=0',(owner(),))
        db.execute('UPDATE personal SET position=0 WHERE owner=?',(owner(),))
    return {'ok':True}
