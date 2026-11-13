"""
Test-suite wide fixtures.

Cache isolation: views cache public catalogue lists (products, designers,
categories). Without isolation, one test's cached list leaks into the next and
tests pass or fail depending on run order. The suite also needed a running
Redis just to start. Every test now gets an in-memory cache, cleared before and
after it. This never touches a real Redis.
"""
import pytest
from django.core.cache import cache
from django.test import override_settings

TEST_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'aso-test-suite',
    }
}


@pytest.fixture(autouse=True, scope='session')
def _in_memory_test_cache():
    with override_settings(CACHES=TEST_CACHES):
        yield


@pytest.fixture(autouse=True)
def _clear_cache_between_tests(_in_memory_test_cache):
    cache.clear()
    yield
    cache.clear()
