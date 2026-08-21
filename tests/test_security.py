"""Tests for security utilities."""

import os
import threading
import time
from unittest.mock import patch

import pytest

import security
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


class TestBoundedDnsAdmission:
    """
    F6.1 / P7 - DNS runs on a shared bounded pool.

    What is asserted here is what the code actually enforces: the CALLER's wait
    and the ADMISSION limit. Nothing asserts a bound on the lookup itself or on
    teardown, because nothing here enforces one -- getaddrinfo exposes no timeout
    and cannot be cancelled.
    """

    RESOLVED = [(2, 1, 6, '', ('93.184.216.34', 0))]

    @pytest.fixture
    def blocking_dns(self, monkeypatch):
        """A getaddrinfo that hangs until the test releases it."""
        release = threading.Event()

        def slow_getaddrinfo(*args, **kwargs):
            if not release.wait(30):
                raise AssertionError('test never released the mocked lookup')
            return self.RESOLVED

        monkeypatch.setattr(security.socket, 'getaddrinfo', slow_getaddrinfo)
        monkeypatch.setattr(security, 'DEFAULT_DNS_TIMEOUT', 0.2)
        monkeypatch.setattr(security, 'DEFAULT_DNS_MAX_WORKERS', 2)
        monkeypatch.setattr(security, 'DEFAULT_DNS_ADMISSION_TIMEOUT', 0.1)
        security.reset_resolver_pool()

        yield release

        release.set()
        security.reset_resolver_pool()

    @staticmethod
    def _wait_for(predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_caller_wait_is_bounded_and_permits_are_not_leaked(self, blocking_dns):
        pool = security.get_resolver_pool()
        assert pool.capacity == 4  # max_workers 2 + an equal backlog

        # Fill the pool. Every caller must come back on its own timeout even
        # though the lookups behind them are still running.
        for _ in range(pool.capacity):
            started = time.monotonic()
            is_valid, error = validate_url('http://slow.example.com')
            elapsed = time.monotonic() - started
            assert not is_valid
            assert 'resolve' in error.lower()
            assert elapsed < 5, f'caller waited {elapsed:.2f}s, not the configured bound'

        # The permits stay held: the lookups are still running. Releasing on
        # caller timeout would re-admit work into an already-blocked pool.
        assert pool.in_flight == pool.capacity

        # No unbounded thread growth: the pool never exceeds max_workers threads.
        assert len(pool.executor._threads) <= pool.max_workers

        # Once the lookups finish, every permit comes back.
        blocking_dns.set()
        assert self._wait_for(lambda: pool.in_flight == 0), (
            f'{pool.in_flight} permits leaked after the lookups finished'
        )

    def test_saturation_returns_the_admission_error_instead_of_blocking(self, blocking_dns):
        pool = security.get_resolver_pool()
        for _ in range(pool.capacity):
            validate_url('http://slow.example.com')
        assert pool.in_flight == pool.capacity

        started = time.monotonic()
        is_valid, error = validate_url('http://another.example.com')
        elapsed = time.monotonic() - started

        assert not is_valid
        assert 'busy' in error.lower()
        # Rejected on the short admission wait, not queued behind the lookups.
        assert elapsed < 1

    def test_repeated_timeouts_do_not_grow_the_pool(self, blocking_dns):
        pool = security.get_resolver_pool()
        for _ in range(12):
            validate_url('http://slow.example.com')
        assert len(pool.executor._threads) <= pool.max_workers
        assert pool.in_flight <= pool.capacity

    def test_pool_is_rebuilt_after_a_fork(self, monkeypatch):
        monkeypatch.setattr(security.socket, 'getaddrinfo', lambda *a, **k: self.RESOLVED)
        security.reset_resolver_pool()
        try:
            parent_pool = security.get_resolver_pool()
            assert security.get_resolver_pool() is parent_pool

            # Simulate the worker being forked from a process that already built
            # a pool: the recorded pid no longer matches, so it is replaced.
            parent_pool.pid = parent_pool.pid + 1
            child_pool = security.get_resolver_pool()
            assert child_pool is not parent_pool
            assert child_pool.pid == os.getpid()

            assert validate_url('https://example.com')[0] is True
        finally:
            security.reset_resolver_pool()

    def test_teardown_is_not_bounded_by_anything_this_code_enforces(self, blocking_dns):
        """
        Pins the ACCEPTED behavior, not a bound.

        shutdown(wait=False, cancel_futures=True) returns at once but cannot
        cancel a running getaddrinfo, so the worker thread stays alive until the
        platform resolver returns. Asserting a wall-clock bound here would be
        asserting something the code does not enforce.
        """
        validate_url('http://slow.example.com')
        pool = security.get_resolver_pool()
        threads = list(pool.executor._threads)
        assert threads

        security.reset_resolver_pool()

        # Still running well past API_DNS_TIMEOUT: that is the documented exposure.
        time.sleep(0.5)
        assert any(thread.is_alive() for thread in threads)

        blocking_dns.set()
        for thread in threads:
            thread.join(timeout=10)
        assert not any(thread.is_alive() for thread in threads)
