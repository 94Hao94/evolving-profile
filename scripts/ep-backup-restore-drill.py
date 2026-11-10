#!/usr/bin/env python3
"""Non-destructive backup restore preflight for the latest local set."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-root", type=Path, default=Path("~/.evolving-profile/backups/managed/daily").expanduser())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dbs = sorted(args.backup_root.glob("evolving-profile-db-*.dump"))
    if not dbs:
        raise SystemExit("latest_backup_missing")
    db = dbs[-1]
    stamp = db.name.removeprefix("evolving-profile-db-").removesuffix(".dump")
    checksum = args.backup_root / f"SHA256SUMS-{stamp}"
    config = args.backup_root / f"evolving-profile-config-{stamp}.tar.gz.enc"
    capture = args.backup_root / f"evolving-profile-capture-{stamp}.sqlite.gz.enc"
    required = [checksum, config, capture]
    if any(not p.is_file() for p in required):
        raise SystemExit("backup_set_incomplete")

    report = {
        "schema": "ep.backup-restore-drill.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stamp": stamp,
        "backup_root": str(args.backup_root),
        "artifacts": {},
        "destructive_restore": False,
        "production_state_untouched": True,
    }
    check = subprocess.run(["shasum", "-a", "256", "-c", checksum.name], cwd=args.backup_root, text=True, capture_output=True, check=False)
    report["checksum"] = {"exit_code": check.returncode, "passed": check.returncode == 0}
    pg_restore = shutil.which("pg_restore") or "/Users/example/.pg0/installation/18.1.0/bin/pg_restore"
    listing = run([pg_restore, "--list", str(db)], check=False)
    report["database"] = {
        "bytes": db.stat().st_size,
        "pg_restore_list_exit_code": listing.returncode,
        "pg_restore_list_entries": len([line for line in listing.stdout.splitlines() if line.strip()]),
        "passed": listing.returncode == 0,
    }

    service = "evolving-profile-backup-key-v1"
    account = os.environ.get("USER", "")
    key = run(["security", "find-generic-password", "-a", account, "-s", service, "-w"]).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="ep-restore-drill-") as temp:
        temp_root = Path(temp)
        key_path = temp_root / "key"
        key_path.write_text(key)
        key_path.chmod(0o600)

        config_tar = temp_root / "config.tar.gz"
        dec_config = run(["openssl", "enc", "-d", "-aes-256-cbc", "-salt", "-pbkdf2", "-iter", "600000", "-md", "sha256", "-in", str(config), "-out", str(config_tar), "-pass", f"file:{key_path}"], check=False)
        config_members = []
        config_ok = dec_config.returncode == 0
        if config_ok:
            with tarfile.open(config_tar, "r:gz") as archive:
                config_members = archive.getnames()
        report["config"] = {"bytes": config.stat().st_size, "decrypt_exit_code": dec_config.returncode, "member_count": len(config_members), "passed": config_ok and bool(config_members)}

        capture_gz = temp_root / "capture.sqlite.gz"
        dec_capture = run(["openssl", "enc", "-d", "-aes-256-cbc", "-salt", "-pbkdf2", "-iter", "600000", "-md", "sha256", "-in", str(capture), "-out", str(capture_gz), "-pass", f"file:{key_path}"], check=False)
        capture_ok = dec_capture.returncode == 0
        sqlite_ok = False
        if capture_ok:
            capture_db = temp_root / "capture.sqlite3"
            with gzip.open(capture_gz, "rb") as source, capture_db.open("wb") as target:
                shutil.copyfileobj(source, target)
            conn = sqlite3.connect(f"file:{capture_db}?mode=ro", uri=True)
            try:
                sqlite_ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            finally:
                conn.close()
        report["capture"] = {"bytes": capture.stat().st_size, "decrypt_exit_code": dec_capture.returncode, "sqlite_integrity": sqlite_ok, "passed": capture_ok and sqlite_ok}

    report["status"] = "passed" if all(report[key].get("passed") for key in ("checksum", "database", "config", "capture")) else "failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    args.output.chmod(0o600)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

