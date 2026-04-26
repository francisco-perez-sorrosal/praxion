"""One-shot utility to list and delete all Daytona sandboxes for the current org.

Use when the demo's `--warm` step hits "Total disk limit exceeded" because
prior debugging runs left sandboxes alive. Safe to re-run.

Usage:
    python hackathon/cleanup_sandboxes.py          # dry-run: list only
    python hackathon/cleanup_sandboxes.py --yes    # actually delete
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / "hackathon" / ".env")
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes", action="store_true", help="Actually delete (default: dry-run)"
    )
    args = parser.parse_args()

    from daytona import Daytona, DaytonaConfig

    api_key = os.environ.get("DAYTONA_API_KEY")
    api_url = os.environ.get("DAYTONA_API_URL", "https://app.daytona.io")
    if not api_key:
        print("DAYTONA_API_KEY not set — check hackathon/.env", file=sys.stderr)
        return 1

    client = Daytona(DaytonaConfig(api_key=api_key, api_url=api_url))

    sandboxes = list(client.list())
    print(f"Found {len(sandboxes)} sandbox(es) in org:")
    for sb in sandboxes:
        state = getattr(sb, "state", "?")
        created = getattr(sb, "created_at", "?")
        print(f"  - {sb.id}  state={state}  created={created}")

    if not sandboxes:
        return 0

    if not args.yes:
        print("\nDry-run only. Re-run with --yes to delete all listed sandboxes.")
        return 0

    deleted = 0
    failed: list[tuple[str, str]] = []
    for sb in sandboxes:
        try:
            sb.delete()
            print(f"  deleted {sb.id}")
            deleted += 1
        except Exception as exc:
            failed.append((sb.id, repr(exc)))
            print(f"  FAILED {sb.id}: {exc!r}", file=sys.stderr)

    print(f"\nDeleted {deleted}/{len(sandboxes)} sandboxes")
    if failed:
        print(f"Failed: {len(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
