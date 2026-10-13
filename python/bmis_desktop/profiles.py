"""Saved BMis connection profiles.

Profiles store connection metadata only. Passwords and other secrets are never
written to this database.
"""

import os
import sqlite3
import stat
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_MIN_PORT = 1
_MAX_PORT = 65535
_GROUP_OR_OTHER_PERMISSIONS = stat.S_IRWXG | stat.S_IRWXO
_SQLITE_SIDECAR_SUFFIXES = ("-journal", "-wal", "-shm")
_CREATE_PROFILES_SQL = """
CREATE TABLE IF NOT EXISTS connection_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

Clock = Callable[[], datetime]
IdFactory = Callable[[], str]


class ProfileError(Exception):
    """Base error for saved connection profiles."""


class ProfileValidationError(ProfileError, ValueError):
    """A connection profile field failed validation."""


class ProfileNotFoundError(ProfileError, LookupError):
    """No connection profile exists for the given id."""


class ProfileConflictError(ProfileError):
    """A connection profile id already exists."""


class ProfileRepositoryError(ProfileError):
    """The profile database could not be read or written safely."""


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
    """Non-secret settings for one saved BMis server connection."""

    id: str
    name: str
    host: str
    port: int
    created_at: datetime
    updated_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_profile_id() -> str:
    return str(uuid.uuid4())


def _parse_text(value: object, label: str) -> str:
    empty = f"{label} must be a non-empty string"
    if not isinstance(value, str):
        raise ProfileValidationError(empty)
    if "\n" in value or "\r" in value:
        raise ProfileValidationError(f"{label} cannot contain newline characters")
    text = value.strip()
    if not text:
        raise ProfileValidationError(empty)
    return text


def _parse_port(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileValidationError("Port must be an integer between 1 and 65535")
    if value < _MIN_PORT or value > _MAX_PORT:
        raise ProfileValidationError("Port must be an integer between 1 and 65535")
    return value


def _database_file(value: str | Path) -> Path:
    if isinstance(value, str):
        if not value.strip():
            raise ProfileValidationError("Database path must be a SQLite file path")
        path = Path(value)
    elif isinstance(value, Path):
        path = value
    else:
        raise ProfileValidationError("Database path must be a SQLite file path")

    # A private in-memory database is empty for every new connection.
    if path == Path(":memory:") or str(value) == ":memory:":
        raise ProfileValidationError("Database path must be a SQLite file path")
    return path


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ProfileRepositoryError("Profile timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _parse_stored_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ProfileRepositoryError("Stored profile timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise ProfileRepositoryError("Stored profile timestamp is invalid")
    return parsed


def _no_follow_flag() -> int:
    flag = getattr(os, "O_NOFOLLOW", 0)
    if isinstance(flag, int):
        return flag
    return 0


def _ensure_owner_only(path: Path, *, missing_ok: bool) -> None:
    """Reject or tighten a POSIX file so group and other cannot access it.

    Symlinks are not followed. A group- or other-accessible file is tightened
    only when this process owns it and the inode has a single hard link.
    """
    no_follow = _no_follow_flag()
    if no_follow == 0:
        raise ProfileRepositoryError("Profile database file permissions are unsafe")
    try:
        descriptor = os.open(path, os.O_RDONLY | no_follow)
    except FileNotFoundError as exc:
        if missing_ok:
            return
        raise ProfileRepositoryError("Profile database file could not be opened") from exc
    except OSError as exc:
        raise ProfileRepositoryError("Profile database file could not be opened") from exc

    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ProfileRepositoryError("Profile database file permissions are unsafe")
        mode = stat.S_IMODE(info.st_mode)
        if (mode & _GROUP_OR_OTHER_PERMISSIONS) == 0:
            return
        if info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ProfileRepositoryError("Profile database file permissions are unsafe")
        tightened = mode & ~_GROUP_OR_OTHER_PERMISSIONS
        try:
            os.chmod(descriptor, tightened)
        except OSError as exc:
            raise ProfileRepositoryError(
                "Profile database file permissions are unsafe"
            ) from exc
        confirmed = stat.S_IMODE(os.fstat(descriptor).st_mode)
        if confirmed & _GROUP_OR_OTHER_PERMISSIONS:
            raise ProfileRepositoryError("Profile database file permissions are unsafe")
    finally:
        os.close(descriptor)


class ConnectionProfileRepository:
    """SQLite storage for connection profiles.

    Each operation opens a connection and closes its cursor and connection
    before returning. The repository does not keep a connection open. The
    parent directory must already exist. SQLite rollback journals use delete
    mode so WAL sidecar files are not left beside the database.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self._database_path = _database_file(database_path)
        self._clock = clock or _utc_now
        self._id_factory = id_factory or _new_profile_id

    def create(self, name: object, host: object, port: object) -> ConnectionProfile:
        profile_name = _parse_text(name, "Name")
        profile_host = _parse_text(host, "Host")
        profile_port = _parse_port(port)
        profile_id = _parse_text(self._id_factory(), "Profile id")
        timestamp = _format_timestamp(self._clock())

        with self._open() as connection:
            try:
                with connection:
                    cursor = connection.cursor()
                    try:
                        try:
                            cursor.execute(
                                """
                                INSERT INTO connection_profiles (
                                    id, name, host, port, created_at, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    profile_id,
                                    profile_name,
                                    profile_host,
                                    profile_port,
                                    timestamp,
                                    timestamp,
                                ),
                            )
                        except sqlite3.IntegrityError as exc:
                            raise ProfileConflictError(
                                "Connection profile id already exists"
                            ) from exc
                    finally:
                        cursor.close()
            except sqlite3.Error as exc:
                raise ProfileRepositoryError(
                    "Profile database could not be written"
                ) from exc
            try:
                return self._require(connection, profile_id)
            except sqlite3.Error as exc:
                raise ProfileRepositoryError("Profile database could not be read") from exc

    def list_profiles(self) -> list[ConnectionProfile]:
        with self._open() as connection:
            try:
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        """
                        SELECT id, name, host, port, created_at, updated_at
                        FROM connection_profiles
                        ORDER BY name, id
                        """
                    )
                    rows = cursor.fetchall()
                finally:
                    cursor.close()
            except sqlite3.Error as exc:
                raise ProfileRepositoryError("Profile database could not be read") from exc
        return [_profile_from_row(row) for row in rows]

    def update(
        self,
        profile_id: object,
        *,
        name: object,
        host: object,
        port: object,
    ) -> ConnectionProfile:
        stored_id = _parse_text(profile_id, "Profile id")
        profile_name = _parse_text(name, "Name")
        profile_host = _parse_text(host, "Host")
        profile_port = _parse_port(port)
        updated_at = _format_timestamp(self._clock())

        with self._open() as connection:
            try:
                with connection:
                    cursor = connection.cursor()
                    try:
                        cursor.execute(
                            """
                            UPDATE connection_profiles
                            SET name = ?, host = ?, port = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                profile_name,
                                profile_host,
                                profile_port,
                                updated_at,
                                stored_id,
                            ),
                        )
                        updated = cursor.rowcount
                    finally:
                        cursor.close()
                    if updated != 1:
                        raise ProfileNotFoundError("Connection profile not found")
            except sqlite3.Error as exc:
                raise ProfileRepositoryError(
                    "Profile database could not be written"
                ) from exc
            try:
                return self._require(connection, stored_id)
            except sqlite3.Error as exc:
                raise ProfileRepositoryError("Profile database could not be read") from exc

    def delete(self, profile_id: object) -> None:
        stored_id = _parse_text(profile_id, "Profile id")
        with self._open() as connection:
            try:
                with connection:
                    cursor = connection.cursor()
                    try:
                        cursor.execute(
                            "DELETE FROM connection_profiles WHERE id = ?",
                            (stored_id,),
                        )
                        deleted = cursor.rowcount
                    finally:
                        cursor.close()
                    if deleted != 1:
                        raise ProfileNotFoundError("Connection profile not found")
            except sqlite3.Error as exc:
                raise ProfileRepositoryError(
                    "Profile database could not be written"
                ) from exc

    @contextmanager
    def _open(self) -> Iterator[sqlite3.Connection]:
        self._prepare_database_files()
        # SQLite creates rollback journals with the process umask. Restrict that
        # mask for the whole operation, then put the previous mask back.
        previous_umask = os.umask(0o077)
        try:
            try:
                connection = sqlite3.connect(self._database_path)
            except sqlite3.Error as exc:
                raise ProfileRepositoryError("Profile database could not be opened") from exc
            try:
                connection.row_factory = sqlite3.Row
                self._initialize(connection)
                yield connection
            finally:
                connection.close()
        finally:
            os.umask(previous_umask)

    def _initialize(self, connection: sqlite3.Connection) -> None:
        cursor = connection.cursor()
        try:
            try:
                cursor.execute("PRAGMA journal_mode=DELETE")
                row = cursor.fetchone()
            except sqlite3.Error as exc:
                raise ProfileRepositoryError(
                    "Profile database could not be initialized"
                ) from exc
            if row is None or str(row[0]).lower() != "delete":
                raise ProfileRepositoryError("Profile database journal mode is unsafe")
            try:
                # Keep sort and temporary pages in memory so they are not written
                # beside the database with the process file-creation mask.
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute(_CREATE_PROFILES_SQL)
            except sqlite3.Error as exc:
                raise ProfileRepositoryError(
                    "Profile database could not be initialized"
                ) from exc
        finally:
            cursor.close()
        if os.name == "posix":
            self._restrict_database_permissions()

    def _prepare_database_files(self) -> None:
        self._require_database_directory()
        self._create_database_file()
        if os.name == "posix":
            self._restrict_database_permissions()

    def _require_database_directory(self) -> None:
        parent = self._database_path.parent
        if parent == Path(""):
            parent = Path(".")
        try:
            parent_is_directory = parent.is_dir()
        except OSError as exc:
            raise ProfileRepositoryError("Profile database directory does not exist") from exc
        if not parent_is_directory:
            raise ProfileRepositoryError("Profile database directory does not exist")

    def _create_database_file(self) -> None:
        """Create a new database file readable and writable only by its owner."""
        try:
            descriptor = os.open(
                self._database_path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR | _no_follow_flag(),
                0o600,
            )
        except FileExistsError:
            return
        except OSError as exc:
            raise ProfileRepositoryError("Profile database file could not be created") from exc
        try:
            os.chmod(descriptor, 0o600)
        except OSError as exc:
            raise ProfileRepositoryError("Profile database file could not be created") from exc
        finally:
            os.close(descriptor)

    def _restrict_database_permissions(self) -> None:
        _ensure_owner_only(self._database_path, missing_ok=False)
        parent = self._database_path.parent
        name = self._database_path.name
        for suffix in _SQLITE_SIDECAR_SUFFIXES:
            _ensure_owner_only(parent / f"{name}{suffix}", missing_ok=True)

    def _require(self, connection: sqlite3.Connection, profile_id: str) -> ConnectionProfile:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT id, name, host, port, created_at, updated_at
                FROM connection_profiles
                WHERE id = ?
                """,
                (profile_id,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
        if row is None:
            raise ProfileRepositoryError("Stored connection profile is invalid")
        return _profile_from_row(row)


def _profile_from_row(row: sqlite3.Row) -> ConnectionProfile:
    profile_id = row["id"]
    name = row["name"]
    host = row["host"]
    port = row["port"]
    created_at = row["created_at"]
    updated_at = row["updated_at"]
    if (
        not isinstance(profile_id, str)
        or not isinstance(name, str)
        or not isinstance(host, str)
        or isinstance(port, bool)
        or not isinstance(port, int)
        or not isinstance(created_at, str)
        or not isinstance(updated_at, str)
    ):
        raise ProfileRepositoryError("Stored connection profile is invalid")
    return ConnectionProfile(
        id=profile_id,
        name=name,
        host=host,
        port=port,
        created_at=_parse_stored_timestamp(created_at),
        updated_at=_parse_stored_timestamp(updated_at),
    )
