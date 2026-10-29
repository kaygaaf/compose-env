"""Command line interface for compose-env."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from compose_env import __version__
from compose_env.check import ComposeEnvError, build_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="compose-env",
        description="Check docker-compose files for missing environment variables.",
    )
    parser.add_argument(
        "-f",
        "--file",
        action="append",
        dest="files",
        metavar="PATH",
        help=(
            "Compose file to check. Repeat to pass more than one. "
            "Default: docker-compose.yml, docker-compose.yaml, compose.yml, "
            "and compose.yaml in the current directory."
        ),
    )
    parser.add_argument(
        "--env-file",
        action="append",
        dest="env_files",
        metavar="PATH",
        help=(
            "Dotenv file of KEY=VALUE lines. Repeat to pass more than one. "
            "When set, the default .env file is not read."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help='Print {"missing", "checked", "files"} as JSON.',
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also report variables that only appear with a default.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"compose-env {__version__}",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 2

    try:
        report = build_report(
            args.files,
            args.env_files,
            cwd=Path.cwd(),
            environ_keys=set(os.environ),
            strict=args.strict,
        )
    except ComposeEnvError as exc:
        print(f"compose-env: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "missing": report.missing,
            "checked": report.checked,
            "files": report.files,
        }
        sys.stdout.write(json.dumps(payload) + "\n")
    elif report.missing:
        sys.stdout.write("\n".join(report.missing) + "\n")
    return 1 if report.missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
