# coding: utf-8
"""Common test functions and fixtures."""

__author__ = "Bartek Kryza"
__copyright__ = "Copyright (C) 2023 Onedata"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

import random
import string
from typing import Optional


def random_int(lower_bound: int = 1, upper_bound: int = 100) -> int:
    """Generate random int in a given range."""
    return random.randint(lower_bound, upper_bound)


def random_str(
    size: Optional[int] = None,
    *,
    characters: str = string.ascii_uppercase + string.digits
) -> str:
    """Generate random string of specified size."""
    size = size or random_int()
    return "".join(random.choice(characters) for _ in range(size))


def random_path(size: Optional[int] = None) -> str:
    """Generate random file system path."""
    size = size or random_int(3, 10)
    return "/".join(random_str(5) for _ in range(size))


def random_bytes(size: Optional[int] = None) -> bytes:
    """Generate random sequence of bytes."""
    size = size or random_int()
    return random_str(size).encode("utf-8")
