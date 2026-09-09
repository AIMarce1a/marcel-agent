"""One-time migration from the pre-Marcel home layout.

This module is intentionally the only production module that contains the
legacy Hermes names.  It is explicit (never automatic), conservative, and
does not read file contents except for SQLite integrity checks.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_LEGACY_ENV = "HERMES_HOME"
_LEGACY_DIR = ".hermes"
_RECEIPT = ".marcel-migration.json"
_TRANSIENT_NAMES = {
    "gateway.pid",
    "gateway.sock",
    "gateway.sock.path",
    "gateway.lock",
    "gateway-starts.log",
}
_TRANSIENT_DIRS = {"gateway-locks", "locks"}
_TRANSIENT_SUFFIXES = (".pid", ".sock", ".lock", ".lck", ".heartbeat", ".hb")
_REBUILDABLE_DIRS = {"hermes-agent", "marcel-agent", "node", "venv", ".cache", "cache", "__pycache__"}
_LOCK_NAME = ".marcel-migration.lock"
_STALE_LOCK_SECONDS = 24 * 60 * 60
_SCAFFOLD_FILES = {".env", "config.yaml", "active_profile"}


def legacy_homes() -> list[Path]:
    """Historical roots in precedence order (explicit override first)."""
    candidates: list[Path] = []
    value = os.environ.get(_LEGACY_ENV, "").strip()
    if value:
        candidates.append(Path(value).expanduser())
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        roaming = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        candidates.extend((local / "hermes", local / "Hermes", roaming / "hermes", roaming / "Hermes"))
    else:
        candidates.extend((Path.home() / _LEGACY_DIR, Path.home() / ".config" / "hermes"))
    return list(dict.fromkeys(candidates))


def legacy_home() -> Path:
    """Return the old default home, without inspecting or printing secrets."""
    return next((candidate for candidate in legacy_homes() if candidate.is_dir()), legacy_homes()[0])


def _is_transient(relative: Path) -> bool:
    name = relative.name.lower()
    return (
        name in _TRANSIENT_NAMES
        or any(part.lower() in (_TRANSIENT_DIRS | _REBUILDABLE_DIRS) for part in relative.parts)
        or name.endswith(_TRANSIENT_SUFFIXES)
        or "heartbeat" in name
    )


def _gateway_is_live(src: Path) -> bool:
    """Conservatively detect a running legacy gateway without reading secrets."""
    for pid_path in (src / "gateway.pid", *(src / "profiles").glob("*/gateway.pid")):
        try:
            raw = pid_path.read_text(encoding="utf-8").strip()
            record = json.loads(raw)
            pid = int(record.get("pid") if isinstance(record, dict) else record)
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            pid = None
        if pid and pid > 0 and _pid_alive(pid):
            return True
    # A connectable socket is authoritative even when its PID file is stale.
    socket_path = src / "gateway.sock"
    if socket_path.exists() and hasattr(socket_path, "stat"):
        import socket

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                sock.connect(str(socket_path))
            return True
        except (OSError, ValueError):
            pass
    return False


def _sqlite_is_healthy(path: Path) -> bool:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            return db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    except (OSError, sqlite3.Error):
        return False


def _copy_sqlite(source: Path, target: Path) -> None:
    """Create a transactionally coherent copy after gateway quiescence."""
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_db:
        with sqlite3.connect(target) as target_db:
            source_db.backup(target_db)


def _fsync_directory(path: Path) -> None:
    """Best-effort directory durability (not supported on Windows)."""
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
            if not handle:
                return ctypes.windll.kernel32.GetLastError() == 5
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except (AttributeError, OSError):
            return True
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class _MigrationLock:
    """Exclusive parent-directory lock with conservative stale-lock recovery."""

    def __init__(self, parent: Path) -> None:
        self.path = parent / _LOCK_NAME
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.handle = self.path.open("x", encoding="ascii")
        except FileExistsError:
            try:
                details = json.loads(self.path.read_text(encoding="ascii"))
                pid = int(details.get("pid", 0))
                created = float(details.get("created", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pid = 0
                try:
                    created = self.path.stat().st_mtime
                except OSError:
                    created = time.time()
            if (pid and _pid_alive(pid)) or (
                created and time.time() - created < _STALE_LOCK_SECONDS
            ):
                raise RuntimeError("another Marcel legacy migration is already running")
            # An abandoned or malformed lock is safe to remove only after the
            # age check; this avoids deleting a lock during a writer's startup.
            self.path.unlink(missing_ok=True)
            self.handle = self.path.open("x", encoding="ascii")
        self.handle.write(json.dumps({"pid": os.getpid(), "created": time.time()}))
        self.handle.flush()
        os.fsync(self.handle.fileno())
        return self

    def __exit__(self, *_exc) -> None:
        if self.handle is not None:
            self.handle.close()
        self.path.unlink(missing_ok=True)
        _fsync_directory(self.path.parent)


def canonical_home() -> Path:
    value = os.environ.get("MARCEL_HOME", "").strip()
    if value:
        return Path(value).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "Marcel"
    return Path.home() / ".marcel"


def migrate_if_needed() -> dict[str, object]:
    """Perform the managed cutover before Marcel loads env/config modules."""
    src, dst = legacy_home(), canonical_home()
    if not src.is_dir():
        return {"status": "not-needed"}
    if dst.exists() and (dst / _RECEIPT).exists():
        return {"status": "already-migrated"}
    with _MigrationLock(dst.parent):
        # Recheck after acquiring the cross-process lock.
        return migrate_legacy_home(src, dst)


def _reject_symlinks(root: Path) -> None:
    for item in root.rglob("*"):
        relative = item.relative_to(root)
        if item.is_symlink() and not _is_transient(relative):
            raise ValueError(f"refusing legacy home containing symlink: {item.name}")


def _recognized_empty_scaffold(root: Path) -> bool:
    """Allow only installer-created, empty Marcel scaffolding to be replaced."""
    if not root.is_dir():
        return False
    for item in root.rglob("*"):
        if item.is_symlink():
            return False
        rel = item.relative_to(root)
        if item.is_dir():
            continue
        if rel.name not in _SCAFFOLD_FILES or item.stat().st_size != 0:
            return False
    return True


def migrate_legacy_home(
    source: str | os.PathLike | None = None,
    destination: str | os.PathLike | None = None,
) -> dict[str, object]:
    """Copy a legacy home to the Marcel home, preserving data and permissions.

    The source remains untouched as the rollback copy. Data is copied into a
    sibling staging directory and committed with one same-filesystem rename;
    no duplicate backup is created in the destination.
    """
    src = Path(source).expanduser() if source else legacy_home()
    dst = Path(destination).expanduser() if destination else canonical_home()
    if not src.is_dir():
        return {"status": "not-needed", "source": str(src), "destination": str(dst)}
    receipt = dst / _RECEIPT
    if receipt.exists():
        return {"status": "already-migrated", "source": str(src), "destination": str(dst)}
    if _gateway_is_live(src):
        raise RuntimeError("refusing migration while the legacy gateway is running")
    _reject_symlinks(src)
    try:
        dst.resolve().relative_to(src.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("destination must not be inside the legacy home")
    if dst.exists():
        if not _recognized_empty_scaffold(dst):
            raise FileExistsError(f"destination already exists and is not an empty Marcel scaffold: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{dst.name}.migration-", dir=str(dst.parent)))
    copied = 0
    skipped = 0
    unhealthy: list[str] = []
    try:
        try:
            shutil.copystat(src, stage, follow_symlinks=False)
        except OSError:
            pass
        for item in src.rglob("*"):
            rel = item.relative_to(src)
            if _is_transient(rel):
                skipped += 1
                continue
            target = stage / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copystat(item, target, follow_symlinks=False)
                except OSError:
                    pass
                continue
            if not item.is_file():
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if item.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
                _copy_sqlite(item, target)
                shutil.copystat(item, target, follow_symlinks=False)
            else:
                shutil.copy2(item, target, follow_symlinks=False)
            copied += 1
            if item.suffix.lower() in {".db", ".sqlite", ".sqlite3"} and not _sqlite_is_healthy(target):
                unhealthy.append(str(rel))
        if unhealthy:
            raise ValueError("SQLite validation failed before migration commit")
        result = {
            "status": "migrated",
            "source": str(src),
            "destination": str(dst),
            "rollback_source": str(src),
            "copied": copied,
            "skipped_transient_or_existing": skipped,
            "unhealthy_databases": unhealthy,
        }
        receipt_stage = stage / _RECEIPT
        with receipt_stage.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(receipt_stage, 0o600)
        _fsync_directory(stage)
        # The lock prevents another writer, but keep this final check adjacent
        # to the commit so an external creator cannot receive a partial tree.
        if dst.exists():
            if not _recognized_empty_scaffold(dst):
                raise FileExistsError(f"destination appeared during migration: {dst}")
            shutil.rmtree(dst)
        os.replace(stage, dst)
        _fsync_directory(dst.parent)
        return result
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate a legacy home to Marcel")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.source or args.destination:
        target = args.destination.expanduser() if args.destination else canonical_home()
        with _MigrationLock(target.parent):
            result = migrate_legacy_home(args.source, args.destination)
    else:
        result = migrate_if_needed()
    print(result["status"])
    return 0 if result["status"] in {"migrated", "not-needed", "already-migrated"} else 1


if __name__ == "__main__":
    raise SystemExit(main())