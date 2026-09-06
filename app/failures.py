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
}


class SourceFailure(RuntimeError):
    def __init__(self, code='temporarily_unavailable', retry_after=None):
        self.code = code if code in MESSAGES else 'temporarily_unavailable'
        self.retry_after = retry_after
        super().__init__(MESSAGES[self.code])


def classify(exc):
    from urllib.error import HTTPError
    from yt_dlp.utils import GeoRestrictedError, ExtractorError, DownloadError
    if isinstance(exc, SourceFailure):
        return exc
    if isinstance(exc, GeoRestrictedError):
        return SourceFailure('geo_restricted')
    if isinstance(exc, HTTPError):
        if exc.code == 401:
            return SourceFailure('authentication_required')
        if exc.code == 429:
            try:
                retry = min(3600, max(1, int(exc.headers.get('Retry-After', '60'))))
            except (ValueError, TypeError):
                retry = 60
            return SourceFailure('rate_limited', retry)
    if isinstance(exc, (TimeoutError,)):
        return SourceFailure('timeout')
    # Do not guess that every 403 means authentication, DRM or a regional block.
    if isinstance(exc, DownloadError) and exc.exc_info and exc.exc_info[1] is not exc:
        return classify(exc.exc_info[1])
    if isinstance(exc, ExtractorError) and exc.cause is not None:
        return classify(exc.cause)
    return SourceFailure()
