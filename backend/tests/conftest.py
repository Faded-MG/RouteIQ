"""Root pytest fixtures and configuration."""

import pytest
import respx


@pytest.fixture(autouse=True)
def block_external_network():
    """Ensure no test makes outbound HTTP calls over the network."""
    with respx.mock(assert_all_called=False) as respx_mock:
        yield respx_mock
