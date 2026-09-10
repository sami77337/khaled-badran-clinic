"""Response cleanup that preserves Django TestCase's open database transaction."""

from collections import deque

from django.test.client import closing_iterator_wrapper


def close_test_response(response):
    # Match the test client's streaming cleanup: fire request_finished while
    # temporarily disconnecting close_old_connections. A direct response.close()
    # closes PostgreSQL's connection inside TestCase's surrounding transaction.
    deque(closing_iterator_wrapper((), response.close), maxlen=0)
