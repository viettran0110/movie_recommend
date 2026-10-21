"""Write the OpenAPI schema to a file without starting a server.

Usage (from apps/api): uv run python -m scripts.export_openapi openapi.json
The committed openapi.json is the contract the web client is generated from;
CI fails if it is stale.
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: export_openapi.py <output.json>")
    output = Path(sys.argv[1])
    schema = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    output.write_text(schema, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
