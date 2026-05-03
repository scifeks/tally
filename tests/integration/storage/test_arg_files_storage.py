"""Integration tests for ArgFilesStorageAdapter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.arg_files_storage import ArgFileNameError  # noqa: E402
from infrastructure.storage.arg_files import (  # noqa: E402
    ArgFilesStorageAdapter,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def arg_files_dir(tmp_path: Path) -> Path:
    return tmp_path / "arg_files"


@pytest.fixture()
def storage(arg_files_dir: Path) -> ArgFilesStorageAdapter:
    return ArgFilesStorageAdapter(arg_files_dir)


class TestArgFilesStorageAdapter:
    def test_write_persists_bytes_and_returns_relative_path(
        self,
        storage: ArgFilesStorageAdapter,
        arg_files_dir: Path,
    ) -> None:
        rel = storage.write(12, "--rules.yml", b"rule: a\n")
        assert rel == "arg_files/12/--rules.yml"
        assert (arg_files_dir / "12" / "--rules.yml").read_bytes() == b"rule: a\n"

    def test_write_creates_profile_dir_when_absent(
        self,
        storage: ArgFilesStorageAdapter,
        arg_files_dir: Path,
    ) -> None:
        assert not (arg_files_dir / "7").exists()
        storage.write(7, "--config", b"x")
        assert (arg_files_dir / "7").is_dir()

    def test_write_overwrites_existing_file(
        self,
        storage: ArgFilesStorageAdapter,
        arg_files_dir: Path,
    ) -> None:
        storage.write(3, "--rules", b"first")
        storage.write(3, "--rules", b"second")
        assert (arg_files_dir / "3" / "--rules").read_bytes() == b"second"

    def test_write_leaves_no_temp_files(
        self,
        storage: ArgFilesStorageAdapter,
        arg_files_dir: Path,
    ) -> None:
        storage.write(4, "--rules", b"x")
        names = sorted(p.name for p in (arg_files_dir / "4").iterdir())
        assert names == ["--rules"]

    def test_read_returns_bytes(self, storage: ArgFilesStorageAdapter) -> None:
        storage.write(1, "--rules", b"hello")
        assert storage.read(1, "--rules") == b"hello"

    def test_read_returns_none_when_profile_dir_missing(
        self, storage: ArgFilesStorageAdapter
    ) -> None:
        assert storage.read(999, "--rules") is None

    def test_read_returns_none_when_file_missing(
        self, storage: ArgFilesStorageAdapter
    ) -> None:
        storage.write(2, "--config", b"x")
        assert storage.read(2, "--rules") is None

    def test_delete_removes_single_file(
        self,
        storage: ArgFilesStorageAdapter,
        arg_files_dir: Path,
    ) -> None:
        storage.write(5, "--rules", b"x")
        storage.delete(5, "--rules")
        assert not (arg_files_dir / "5" / "--rules").exists()

    def test_delete_leaves_siblings_intact(
        self,
        storage: ArgFilesStorageAdapter,
        arg_files_dir: Path,
    ) -> None:
        storage.write(6, "--rules", b"a")
        storage.write(6, "--config", b"b")
        storage.delete(6, "--rules")
        assert not (arg_files_dir / "6" / "--rules").exists()
        assert (arg_files_dir / "6" / "--config").read_bytes() == b"b"

    def test_delete_silent_when_file_missing(
        self, storage: ArgFilesStorageAdapter
    ) -> None:
        storage.write(8, "--config", b"x")
        storage.delete(8, "--rules")
        assert storage.read(8, "--config") == b"x"

    def test_delete_silent_when_profile_dir_missing(
        self, storage: ArgFilesStorageAdapter
    ) -> None:
        storage.delete(404, "--rules")

    def test_delete_profile_dir_removes_subtree(
        self,
        storage: ArgFilesStorageAdapter,
        arg_files_dir: Path,
    ) -> None:
        storage.write(9, "--rules", b"a")
        storage.write(9, "--config", b"b")
        storage.delete_profile_dir(9)
        assert not (arg_files_dir / "9").exists()

    def test_delete_profile_dir_silent_when_missing(
        self, storage: ArgFilesStorageAdapter
    ) -> None:
        storage.delete_profile_dir(404)

    @pytest.mark.parametrize(
        "bad_name",
        [
            "",
            ".",
            "..",
            "../escape",
            "sub/file",
            "sub\\file",
            "/etc/passwd",
            "with\x00null",
        ],
    )
    def test_write_rejects_unsafe_arg_name(
        self,
        storage: ArgFilesStorageAdapter,
        bad_name: str,
    ) -> None:
        with pytest.raises(ArgFileNameError):
            storage.write(1, bad_name, b"x")

    @pytest.mark.parametrize(
        "bad_name",
        ["", "..", "../escape", "sub/file", "/etc/passwd"],
    )
    def test_read_rejects_unsafe_arg_name(
        self,
        storage: ArgFilesStorageAdapter,
        bad_name: str,
    ) -> None:
        with pytest.raises(ArgFileNameError):
            storage.read(1, bad_name)

    @pytest.mark.parametrize(
        "bad_name",
        ["", "..", "../escape", "sub/file", "/etc/passwd"],
    )
    def test_delete_rejects_unsafe_arg_name(
        self,
        storage: ArgFilesStorageAdapter,
        bad_name: str,
    ) -> None:
        with pytest.raises(ArgFileNameError):
            storage.delete(1, bad_name)
