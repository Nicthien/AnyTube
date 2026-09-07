"""Public, bounded errors: provider output and credential values never leave workers."""
MESSAGES = {
    'authentication_required': 'La source demande une connexion. Vérifiez ses accès dans Mes sources.',
    'geo_restricted': 'Ce média est indisponible depuis la région du serveur.',
    'drm_protected': 'Ce média est protégé par DRM et ne peut pas être préparé.',
    'rate_limited': 'La plateforme limite les requêtes. Réessayez plus tard.',
    'unavailable_format': 'Aucun format compatible avec les limites choisies.',
    'timeout': 'La plateforme a dépassé le délai de réponse.',
    'temporarily_unavailable': 'La plateforme est indisponible ou a refusé la requête.',
    'invalid_response': 'La plateforme a renvoyé une réponse invalide.',
    'unsupported_media': 'Ce média n’est diffusé que sous une forme qu’AnyTube ne sait pas lire.',
}

# The provider states the medium is out of reach by design, not by an outage.
UNSUPPORTED_MARKERS = ('are not supported', 'is not supported', 'app-only', 'unsupported url')

# A 403 alone never means "log in"; only these explicit provider markers do.
LOGIN_MARKERS = ('only available for registered users', 'sign in to confirm', 'log in to confirm',
                 'login required', 'requires authentication', 'not authorized to perform',
                 'account is required', 'members-only', 'subscribe to this channel')


class SourceFailure(RuntimeError):
    def __init__(self, code='temporarily_unavailable', retry_after=None):
        self.code = code if code in MESSAGES else 'temporarily_unavailable'
        self.retry_after = retry_after
        super().__init__(MESSAGES[self.code])


def http_status(exc):
    """yt-dlp raises its own HTTPError; urllib's is still used by the JSON connectors."""
    from urllib.error import HTTPError as UrllibHTTPError
    from yt_dlp.networking.exceptions import HTTPError as EngineHTTPError
    if isinstance(exc, UrllibHTTPError):
        return exc.code, exc.headers
    if isinstance(exc, EngineHTTPError):
        return exc.status, getattr(exc.response, 'headers', None)
    return None, None


def message_of(exc):
    return str(getattr(exc, 'msg', None) or exc).casefold()


def mentions_login(exc):
    return any(marker in message_of(exc) for marker in LOGIN_MARKERS)


def mentions_unsupported(exc):
    return any(marker in message_of(exc) for marker in UNSUPPORTED_MARKERS)


def retry_delay(headers):
    try:
        return min(3600, max(1, int((headers or {}).get('Retry-After', '60'))))
    except (ValueError, TypeError):
        return 60


def classify(exc, login_hint=False, unsupported_hint=False):
    from yt_dlp.utils import GeoRestrictedError, ExtractorError, DownloadError
    if isinstance(exc, SourceFailure):
        return exc
    if isinstance(exc, GeoRestrictedError):
        return SourceFailure('geo_restricted')
    # NRK sometimes omits its structured geo flag and supplies only this explicit
    # regional refusal. Do not classify its generic "Ikke tilgjengelig" as geo.
    if isinstance(exc, ExtractorError) and 'nrk said: ikke tilgjengelig utenfor norge' in message_of(exc):
        return SourceFailure('geo_restricted')
    login_hint = login_hint or mentions_login(exc)
    unsupported_hint = unsupported_hint or mentions_unsupported(exc)
    status, headers = http_status(exc)
    if status == 401 or (status == 403 and login_hint):
        return SourceFailure('authentication_required')
    # AnyTube never sends a conditional request header, so a provider 412 is an anti-crawler
    # gate, not a precondition we set: Bilibili answers 412 to consecutive searches.
    if status in (429, 412):
        return SourceFailure('rate_limited', retry_delay(headers))
    if isinstance(exc, TimeoutError):
        return SourceFailure('timeout')
    # Do not guess that every 403 means authentication, DRM or a regional block.
    if isinstance(exc, DownloadError) and exc.exc_info and exc.exc_info[1] is not exc:
        return classify(exc.exc_info[1], login_hint, unsupported_hint)
    if isinstance(exc, ExtractorError) and exc.cause is not None:
        return classify(exc.cause, login_hint, unsupported_hint)
    if login_hint:
        return SourceFailure('authentication_required')
    if unsupported_hint:
        return SourceFailure('unsupported_media')
    return SourceFailure()
