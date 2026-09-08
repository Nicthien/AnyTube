"""Bounded discovery diagnostics; no documents, request headers or cookies."""
from contextvars import ContextVar
from contextlib import contextmanager
import time

sink = ContextVar('source_diagnostic_sink', default=None)
context = ContextVar('source_diagnostic_context', default={})
confirmation = ContextVar('source_endpoint_confirmation',default=None)

class ControlError(ValueError):
    def __init__(self, code, message, correctable=False):
        self.code, self.correctable = code, correctable
        super().__init__(message)

def emit(**values):
    callback=sink.get()
    if callback:
        from app.source_assistant import safe_text
        def scrub(value):
            if isinstance(value,str):return safe_text(value,2000)
            if isinstance(value,list):return [scrub(v) for v in value[:3]]
            if isinstance(value,dict):return {k:scrub(v) for k,v in value.items()}
            return value
        callback(scrub({'time':time.time(),**context.get(),**values}))

@contextmanager
def scope(**values):
    token=context.set({**context.get(),**values})
    try:yield
    finally:context.reset(token)

def identity(candidate):
    from app.connectors import Connector
    from app.pagination import signature
    return signature(Connector.model_validate(candidate).model_dump())

class Attempts:
    def __init__(self,browser=False):
        self.seen=set();self.initial=0;self.corrections=0
        self.http_limit=2 if browser else 3
    def claim(self,candidate,*,browser=False,correction=False):
        key=identity(candidate)
        if key in self.seen:
            emit(candidate_id=key,phase='candidate',outcome='skipped',code='duplicate',message='Configuration identique déjà contrôlée ; aucune requête relancée.')
            return False
        if correction:
            if self.corrections>=2:return False
            self.corrections+=1
        else:
            if self.initial >= (3 if browser else self.http_limit):return False
            self.initial+=1
        self.seen.add(key)
        return True

NEXT_ACTIONS={
    'error_page':'L’endpoint aboutit à une page d’erreur ; vérifiez l’URL issue du formulaire.',
    'access_required':'La page demande un accès ; aucun ajout automatique possible.',
    'ambiguous':'Précisez un exemple de recherche ; la réponse reste ambiguë.',
    'unstable_results':'Les listes sont instables ; vérifiez qu’elles proviennent de la recherche.',
    'empty_results':'Précisez un terme de contrôle présent dans le catalogue ou ajoutez un exemple de recherche.',
    'same_results':'Vérifiez le formulaire et le paramètre qui transmet le terme de recherche.',
    'witness_repeated':'Le témoin reproduit les résultats ordinaires ; vérifiez que le terme est bien transmis.',
    'endpoint_unconfirmed':'Fournissez une URL issue du formulaire avec le terme utilisé.',
    'network_unavailable':'Vérifiez la disponibilité du site ou du service avant de relancer.',
    'missing_fields':'Précisez les sélecteurs de titre et de lien du candidat.',
    'pagination_repeated':'Corrigez la pagination ou limitez explicitement la recherche à la première page.',
    'video_evidence_missing':'Les pages restent non confirmées ; consultez les preuves et les exemples disponibles.',
    'unsupported_form':'Une recherche POST ou sans URL GET reproductible nécessite un connecteur dédié.'
}
