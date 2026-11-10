"""Encrypted PostgreSQL backup with a restore check in an isolated container."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/opt/clashinfobot")
COMPOSE = [
    "docker", "compose", "--env-file", str(ROOT / "shared/.env"),
    "-f", str(ROOT / "current/compose.server.yaml"),
]


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, **kwargs)


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main() -> None:
    os.umask(0o077)
    backups = ROOT / "backups"
    backups.mkdir(mode=0o700, exist_ok=True)
    if shutil.disk_usage(ROOT).free < 512 * 1024 * 1024:
        raise RuntimeError("Backup needs at least 512 MiB of free disk space")
    available = next(
        int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    if available < 384 * 1024:
        raise RuntimeError("Backup needs at least 384 MiB of available memory")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"clashinfobot-{stamp}"
    destination = backups / f"{name}.dump.gpg"
    proof = backups / f"{name}.json"
    if destination.exists() or proof.exists():
        raise RuntimeError("Backup name already exists")
    gpg = [
        "gpg", "--batch", "--yes", "--pinentry-mode", "loopback",
        "--homedir", str(ROOT / "shared/gnupg"),
        "--passphrase-file", str(ROOT / "shared/backup.key"),
    ]
    container = f"clashinfobot-restore-{os.getpid()}"
    config = json.loads(run(COMPOSE + ["config", "--format", "json"], capture_output=True).stdout)
    postgres_image = config["services"]["db"]["image"]
    with tempfile.TemporaryDirectory(prefix=".verify-", dir=backups) as directory:
        temporary = Path(directory)
        dump = temporary / "database.dump"
        encrypted = temporary / "database.dump.gpg"
        decrypted = temporary / "restored.dump"
        with dump.open("wb") as output:
            run(COMPOSE + ["exec", "-T", "db", "sh", "-c",
                'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl'], stdout=output)
        run(gpg + ["--symmetric", "--cipher-algo", "AES256", "--output", str(encrypted), str(dump)])
        run(gpg + ["--decrypt", "--output", str(decrypted), str(encrypted)], capture_output=True)
        if digest(dump) != digest(decrypted):
            raise RuntimeError("Encrypted backup round trip failed")
        started = False
        try:
            run([
                "docker", "run", "--detach", "--name", container, "--network", "none",
                "--memory", "128m", "--cpus", "0.25", "--pids-limit", "64",
                "--tmpfs", "/var/lib/postgresql/data",
                "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                "-e", "POSTGRES_USER=restore_check", "-e", "POSTGRES_DB=clash_restore",
                postgres_image, "postgres", "-c", "shared_buffers=16MB", "-c", "max_connections=10",
            ], capture_output=True)
            started = True
            for _ in range(90):
                # The image's temporary init server accepts Unix sockets before
                # initialization is complete; TCP is available only on final start.
                ready = subprocess.run([
                    "docker", "exec", container, "pg_isready", "-h", "127.0.0.1",
                    "-U", "restore_check", "-d", "clash_restore",
                ], capture_output=True, check=False)
                if ready.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Restore database did not become ready")
            with decrypted.open("rb") as source:
                run([
                    "docker", "exec", "-i", container, "pg_restore", "-U", "restore_check",
                    "-d", "clash_restore", "--exit-on-error", "--no-owner", "--no-acl",
                ], stdin=source)
            revision = run([
                "docker", "exec", container, "psql", "-U", "restore_check", "-d", "clash_restore",
                "-At", "-c", "SELECT version_num FROM alembic_version",
            ], capture_output=True, text=True).stdout.strip()
            if not revision:
                raise RuntimeError("Restored database has no migration revision")
        finally:
            if started:
                run(["docker", "rm", "--force", container], capture_output=True)

        report = {
            "archive": destination.name, "sha256": digest(encrypted),
            "dump_sha256": digest(dump), "revision": revision,
            "restored": True, "created_at": stamp,
        }
        encrypted.replace(destination)
        proof.write_text(json.dumps(report, indent=2) + "\n")

    # Retention applies only to this service's successfully verified archives.
    verified = []
    for item in sorted(backups.glob("clashinfobot-*.json"), reverse=True):
        metadata = json.loads(item.read_text())
        archive = backups / metadata["archive"]
        if archive.parent != backups or not archive.name.startswith("clashinfobot-"):
            raise RuntimeError("Unexpected backup path")
        if metadata.get("restored") and archive.is_file() and digest(archive) == metadata["sha256"]:
            verified.append((item, archive))
    for item, archive in verified[3:]:
        archive.unlink()
        item.unlink()
    print(json.dumps(report))


if __name__ == "__main__":
    main()
