import subprocess
import sys
from pathlib import Path


def test_worker_imports_from_its_service_directory_without_repo_root():
    service_dir = Path(__file__).parent
    script = """
from app.main import canonical_attribute_text
for value in ({'private_path': '/secret/image.png'}, {'relative': '../secret.png'}, {'data': 'data:image/png;base64,AAAA'}):
    try:
        canonical_attribute_text(value)
    except (TypeError, ValueError):
        continue
    raise AssertionError(value)
assert canonical_attribute_text({'objects': ['bowl'], 'style': 'warm'}) == '{"objects":["bowl"],"style":"warm"}'
"""

    result = subprocess.run([sys.executable, "-c", script], cwd=service_dir, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr or result.stdout
