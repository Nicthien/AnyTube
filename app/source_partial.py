"""Explicit partial acceptance with fresh proofs and transactional source updates."""
import json
import time
import uuid
from urllib.parse import urlsplit
from fastapi import HTTPException
from app.store import connect, owner
from app.connectors import Connector, default_connector
from app.pagination import signature
from app.verification import engine_version
from app.source_pages import summarize


def accept(identifier):
    from app.source_assistant import load, update, ACTIVE
    job=load(identifier)
    if job.get('partial_accepted') and job['status'] in ('added','updated'):return job
    evidence=job.get('evidence',{})
    try:candidate=Connector.model_validate(job.get('candidate')).model_dump()
    except ValueError:raise HTTPException(409,'Configuration invalide ; reprenez la découverte.')
    if (job['status'] in ACTIVE or not summarize(evidence)['eligible_partial'] or
        evidence.get('engine')!=engine_version() or evidence.get('configuration_signature')!=signature(candidate) or
        not 0<=time.time()-evidence.get('date',0)<86400):
        raise HTTPException(409,'Preuves insuffisantes, périmées ou moteur modifié ; reprenez la découverte.')
    summary=summarize(evidence)
    qualification={'search':'verified','pagination':evidence['pagination'],'level':'partial','date':evidence['date'],'engine':evidence['engine'],'page_summary':summary,'playback':'unverified'}
    source_id=job.get('source_id')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if source_id:
            row=db.execute('SELECT connector FROM sources WHERE owner=? AND id=?',(owner(),source_id)).fetchone()
            old=json.loads(row[0]) if row and row[0] else default_connector(source_id) if row else None
            if old!=job.get('baseline'):raise HTTPException(409,'La source a changé ; reprenez la découverte.')
            db.execute('INSERT INTO source_assistant_backups VALUES (?,?,?,?,?)',(uuid.uuid4().hex,owner(),source_id,time.time(),json.dumps(old)))
            db.execute('UPDATE sources SET connector=? WHERE owner=? AND id=?',(json.dumps(candidate),owner(),source_id))
        else:
            host=urlsplit(job.get('resolved_target') or job['target']).hostname or job['target']
            source_id='custom-'+signature([host,candidate])[:24]
            for row in db.execute('SELECT id,connector FROM sources WHERE owner=?',(owner(),)):
                try:existing=Connector.model_validate(json.loads(row['connector']) if row['connector'] else default_connector(row['id'])).model_dump()
                except ValueError:continue
                if signature(existing)==signature(candidate):source_id=row['id'];break
            else:db.execute('INSERT INTO sources(id,name,connector,owner) VALUES (?,?,?,?)',(source_id,host,json.dumps(candidate),owner()))
        db.execute('INSERT OR REPLACE INTO source_validation VALUES (?,?,?,?)',(owner(),source_id,signature(candidate),json.dumps(qualification)))
        # Source and accepted task state are committed atomically, including repeat clicks.
        job.update(status='updated' if job.get('source_id') else 'added',added_source=source_id,partial_accepted=True,
                   message='Source enregistrée avec validation partielle ; lecture non vérifiée.')
        payload={k:v for k,v in job.items() if k not in ('id','owner','status','created','updated')}
        db.execute('UPDATE source_assistant_jobs SET status=?,updated=?,payload=? WHERE id=? AND owner=?',
                   (job['status'],time.time(),json.dumps(payload),identifier,owner()))
    return load(identifier)
