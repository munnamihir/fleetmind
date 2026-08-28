#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()

    path = Path(args.artifact)
    if not path.exists():
        raise SystemExit(f"artifact not found: {path}")

    digest = sha256(path)
    result = {
        "artifact": str(path),
        "sha256": digest,
        "matchesExpected": (
            None
            if not args.expected_sha256
            else digest == args.expected_sha256
        ),
    }

    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            payload = json.loads(path.read_text())
        result["jsonReadable"] = True
        result["topLevelType"] = type(payload).__name__
    except Exception as exc:
        result["jsonReadable"] = False
        result["parseError"] = str(exc)

    print(json.dumps(result, indent=2))

    if args.expected_sha256 and digest != args.expected_sha256:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
