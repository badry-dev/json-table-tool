"""Tests for security utilities."""

from unittest.mock import patch
from security import validate_url


class TestValidateUrl:
    def test_valid_https_url(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('93.184.216.34', 0))]
            is_valid, error = validate_url('https://example.com/api')
            assert is_valid
            assert error is None

    def test_valid_http_url(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('93.184.216.34', 0))]
            is_valid, error = validate_url('http://example.com/api')
            assert is_valid
            assert error is None

    def test_rejects_ftp_scheme(self):
        is_valid, error = validate_url('ftp://example.com/file')
        assert not is_valid
        assert 'HTTP' in error

    def test_rejects_file_scheme(self):
        is_valid, error = validate_url('file:///etc/passwd')
        assert not is_valid

    def test_rejects_no_hostname(self):
        is_valid, error = validate_url('http://')
        assert not is_valid
        assert 'hostname' in error.lower()

    def test_blocks_localhost(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('127.0.0.1', 0))]
            is_valid, error = validate_url('http://localhost/admin')
            assert not is_valid
            assert 'private' in error.lower()

    def test_blocks_private_ip_10(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('10.0.0.1', 0))]
            is_valid, error = validate_url('http://internal.corp')
            assert not is_valid

    def test_blocks_private_ip_172(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('172.16.0.1', 0))]
            is_valid, error = validate_url('http://internal.corp')
            assert not is_valid

    def test_blocks_private_ip_192(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('192.168.1.1', 0))]
            is_valid, error = validate_url('http://internal.corp')
            assert not is_valid

    def test_blocks_link_local(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('169.254.169.254', 0))]
            is_valid, error = validate_url('http://metadata.google')
            assert not is_valid

    def test_blocks_multicast(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('224.0.0.1', 0))]
            is_valid, error = validate_url('http://multicast.local')
            assert not is_valid

    def test_unresolvable_hostname(self):
        import socket
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.side_effect = socket.gaierror('Name not found')
            is_valid, error = validate_url('http://nonexistent.invalid')
            assert not is_valid
            assert 'resolve' in error.lower()

    def test_blocks_unspecified_ipv4(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(2, 1, 6, '', ('0.0.0.0', 0))]
            is_valid, error = validate_url('http://zero.example.com')
            assert not is_valid
            assert 'private' in error.lower()

    def test_blocks_unspecified_ipv6(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(10, 1, 6, '', ('::', 0, 0, 0))]
            is_valid, error = validate_url('http://zero6.example.com')
            assert not is_valid
            assert 'private' in error.lower()

    def test_multiple_ips_all_validated(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [
                (2, 1, 6, '', ('93.184.216.34', 0)),
                (2, 1, 6, '', ('93.184.216.35', 0)),
            ]
            is_valid, error = validate_url('https://example.com')
            assert is_valid
            assert error is None

    def test_blocks_ipv6_loopback(self):
        with patch('security.socket.getaddrinfo') as mock_dns:
            mock_dns.return_value = [(10, 1, 6, '', ('::1', 0, 0, 0))]
            is_valid, error = validate_url('http://localhost6.example.com')
            assert not is_valid
