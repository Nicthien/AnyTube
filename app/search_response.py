"""Classify search responses before interpreting their listings."""
import re
import json
from urllib.parse import urlsplit, unquote
from app.source_diagnostics import ControlError, emit


def classify(text, url, status=None, content_type=''):
    path=unquote(urlsplit(url).path).lower()
    status=status if isinstance(status,int) else None
    if status in (401,403,429) or re.search(r'/(?:login|signin|captcha)(?:[/.]|$)',path):
        return 'access_required','Accès ou vérification requis.'
    if (status is not None and status>=400) or re.search(r'/(?:errors?|404|not[-_]found)(?:[/.]|$)',path):
        return 'error_page','La réponse est une page d’erreur, même si son statut est HTTP 200.'
    if text.lstrip().startswith(('{','[')):
        try:
            data=json.loads(text)
        except ValueError:
            return 'ambiguous','Réponse structurée illisible : recherche non confirmée.'
        if isinstance(data,dict) and (data.get('error') or data.get('errors') or data.get('success') is False):
            return 'error_page','La réponse structurée signale une erreur.'
        return 'usable','Réponse structurée à contrôler.'
    from app.html_search import document
    soup=document(text)
    gate = access_gate(soup)
    if gate:
        return 'access_required', gate['reason']
    headings=[n.get_text(' ',strip=True)[:300].lower() for n in soup.select('title, h1',limit=8)]
    error=r'(?:404|page not found|video (?:not found|missing)|invalid search(?: type)?|page introuvable|une erreur est survenue|an error (?:has )?occurred)'
    access=r'(?:access denied|sign in to continue|verify you are human|vérifiez que vous êtes humain|connexion requise)'
    if any(re.search(access,h) for h in headings):return 'access_required','La page demande un accès ou une vérification.'
    if any(re.search(error,h) for h in headings):return 'error_page','Le titre principal indique une erreur.'
    main=soup.find('main') or soup.find(attrs={'role':'main'})
    if main:
        # Exclude card text: an error mentioned by a result is not a page error.
        for node in main.select('article, li, a, script, style'):node.decompose()
        lead=main.get_text(' ',strip=True)[:500].lower()
        if re.match(error,lead):return 'error_page','Le contenu principal indique une erreur.'
        if re.match(access,lead):return 'access_required','Le contenu principal demande un accès.'
    if not text.strip():return 'ambiguous','Réponse vide : recherche non confirmée.'
    return 'usable','Aucune page d’erreur identifiée ; contrôles de recherche encore nécessaires.'


def access_gate(soup):
    """Inspect dominant headings and visible modal text, not video-result titles."""
    patterns = (
        ('age_verification', r'verify (?:your )?age|age verification|vérification d[’\x27]âge|confirmez votre âge|confirm (?:you are|your age)|18 years (?:old|of age)',
         'Vérification d’âge demandée. Ouvrez la session pour effectuer vous-même cette vérification.'),
        ('human_verification', r'verify you are human|vérifiez que vous êtes humain|complete the captcha',
         'Vérification humaine demandée.'),
        ('login', r'sign in to continue|log in to continue|connexion requise', 'Connexion demandée par le site.'),
        ('consent', r'accept cookies to continue|acceptez les cookies pour continuer', 'Consentement demandé par le site.'),
    )
    for node in soup.select('title,h1,dialog[open],[role="dialog"],[aria-modal="true"]', limit=20):
        if node.has_attr('hidden') or node.get('aria-hidden') == 'true':
            continue
        style = node.get('style', '').replace(' ', '').lower()
        if 'display:none' in style or 'visibility:hidden' in style:
            continue
        text = node.get_text(' ', strip=True)[:1500].lower()
        for kind, pattern, reason in patterns:
            if re.search(pattern, text):
                return {'type': kind, 'reason': reason}
    return None


def require_usable(text,url,status=None,content_type=''):
    category,reason=classify(text,url,status,content_type)
    emit(classification=category,classification_reason=reason,final_url=url,http_status=status if isinstance(status,int) else None,
         outcome='observed' if category=='usable' else 'failed',code='' if category=='usable' else category,message=reason)
    if category!='usable':raise ControlError(category,reason)
