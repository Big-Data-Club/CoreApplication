import os
import sys
import tempfile
from pathlib import Path

# Never import the lakehouse singleton against the configured production path.
_data = tempfile.TemporaryDirectory(prefix="bdc-notebook-tests-")
os.environ["DATA_DIR"] = _data.name
os.environ["AI_SERVICE_SECRET"] = "notebook-test-only-secret"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
