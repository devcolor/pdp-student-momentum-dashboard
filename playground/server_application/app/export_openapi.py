"""Write the API's OpenAPI schema to a file, for the client to generate its TypeScript types.

Run from server_application/:  python -m app.export_openapi <out.json>
The client's `bun run api-types` runs this, then openapi-typescript on the result.
"""

import json
import os
import sys
from pathlib import Path


def export(out: Path) -> None:
    """Build the app with every sandbox route mounted and write its OpenAPI schema to out."""
    # Set before the app is imported: settings are read once, at import.
    os.environ["SANDBOX_ENABLED"] = "true"
    # Any URL will do: building the schema never opens the database. Not :memory:, which
    # rejects the pool arguments in app/db/session.py.
    os.environ["DATABASE_URL"] = "sqlite:///./openapi-export.db"
    from app.main import app

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m app.export_openapi <out.json>")
    target = Path(sys.argv[1])
    export(target)
    print(f"wrote {target}")
