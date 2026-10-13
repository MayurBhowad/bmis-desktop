import os
import sqlite3
import stat
from datetime import UTC, datetime, timedelta

import pytest

from bmis_desktop.profiles import (
    ConnectionProfileRepository,
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileRepositoryError,
    ProfileValidationError,
)

_CREATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
_UPDATED_AT = datetime(2026, 1, 1, 13, 0, tzinfo=UTC)


class SequenceClock:
    def __init__(self, *times: datetime) -> None:
        self._times = iter(times)

    def __call__(self) -> datetime:
        return next(self._times)


def _repository(
    path,
    *,
    clock: SequenceClock | None = None,
    ids: list[str] | None = None,
) -> ConnectionProfileRepository:
    id_values = iter(ids) if ids is not None else None
    return ConnectionProfileRepository(
        path,
        clock=clock,
        id_factory=(lambda: next(id_values)) if id_values is not None else None,
    )


def test_create_list_update_and_delete(tmp_path) -> None:
    repository = _repository(
        tmp_path / "profiles.db",
        clock=SequenceClock(_CREATED_AT, _UPDATED_AT),
        ids=["profile-1"],
    )

    created = repository.create("  Local  ", " 127.0.0.1 ", 6379)
    assert created.id == "profile-1"
    assert created.name == "Local"
    assert created.host == "127.0.0.1"
    assert created.port == 6379
    assert created.created_at == _CREATED_AT
    assert created.updated_at == _CREATED_AT
    assert repository.list_profiles() == [created]

    updated = repository.update(
        created.id,
        name="Staging",
        host="db.example",
        port=6380,
    )
    assert updated.id == created.id
    assert updated.name == "Staging"
    assert updated.host == "db.example"
    assert updated.port == 6380
    assert updated.created_at == created.created_at
    assert updated.updated_at == _UPDATED_AT
    assert updated.updated_at != updated.created_at
    assert repository.list_profiles() == [updated]

    repository.delete(created.id)
    assert repository.list_profiles() == []


