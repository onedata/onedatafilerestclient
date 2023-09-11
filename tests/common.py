# coding: utf-8
"""Common test functions and fixtures."""

import random
import string
import time
from contextlib import contextmanager


@contextmanager
def timer() -> float:
    """Measure context execution time."""
    start = time.perf_counter()
    yield lambda: time.perf_counter() - start


def random_int(lower_bound=1, upper_bound=100):
    """Generate random int in a given range."""
    return random.randint(lower_bound, upper_bound)


def random_str(
        size=random_int(), characters=string.ascii_uppercase + string.digits):
    """Generate random string of specified width."""
    return ''.join(random.choice(characters) for _ in range(size))


def random_path(size=random_int(3, 10)):
    """Generate random file system path."""
    return '/'.join(random_str(5) for _ in range(size))


def random_bytes(size=random_int()):
    """Generate random sequence of bytes."""
    return random_str(size).encode('utf-8')
