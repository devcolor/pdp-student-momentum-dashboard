"""The OpenAPI export the client generates its types from."""

import json
import subprocess
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]


def _export(out: Path) -> dict:
    """Run the export as the client's api-types script does, and read the schema it wrote."""
    # Its own process: the export sets environment variables before importing the app.
    subprocess.run(
        [sys.executable, "-m", "app.export_openapi", str(out)], cwd=SERVER_ROOT, check=True
    )
    return json.loads(out.read_text())


def test_export_includes_sandbox_routes_and_required_defaults(tmp_path):
    schema = _export(tmp_path / "nested" / "openapi.json")

    assert "/api/v1/sandbox/results/query" in schema["paths"]
    assert "/api/v1/sandbox/deaggregation/outcomes" in schema["paths"]
    # Defaulted fields are always sent, so the client must not see them as optional.
    assert "takeaway" in schema["components"]["schemas"]["ChartMeta"]["required"]


def test_export_never_creates_a_database(tmp_path):
    before = set(SERVER_ROOT.glob("openapi-export.db*"))
    _export(tmp_path / "openapi.json")
    assert set(SERVER_ROOT.glob("openapi-export.db*")) == before
