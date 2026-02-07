"""Security utilities: SSRF protection and response headers."""

import ipaddress
import socket
from urllib.parse import urlparse


def validate_url(url):
    """
    Validate a URL for SSRF protection.
    Resolves DNS and rejects private/reserved IPs.
    Returns (is_valid, error_message).
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

    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, 'URLs pointing to private or internal networks are not allowed'

    return True, None


def apply_security_headers(response):
    """Add security headers to every response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    return response
