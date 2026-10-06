import subprocess
import sys
from pathlib import Path


def test_worker_imports_from_its_service_directory_without_repo_root():
    service_dir = Path(__file__).parent
    script = """
from app.providers import validate_attributes
for value in ({'private_path': '/secret/image.png'}, {'relative': '../secret.png'}, {'data': 'data:image/png;base64,AAAA'}):
    try:
        validate_attributes(value)
    except (TypeError, ValueError):
        continue
    raise AssertionError(value)
"""

    result = subprocess.run([sys.executable, "-c", script], cwd=service_dir, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr or result.stdout
