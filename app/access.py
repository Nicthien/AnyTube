"""Apply imported cookies without a browser profile, cookie file, or global auth header."""
from http.cookiejar import Cookie, DefaultCookiePolicy
from app.vault import cookie_records
from app.failures import SourceFailure


def attach_access(ydl, credential):
    if not credential:
        return
    if credential['kind'] != 'cookies':
        raise SourceFailure('authentication_required')
    jar = ydl.cookiejar
    jar.set_policy(DefaultCookiePolicy(allowed_domains=credential['domains'],
                   strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain))
    for domain, include, path, secure, expiry, name, value in cookie_records(credential['value'], credential['domains']):
        # Restrict imported domain cookies to explicitly listed hosts, always HTTPS.
        base = domain.lstrip('.').lower()
        for host in credential['domains']:
            if host == base or include == 'TRUE' and host.endswith('.'+base):
                jar.set_cookie(Cookie(0, name, value, None, False, host, False, False, path, True,
                                      True, int(expiry) or None, not int(expiry), None, None, {}, False))
