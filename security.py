"""Security utilities: SSRF protection and response headers."""

import ipaddress
import socket
from urllib.parse import urlparse

from flask import request

# Built as a list of directives so appending can never fuse two tokens into one
# malformed directive (F5). Google Fonts is the only third-party origin the page
# uses; scripts stay self-only, so no inline JS is possible anywhere.
CSP_DIRECTIVES = (
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    # Shrink the XSS blast radius: no plugins, no <base> hijacking, no framing,
    # no cross-origin form exfiltration.
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    # Inert on a plain-http deployment, mandatory on an https one (F5/F14).
    'upgrade-insecure-requests',
)

CONTENT_SECURITY_POLICY = '; '.join(CSP_DIRECTIVES)


def validate_url(url):
    """
    Validate a URL for SSRF protection.
    Resolves DNS and rejects non-global IPs.
    Returns (is_valid, error_message_or_none).
    """
    parsed = urlparse(url)

    if parsed.scheme not in ('http', 'https'):
        return False, 'Only HTTP and HTTPS URLs are allowed'

    hostname = parsed.hostname
    if not hostname:
        return False, 'Invalid URL: no hostname'

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False, f'Could not resolve hostname: {hostname}'

    found_valid = False
    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if not ip.is_global or ip.is_multicast:
            return False, 'URLs pointing to private or internal networks are not allowed'
        found_valid = True

    if not found_valid:
        return False, 'Could not resolve any valid IP addresses'

    return True, None


def apply_security_headers(response):
    """Add security headers to every response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Legacy fallback for browsers predating CSP frame-ancestors.
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = CONTENT_SECURITY_POLICY

    # HSTS only makes sense once the connection is already TLS; sending it over
    # plain http would pin a local dev server to https. request.is_secure reads
    # X-Forwarded-Proto only when ProxyFix is enabled (TRUST_PROXY=1), which is
    # exactly the deployment where the proxy terminates TLS.
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    return response
