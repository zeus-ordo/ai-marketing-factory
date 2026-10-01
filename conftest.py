from pathlib import Path


def pytest_ignore_collect(collection_path: Path, config) -> bool:
    """Keep the explicit live-E2E collection gate isolated from service apps."""
    marker_expression = str(config.getoption("-m") or "").strip()
    return marker_expression == "e2e" and "tests_e2e" not in collection_path.parts
