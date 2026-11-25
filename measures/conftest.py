"""Test settings for the shared measures. Tests marked `slow` load the full mock data; make check-fast leaves them out."""


def pytest_configure(config):
    """Register the slow marker."""
    config.addinivalue_line("markers", "slow: loads the full mock data; make check-fast leaves it out")
