"""Owner-only diagnostic snapshots; explicit field allowlists, no raw payload export."""
import io
import json
import time
import zipfile
from fastapi.responses import Response

FIELDS = set('id status created updated target resolved_target minutes queries video_examples search_example_url search_example_query source_id parent_job message next_action elapsed_seconds deadline engine date search pagination unverified configuration_signature history_truncated diagnostics_version format_version total complete eligible_partial recognized_per_term counts recognized deleted access_required network_error unrecognized_player non_video unchecked terms url final_url requested_url title reason method http_status duration hints player_present metadata_present outcome phase candidate_id provenance code content_type classification classification_reason inspected_count selected_count valid_count card_index missing_field selector stability query count offset time browser_requests http_requests search_checks ai_calls skipped_attempts discovery_requests'.split())
CANDIDATE_FIELDS = set('kind search_url search_trending_url search_views_url search_recent_url query_escape method results_path results_total_path result_base_url duration_unit item_url video_url home_query home_kind home_url extractor prefix'.split())
FIELDS.update({'access_type', 'session_state', 'network_revision', 'remaining_seconds'})
NESTED = {
    'html': set('rendering items next_selector url_path_prefix'.split()),
    'pagination': set('mode parameter has_more_path maximum_results fixed_page_size first_page page_url_path initial_results_path'.split()),
    'mapping': set('id title url thumbnail description channel duration views published'.split()),
}


def clean(value):
    from app.source_assistant import safe_text
    if isinstance(value,str): return safe_text(value,4000)
    if isinstance(value,(bool,int,float)) or value is None: return value
    if isinstance(value,list): return [clean(v) for v in value[:400]]
    if isinstance(value,dict): return {k:clean(v) for k,v in value.items() if k in FIELDS or k in ('pages','page_summary','checks','urls','observations','examples','metrics','steps','diagnostics','evidence')}
    return None


def candidate_report(candidate):
    from app.source_assistant import safe_text
    result={k:clean(v) for k,v in candidate.items() if k in CANDIDATE_FIELDS}
    for key,allowed in NESTED.items():
        if isinstance(candidate.get(key),dict):result[key]={k:clean(v) for k,v in candidate[key].items() if k in allowed}
    if isinstance(candidate.get('html'),dict):
        for field in ('title','link','thumbnail','duration','description'):
            spec=candidate['html'].get(field)
            if isinstance(spec,dict): result['html'][field]={k:safe_text(v,500) for k,v in spec.items() if k in ('selector','attribute','path') and isinstance(v,str)}
    return result


def export_job(job, version):
    from app.verification import engine_version
    report={'export_engine':engine_version(),'report_version':1,'anytube_version':version,'exported_at':time.time(),
            'active':job['status'] in ('queued','running'), 'history_truncated':bool(job.get('history_truncated')),
            'job':clean(job), 'candidate':candidate_report(job.get('candidate') or {})}
    # Candidate is exported separately under its stricter schema.
    text=['Diagnostic AnyTube '+version, 'Tentative : '+job['id'], 'État : '+job['status'],
          'Instantané en cours : '+('oui' if report['active'] else 'non'),
          'Historique tronqué : '+('oui' if report['history_truncated'] else 'non'),
          'Titres, URL publiques et termes inclus. Secrets exclus. Lecture non vérifiée.', '']
    snapshot=report['job']
    text.extend(['Site : '+str(snapshot.get('target','')), 'Bilan : '+str(snapshot.get('message','')),
                 'Recherches : '+', '.join(snapshot.get('queries',[])),
                 'Tentative précédente : '+str(snapshot.get('parent_job') or 'aucune'),
                 'Durée (secondes) : '+str(snapshot.get('elapsed_seconds','en cours')), ''])
    text.extend(['Accès détecté : '+str(snapshot.get('access_type','non identifié')),
                 'Session : '+str(snapshot.get('session_state','aucune')),
                 'Révision réseau : '+str(snapshot.get('network_revision','indisponible')), ''])
    evidence=snapshot.get('evidence',{})
    labels={'recognized':'reconnue','deleted':'supprimée','access_required':'accès nécessaire',
            'network_error':'erreur réseau','unrecognized_player':'lecteur non reconnu','non_video':'contenu non vidéo','unchecked':'non contrôlée'}
    text.append('Recherche : '+str(evidence.get('search','non contrôlée'))+' ; pagination : '+str(evidence.get('pagination','non contrôlée')))
    text.append('Pages :')
    for page in evidence.get('pages',[]):
        text.append(' - '+page.get('url','')+' : '+labels.get(page.get('status'),'?')+' — '+page.get('reason',''))
    text.extend(['','Contrôles chronologiques :'])
    for index,row in enumerate(snapshot.get('diagnostics',[]),1):
        text.append(f"{index}. {row.get('phase','Contrôle')} — {row.get('message') or row.get('code') or row.get('outcome','')}")
        for key,label in (('requested_url','URL demandée'),('final_url','URL finale'),('query','Terme'),('http_status','HTTP'),('valid_count','Résultats valides')):
            if key in row:text.append('   '+label+' : '+str(row[key]))
    text.append('\nConfiguration et données complètes expurgées : diagnostic.json (dans cette archive).')
    if not job.get('diagnostics_version'):text.append('Diagnostic détaillé indisponible pour cette tentative.')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('resume.txt','\n'.join(text))
        archive.writestr('diagnostic.json',json.dumps(report,ensure_ascii=False,indent=2))
    return Response(output.getvalue(),media_type='application/zip',headers={
        'Content-Disposition':f'attachment; filename="anytube-diagnostic-{job["id"]}.zip"', 'Cache-Control':'no-store'})