def test_profiles_persist_after_reopening_the_database(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    original = _repository(
        path,
        clock=SequenceClock(_CREATED_AT),
        ids=["profile-1"],
    )
    saved = original.create("Local", "127.0.0.1", 6379)

    reopened = ConnectionProfileRepository(path)
    assert reopened.list_profiles() == [saved]

    added = reopened.create("Other", "localhost", 1)
    assert [profile.id for profile in ConnectionProfileRepository(path).list_profiles()] == [
        saved.id,
        added.id,
    ]


def test_lists_profiles_by_name_then_id(tmp_path) -> None:
    repository = _repository(
        tmp_path / "profiles.db",
        clock=SequenceClock(_CREATED_AT, _CREATED_AT),
        ids=["b", "a"],
    )
    repository.create("Same", "host-b", 2)
    repository.create("Same", "host-a", 1)

    listed = repository.list_profiles()
    assert [(profile.name, profile.id) for profile in listed] == [
        ("Same", "a"),
        ("Same", "b"),
    ]


@pytest.mark.parametrize(
    ("name", "host", "port", "message"),
    [
        ("", "127.0.0.1", 6379, "Name must be a non-empty string"),
        ("   ", "127.0.0.1", 6379, "Name must be a non-empty string"),
        ("Local\nserver", "127.0.0.1", 6379, "Name cannot contain newline characters"),
        ("Local\rserver", "127.0.0.1", 6379, "Name cannot contain newline characters"),
        (None, "127.0.0.1", 6379, "Name must be a non-empty string"),
        ("Local", "", 6379, "Host must be a non-empty string"),
        ("Local", "   ", 6379, "Host must be a non-empty string"),
        ("Local", "host\nname", 6379, "Host cannot contain newline characters"),
        ("Local", "host\rname", 6379, "Host cannot contain newline characters"),
        ("Local", None, 6379, "Host must be a non-empty string"),
        ("Local", "127.0.0.1", 0, "Port must be an integer between 1 and 65535"),
        ("Local", "127.0.0.1", 65536, "Port must be an integer between 1 and 65535"),
        ("Local", "127.0.0.1", -1, "Port must be an integer between 1 and 65535"),
        ("Local", "127.0.0.1", True, "Port must be an integer between 1 and 65535"),
        ("Local", "127.0.0.1", False, "Port must be an integer between 1 and 65535"),
        ("Local", "127.0.0.1", 6379.0, "Port must be an integer between 1 and 65535"),
        ("Local", "127.0.0.1", "6379", "Port must be an integer between 1 and 65535"),
        ("Local", "127.0.0.1", None, "Port must be an integer between 1 and 65535"),
    ],
)
def test_create_rejects_invalid_fields(tmp_path, name, host, port, message: str) -> None:
    repository = ConnectionProfileRepository(tmp_path / "profiles.db")

    with pytest.raises(ProfileValidationError, match=message):
        repository.create(name, host, port)

    assert repository.list_profiles() == []


def test_update_rejects_invalid_fields_without_changing_the_profile(tmp_path) -> None:
    repository = _repository(
        tmp_path / "profiles.db",
        clock=SequenceClock(_CREATED_AT, _UPDATED_AT),
        ids=["profile-1"],
    )
    created = repository.create("Local", "127.0.0.1", 6379)

    with pytest.raises(ProfileValidationError, match="Name cannot contain newline characters"):
        repository.update(created.id, name="Bad\nname", host="localhost", port=6379)
    with pytest.raises(ProfileValidationError, match="Port must be an integer between 1 and 65535"):
        repository.update(created.id, name="Local", host="localhost", port=True)

    assert repository.list_profiles() == [created]


def test_accepts_minimum_and_maximum_ports(tmp_path) -> None:
    repository = _repository(
        tmp_path / "profiles.db",
        clock=SequenceClock(_CREATED_AT, _CREATED_AT),
        ids=["low", "high"],
    )

    low = repository.create("Low", "127.0.0.1", 1)
    high = repository.create("High", "127.0.0.1", 65535)

    assert low.port == 1
    assert high.port == 65535
    assert [profile.port for profile in repository.list_profiles()] == [65535, 1]


def test_invalid_profile_id_is_rejected(tmp_path) -> None:
    repository = _repository(
        tmp_path / "profiles.db",
        clock=SequenceClock(_CREATED_AT),
        ids=["profile-1"],
    )
    created = repository.create("Local", "127.0.0.1", 6379)

    with pytest.raises(ProfileValidationError, match="Profile id must be a non-empty string"):
        repository.update("   ", name="Local", host="127.0.0.1", port=6379)
    with pytest.raises(
        ProfileValidationError,
        match="Profile id cannot contain newline characters",
    ):
        repository.delete("profile\n1")

    assert repository.list_profiles() == [created]


def test_missing_profile_id_is_rejected(tmp_path) -> None:
    repository = ConnectionProfileRepository(tmp_path / "profiles.db")

    with pytest.raises(ProfileNotFoundError, match="Connection profile not found"):
        repository.update("missing", name="Local", host="127.0.0.1", port=6379)
    with pytest.raises(ProfileNotFoundError, match="Connection profile not found"):
        repository.delete("missing")


def test_duplicate_profile_id_keeps_the_original_profile(tmp_path) -> None:
    repository = _repository(
        tmp_path / "profiles.db",
        clock=SequenceClock(_CREATED_AT, _UPDATED_AT),
        ids=["same-id", "same-id"],
    )
    created = repository.create("Local", "127.0.0.1", 6379)

    with pytest.raises(ProfileConflictError, match="Connection profile id already exists"):
        repository.create("Other", "localhost", 6380)

    assert repository.list_profiles() == [created]


def test_names_containing_sql_punctuation_are_stored_as_data(tmp_path) -> None:
    name = """O'Hara"); DROP TABLE connection_profiles;--"""
    host = "host' OR '1'='1"
    repository = _repository(
        tmp_path / "profiles.db",
        clock=SequenceClock(_CREATED_AT, _CREATED_AT + timedelta(seconds=1)),
        ids=["profile-1", "profile-2"],
    )

    saved = repository.create(name, host, 6379)
    assert repository.list_profiles() == [saved]
    assert saved.name == name
    assert saved.host == host

    repository.create("Second", "localhost", 6380)
    assert len(repository.list_profiles()) == 2


def test_database_file_is_owner_accessible_only(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    ConnectionProfileRepository(path).list_profiles()

    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_operations_close_sqlite_connections_and_cursors(tmp_path, monkeypatch) -> None:
    connections: list[sqlite3.Connection] = []
    cursors: list[sqlite3.Cursor] = []
    real_connect = sqlite3.connect

    class TrackingConnection(sqlite3.Connection):
        def cursor(self, *args, **kwargs) -> sqlite3.Cursor:
            cursor = super().cursor(*args, **kwargs)
            cursors.append(cursor)
            return cursor

    def tracking_connect(*args, **kwargs):
        kwargs["factory"] = TrackingConnection
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    repository = _repository(
        tmp_path / "profiles.db",
        clock=SequenceClock(_CREATED_AT, _UPDATED_AT),
        ids=["profile-1"],
    )

    created = repository.create("Local", "127.0.0.1", 6379)
    repository.list_profiles()
    repository.update(created.id, name="Local", host="localhost", port=6379)
    repository.delete(created.id)

    assert connections
    assert cursors
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
    for cursor in cursors:
        with pytest.raises(sqlite3.ProgrammingError):
            cursor.execute("SELECT 1")


def test_rejects_in_memory_database(tmp_path) -> None:
    with pytest.raises(ProfileValidationError, match="Database path must be a SQLite file path"):
        ConnectionProfileRepository(":memory:")


def test_corrupt_timestamp_raises_repository_error(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    repository = _repository(path, clock=SequenceClock(_CREATED_AT), ids=["profile-1"])
    repository.create("Local", "127.0.0.1", 6379)

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE connection_profiles SET created_at = ? WHERE id = ?",
            ("not-a-timestamp", "profile-1"),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ProfileRepositoryError, match="Stored profile timestamp is invalid"):
        repository.list_profiles()


def test_schema_stores_metadata_only(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    ConnectionProfileRepository(path).list_profiles()

    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("PRAGMA table_info(connection_profiles)").fetchall()
    finally:
        connection.close()

    assert [row[1] for row in rows] == [
        "id",
        "name",
        "host",
        "port",
        "created_at",
        "updated_at",
    ]


def _raise_after_statement(monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
    real_connect = sqlite3.connect

    class StatementCursor(sqlite3.Cursor):
        def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
            result = super().execute(sql, parameters)
            if sql.lstrip().upper().startswith(prefix):
                raise sqlite3.OperationalError("disk I/O error")
            return result

    class StatementConnection(sqlite3.Connection):
        def cursor(self, factory: type[sqlite3.Cursor] = sqlite3.Cursor) -> sqlite3.Cursor:
            return super().cursor(StatementCursor)

    def connect(*args, **kwargs):
        kwargs["factory"] = StatementConnection
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)


def test_missing_parent_directory_is_rejected_without_creating_it(tmp_path) -> None:
    parent = tmp_path / "missing-parent"
    path = parent / "nested" / "profiles.db"
    repository = ConnectionProfileRepository(path)

    with pytest.raises(ProfileRepositoryError, match="Profile database directory does not exist"):
        repository.list_profiles()

    assert not parent.exists()
    assert not path.exists()


def test_database_parent_that_is_a_file_is_rejected(tmp_path) -> None:
    parent = tmp_path / "not-a-directory"
    parent.write_text("x")
    path = parent / "profiles.db"

    with pytest.raises(ProfileRepositoryError, match="Profile database directory does not exist"):
        ConnectionProfileRepository(path).create("Local", "127.0.0.1", 6379)

    assert parent.is_file()
    assert not path.exists()


def test_validation_error_is_not_replaced_when_the_directory_is_missing(tmp_path) -> None:
    repository = ConnectionProfileRepository(tmp_path / "missing" / "profiles.db")

    with pytest.raises(ProfileValidationError, match="Name must be a non-empty string"):
        repository.create("  ", "127.0.0.1", 6379)

    assert not (tmp_path / "missing").exists()


def test_database_file_creation_oserror_raises_repository_error(tmp_path, monkeypatch) -> None:
    real_open = os.open

    def fail_open(path, flags, mode=0o777, *, dir_fd=None):
        if os.path.basename(os.fspath(path)) == "profiles.db":
            raise OSError(13, "Permission denied")
        if dir_fd is None:
            return real_open(path, flags, mode)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", fail_open)
    path = tmp_path / "profiles.db"

    with pytest.raises(ProfileRepositoryError, match="Profile database file could not be created"):
        ConnectionProfileRepository(path).list_profiles()

    assert not path.exists()


def test_sqlite_open_error_raises_repository_error(tmp_path, monkeypatch) -> None:
    def fail_connect(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(sqlite3, "connect", fail_connect)

    with pytest.raises(ProfileRepositoryError, match="Profile database could not be opened"):
        ConnectionProfileRepository(tmp_path / "profiles.db").list_profiles()


def test_sqlite_initialization_error_raises_repository_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("bmis_desktop.profiles._CREATE_PROFILES_SQL", "CREATE TABLE")

    with pytest.raises(ProfileRepositoryError, match="Profile database could not be initialized"):
        ConnectionProfileRepository(tmp_path / "profiles.db").list_profiles()


def test_corrupt_database_file_raises_repository_error(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    path.write_text("not a sqlite database")
    os.chmod(path, 0o600)

    with pytest.raises(ProfileRepositoryError, match="Profile database could not be initialized"):
        ConnectionProfileRepository(path).list_profiles()


def test_read_error_raises_repository_error_without_removing_profiles(tmp_path, monkeypatch) -> None:
    path = tmp_path / "profiles.db"
    repository = _repository(path, clock=SequenceClock(_CREATED_AT), ids=["profile-1"])
    created = repository.create("Local", "127.0.0.1", 6379)
    _raise_after_statement(monkeypatch, "SELECT")

    with pytest.raises(ProfileRepositoryError, match="Profile database could not be read"):
        repository.list_profiles()

    monkeypatch.undo()
    assert repository.list_profiles() == [created]


def test_failed_writes_roll_back_and_raise_repository_error(tmp_path, monkeypatch) -> None:
    repository = _repository(
        tmp_path / "profiles.db",
        clock=SequenceClock(_CREATED_AT, _UPDATED_AT, _UPDATED_AT),
        ids=["profile-1", "profile-2"],
    )
    created = repository.create("Local", "127.0.0.1", 6379)

    _raise_after_statement(monkeypatch, "UPDATE")
    with pytest.raises(ProfileRepositoryError, match="Profile database could not be written"):
        repository.update(created.id, name="Changed", host="localhost", port=1)
    monkeypatch.undo()
    assert repository.list_profiles() == [created]

    _raise_after_statement(monkeypatch, "DELETE")
    with pytest.raises(ProfileRepositoryError, match="Profile database could not be written"):
        repository.delete(created.id)
    monkeypatch.undo()
    assert repository.list_profiles() == [created]

    _raise_after_statement(monkeypatch, "INSERT")
    with pytest.raises(ProfileRepositoryError, match="Profile database could not be written"):
        repository.create("Other", "localhost", 2)
    monkeypatch.undo()
    assert repository.list_profiles() == [created]


def test_profile_operations_restore_process_umask(tmp_path) -> None:
    previous = os.umask(0o027)
    try:
        ConnectionProfileRepository(tmp_path / "profiles.db").list_profiles()
        current = os.umask(0o027)
        assert current == 0o027
    finally:
        os.umask(previous)


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_existing_group_readable_database_is_made_owner_only(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    path.write_bytes(b"")
    os.chmod(path, 0o644)

    ConnectionProfileRepository(path).list_profiles()

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_existing_owner_only_database_keeps_its_mode(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    connection = sqlite3.connect(path)
    connection.close()
    os.chmod(path, 0o600)

    ConnectionProfileRepository(path).list_profiles()

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_database_without_owner_access_is_rejected(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    path.write_bytes(b"")
    os.chmod(path, 0o007)

    with pytest.raises(ProfileRepositoryError, match="Profile database file could not be opened"):
        ConnectionProfileRepository(path).list_profiles()

    assert stat.S_IMODE(path.stat().st_mode) == 0o007


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_symlink_database_is_rejected_without_changing_the_target(tmp_path) -> None:
    target = tmp_path / "target.db"
    target.write_bytes(b"private")
    os.chmod(target, 0o644)
    link = tmp_path / "profiles.db"
    link.symlink_to(target)

    with pytest.raises(ProfileRepositoryError, match="Profile database file could not be opened"):
        ConnectionProfileRepository(link).list_profiles()

    assert link.is_symlink()
    assert target.read_bytes() == b"private"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_hard_linked_database_with_loose_permissions_is_rejected(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    path.write_bytes(b"")
    os.chmod(path, 0o640)
    linked = tmp_path / "linked.db"
    os.link(path, linked)

    with pytest.raises(ProfileRepositoryError, match="Profile database file permissions are unsafe"):
        ConnectionProfileRepository(path).list_profiles()

    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert stat.S_IMODE(linked.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_directory_database_path_is_rejected_without_chmod(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    path.mkdir()
    before = stat.S_IMODE(path.stat().st_mode)

    with pytest.raises(ProfileRepositoryError, match="Profile database file permissions are unsafe"):
        ConnectionProfileRepository(path).list_profiles()

    assert path.is_dir()
    assert stat.S_IMODE(path.stat().st_mode) == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_group_readable_journal_file_is_made_owner_only(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    ConnectionProfileRepository(path).list_profiles()
    journal = tmp_path / "profiles.db-journal"
    journal.write_bytes(b"")
    os.chmod(journal, 0o644)

    ConnectionProfileRepository(path).list_profiles()

    assert journal.is_file()
    assert stat.S_IMODE(journal.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_journal_symlink_is_rejected_without_changing_the_target(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    ConnectionProfileRepository(path).list_profiles()
    target = tmp_path / "notes.txt"
    target.write_text("secret")
    os.chmod(target, 0o644)
    journal = tmp_path / "profiles.db-journal"
    journal.symlink_to(target)

    with pytest.raises(ProfileRepositoryError, match="Profile database file could not be opened"):
        ConnectionProfileRepository(path).list_profiles()

    assert journal.is_symlink()
    assert target.read_text() == "secret"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_hard_linked_journal_with_loose_permissions_is_rejected(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    ConnectionProfileRepository(path).list_profiles()
    journal = tmp_path / "profiles.db-journal"
    journal.write_bytes(b"")
    os.chmod(journal, 0o644)
    other = tmp_path / "other-journal"
    os.link(journal, other)

    with pytest.raises(ProfileRepositoryError, match="Profile database file permissions are unsafe"):
        ConnectionProfileRepository(path).list_profiles()

    assert stat.S_IMODE(journal.stat().st_mode) == 0o644
    assert stat.S_IMODE(other.stat().st_mode) == 0o644


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_rollback_journal_is_owner_only_under_permissive_umask(tmp_path, monkeypatch) -> None:
    path = tmp_path / "profiles.db"
    observed: list[int] = []
    real_connect = sqlite3.connect

    class JournalCursor(sqlite3.Cursor):
        def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
            result = super().execute(sql, parameters)
            if sql.lstrip().upper().startswith("INSERT"):
                journal = path.parent / f"{path.name}-journal"
                assert journal.is_file()
                observed.append(stat.S_IMODE(journal.stat().st_mode))
            return result

    class JournalConnection(sqlite3.Connection):
        def cursor(self, factory: type[sqlite3.Cursor] = sqlite3.Cursor) -> sqlite3.Cursor:
            return super().cursor(JournalCursor)

    def connect(*args, **kwargs):
        kwargs["factory"] = JournalConnection
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    previous = os.umask(0)
    try:
        repository = _repository(path, clock=SequenceClock(_CREATED_AT), ids=["profile-1"])
        repository.create("Local", "127.0.0.1", 6379)
        connection = sqlite3.connect(path)
        try:
            mode = connection.execute("PRAGMA journal_mode").fetchone()
        finally:
            connection.close()
    finally:
        os.umask(previous)

    assert observed
    assert all((mode & 0o077) == 0 for mode in observed)
    assert mode is not None
    assert str(mode[0]).lower() == "delete"
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = path.parent / f"{path.name}{suffix}"
        if sidecar.exists():
            assert stat.S_IMODE(sidecar.stat().st_mode) & 0o077 == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_existing_wal_database_is_switched_to_delete_mode(tmp_path) -> None:
    path = tmp_path / "profiles.db"
    previous = os.umask(0)
    try:
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE marker (id INTEGER)")
            connection.commit()
        finally:
            connection.close()
        os.chmod(path, 0o644)

        ConnectionProfileRepository(path).list_profiles()

        reopened = sqlite3.connect(path)
        try:
            mode = reopened.execute("PRAGMA journal_mode").fetchone()
        finally:
            reopened.close()
    finally:
        os.umask(previous)

    assert mode is not None
    assert str(mode[0]).lower() == "delete"
    assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = path.parent / f"{path.name}{suffix}"
        if sidecar.exists():
            assert stat.S_IMODE(sidecar.stat().st_mode) & 0o077 == 0
