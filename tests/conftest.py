"""
Test configuration and fixtures.
"""

import pytest
from typing import AsyncGenerator

# Mark all tests as async by default
pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def anyio_backend():
    """Use asyncio for async tests."""
    return "asyncio"
