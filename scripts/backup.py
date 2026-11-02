"""Back up local Compose PostgreSQL and optionally verify in a disposable database."""

import argparse
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path


def docker(*args, **kwargs):
    return subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", *args],
        check=True,
        capture_output=True,
        **kwargs,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Restore into a disposable database, compare row counts, then remove it",
    )
    args = parser.parse_args()
    data = docker("pg_dump", "-U", "reviewer", "-d", "reviewer", "-Fc").stdout
    directory = Path("reports/backups")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"reviewer-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.dump"
    path.write_bytes(data)
    path.chmod(0o600)
    print(f"Saved database backup: {path}")
    if args.verify:
        name = "diffsentry_restore_" + uuid.uuid4().hex
        query = "SELECT (SELECT count(*) FROM reviews),(SELECT count(*) FROM jobs),(SELECT count(*) FROM patterns);"
        # Validation assumes no new test webhooks are being sent during this brief drill.
        expected = docker("psql", "-U", "reviewer", "-d", "reviewer", "-tAc", query).stdout.strip()
        docker("createdb", "-U", "reviewer", name)
        try:
            docker("pg_restore", "-U", "reviewer", "--no-owner", "-d", name, input=data)
            actual = docker("psql", "-U", "reviewer", "-d", name, "-tAc", query).stdout.strip()
            if actual != expected:
                raise RuntimeError("Restore row counts differ; stop test traffic and retry")
            print("PASS: backup restored; review, job and pattern counts match.")
        finally:
            docker("dropdb", "-U", "reviewer", name)


if __name__ == "__main__":
    main()
