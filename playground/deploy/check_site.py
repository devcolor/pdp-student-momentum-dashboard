"""Fail if a Sandbox page, Sandbox API endpoint or results query on the deployed site isn't 200.

Usage, from the repo root: python playground/deploy/check_site.py https://your-project.example.com
The site URL can also come from SITE_URL. Standard library only, so it runs before anything is installed.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROUTES = Path("playground/client_application/src/lib/routes.ts")
TRIES = 3  # The first request after a quiet spell can time out while the API starts.


def status(url: str) -> int:
    """The HTTP status for one URL, retried a few times for cold starts."""
    for attempt in range(1, TRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code
        # No answer: URLError and TimeoutError are both OSErrors. HTTPError is handled above.
        except OSError:
            if attempt == TRIES:
                return 0
            time.sleep(5)
    return 0


def sandbox_pages() -> list[str]:
    """Every Sandbox page path the website lists."""
    return sorted(set(re.findall(r'"(/sandbox/[a-z0-9-]+)"', ROUTES.read_text(encoding="utf-8"))))


def sandbox_endpoints(site: str) -> list[str]:
    """Every Sandbox GET endpoint that needs no parameters, from the API's own schema."""
    with urllib.request.urlopen(f"{site}/api/v1/openapi.json", timeout=60) as response:
        spec = json.load(response)
    endpoints = []
    for path, operations in spec["paths"].items():
        get = operations.get("get")
        if "/sandbox/" not in path or "{" in path or get is None:
            continue
        if not any(parameter.get("required") for parameter in get.get("parameters", [])):
            endpoints.append(path)
    return sorted(endpoints)


def results_query_status(site: str) -> int:
    """The status of one results query, built from the first approved measure, cohort and breakdown.

    The query reads the published file and its record, which no GET endpoint does, so a copy that
    doesn't match the deployed manifest shows up here.
    """
    try:
        approved_url = f"{site}/api/v1/sandbox/results/approved"
        with urllib.request.urlopen(approved_url, timeout=60) as response:
            measures = json.load(response)["measures"]
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return 0
    # A measure with no cohort or breakdown can't make a query, and neither can an empty list.
    usable = [(name, a) for name, a in measures.items() if a["cohorts"] and a["group_by"]]
    if not usable:
        print("The approved list has no measure with a cohort and a breakdown.", file=sys.stderr)
        return 0
    measure, approved = usable[0]
    spec = {
        "measure": measure,
        "cohort": approved["cohorts"][0],
        "group_by": approved["group_by"][0],
    }
    request = urllib.request.Request(
        f"{site}/api/v1/sandbox/results/query",
        data=json.dumps(spec).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return 0


def main() -> None:
    """Check every page and endpoint, print each result, and exit 1 if any failed."""
    site = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SITE_URL", "")).rstrip("/")
    if not site:
        sys.exit("Usage: python playground/deploy/check_site.py <site-url>, or set SITE_URL")
    paths = sandbox_pages() + sandbox_endpoints(site)
    failed = []
    for path in paths:
        code = status(site + path)
        print(code, path)
        if code != 200:
            failed.append(path)
    query = "POST /api/v1/sandbox/results/query"
    code = results_query_status(site)
    print(code, query)
    if code != 200:
        failed.append(query)
    checked = len(paths) + 1
    if failed:
        sys.exit(f"{len(failed)} of {checked} failed: {', '.join(failed)}")
    print(f"All {checked} pages, endpoints and the results query answered 200.")


if __name__ == "__main__":
    main()
