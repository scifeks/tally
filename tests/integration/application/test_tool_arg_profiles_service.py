"""Integration tests for ToolArgProfilesService."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.ports.arg_files_storage import ArgFileNameError
from application.ports.tool_arg_profiles import ToolArgProfileNameConflict
from application.tool_arg_profiles.service import (
    FileArgInput,
    FlagArgInput,
    StringArgInput,
    ToolArgProfilesService,
    ToolArgProfileValidationError,
)
from domain.tool_arg_profiles.entry import ToolArgProfileFileArg
from infrastructure.storage.arg_files import ArgFilesStorageAdapter
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def storage(tmp_path: Path) -> ArgFilesStorageAdapter:
    return ArgFilesStorageAdapter(tmp_path / "arg_files")


@pytest.fixture()
def service(
    factory: ConnectionFactory,
    storage: ArgFilesStorageAdapter,
) -> ToolArgProfilesService:
    repo = ToolArgProfilesRepository(factory)
    return ToolArgProfilesService(repo, storage)


class TestToolArgProfilesServiceIntegration:
    def test_create_persists_row_and_files(
        self,
        service: ToolArgProfilesService,
        tmp_path: Path,
    ) -> None:
        profile = service.create(
            tool_name="gitleaks",
            name="my-profile",
            args=[
                FlagArgInput("-v"),
                StringArgInput("--config", value="cfg"),
                FileArgInput("--rules", data=b"rules-bytes"),
            ],
        )

        assert len(profile.args) == 3
        file_arg = profile.args[2]
        assert file_arg.name == "--rules"
        assert isinstance(file_arg, ToolArgProfileFileArg)
        assert file_arg.path == f"arg_files/{profile.id}/--rules/--rules"

        file_path = tmp_path / "arg_files" / str(profile.id) / "--rules" / "--rules"
        assert file_path.read_bytes() == b"rules-bytes"

        retrieved = service.get(profile.id)
        assert retrieved is not None
        assert retrieved.id == profile.id
        assert len(retrieved.args) == 3

    def test_create_preserves_original_filename(
        self,
        service: ToolArgProfilesService,
    ) -> None:
        profile = service.create(
            tool_name="gitleaks",
            name="with-filename",
            args=[
                FileArgInput(
                    "--rules",
                    data=b"data",
                    original_filename="my_rules.yml",
                ),
            ],
        )
        file_arg = profile.args[0]
        assert isinstance(file_arg, ToolArgProfileFileArg)
        assert file_arg.original_filename == "my_rules.yml"

        retrieved = service.get(profile.id)
        assert retrieved is not None
        ret_arg = retrieved.args[0]
        assert isinstance(ret_arg, ToolArgProfileFileArg)
        assert ret_arg.original_filename == "my_rules.yml"

    def test_replace_preserves_original_filename_on_keep(
        self,
        service: ToolArgProfilesService,
    ) -> None:
        profile = service.create(
            tool_name="gitleaks",
            name="keep-fn",
            args=[
                FileArgInput(
                    "--x",
                    data=b"bytes",
                    original_filename="seeds.txt",
                ),
            ],
        )
        replaced = service.replace(
            profile.id,
            tool_name="gitleaks",
            name="keep-fn",
            args=[FileArgInput("--x", data=None)],
        )
        kept = replaced.args[0]
        assert isinstance(kept, ToolArgProfileFileArg)
        assert kept.original_filename == "seeds.txt"

    def test_replace_updates_original_filename_on_reupload(
        self,
        service: ToolArgProfilesService,
    ) -> None:
        profile = service.create(
            tool_name="gitleaks",
            name="reup-fn",
            args=[
                FileArgInput(
                    "--x",
                    data=b"old",
                    original_filename="old.txt",
                ),
            ],
        )
        replaced = service.replace(
            profile.id,
            tool_name="gitleaks",
            name="reup-fn",
            args=[
                FileArgInput(
                    "--x",
                    data=b"new",
                    original_filename="new.txt",
                ),
            ],
        )
        arg = replaced.args[0]
        assert isinstance(arg, ToolArgProfileFileArg)
        assert arg.original_filename == "new.txt"

    def test_create_unique_conflict_is_typed(
        self,
        service: ToolArgProfilesService,
    ) -> None:
        service.create(
            tool_name="gitleaks",
            name="dup",
            args=[FlagArgInput("-v")],
        )

        with pytest.raises(ToolArgProfileNameConflict):
            service.create(
                tool_name="gitleaks",
                name="dup",
                args=[FlagArgInput("-v")],
            )

    def test_create_path_traversal_rejected_and_rolled_back(
        self,
        service: ToolArgProfilesService,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(ArgFileNameError):
            service.create(
                tool_name="gitleaks",
                name="bad-profile",
                args=[FileArgInput("sub/file", data=b"data")],
            )

        items, total = service.list()
        assert total == 0
        assert items == []

        arg_files_dir = tmp_path / "arg_files"
        if arg_files_dir.exists():
            assert len(list(arg_files_dir.iterdir())) == 0

    def test_replace_overwrite_and_orphan_cleanup(
        self,
        service: ToolArgProfilesService,
        tmp_path: Path,
    ) -> None:
        profile = service.create(
            tool_name="gitleaks",
            name="original",
            args=[
                FileArgInput("--a", data=b"old-A"),
                FileArgInput("--b", data=b"old-B"),
            ],
        )

        profile_id = profile.id

        profile = service.replace(
            profile_id,
            tool_name="gitleaks",
            name="original",
            args=[
                FileArgInput("--a", data=b"new-A"),
                FileArgInput("--c", data=b"new-C"),
            ],
        )

        assert len(profile.args) == 2
        arg_names = {arg.name for arg in profile.args}
        assert arg_names == {"--a", "--c"}

        arg_files = tmp_path / "arg_files" / str(profile_id)
        assert (arg_files / "--a" / "--a").read_bytes() == b"new-A"
        assert not (arg_files / "--b").exists()
        assert (arg_files / "--c" / "--c").read_bytes() == b"new-C"

    def test_replace_keep_existing(
        self,
        service: ToolArgProfilesService,
        tmp_path: Path,
    ) -> None:
        profile = service.create(
            tool_name="gitleaks",
            name="keep-test",
            args=[FileArgInput("--x", data=b"original")],
        )

        profile_id = profile.id
        original_file_arg = profile.args[0]
        assert isinstance(original_file_arg, ToolArgProfileFileArg)
        original_path = original_file_arg.path

        profile = service.replace(
            profile_id,
            tool_name="gitleaks",
            name="keep-test",
            args=[FileArgInput("--x", data=None)],
        )

        assert len(profile.args) == 1
        kept_file_arg = profile.args[0]
        assert isinstance(kept_file_arg, ToolArgProfileFileArg)
        assert kept_file_arg.path == original_path

        arg_files = tmp_path / "arg_files" / str(profile_id)
        assert (arg_files / "--x" / "--x").read_bytes() == b"original"

    def test_replace_keep_existing_unknown_name_rejected(
        self,
        service: ToolArgProfilesService,
    ) -> None:
        profile = service.create(
            tool_name="gitleaks",
            name="unknown-test",
            args=[FileArgInput("--x", data=b"data")],
        )

        profile_id = profile.id

        with pytest.raises(ToolArgProfileValidationError):
            service.replace(
                profile_id,
                tool_name="gitleaks",
                name="unknown-test",
                args=[FileArgInput("--y", data=None)],
            )

        retrieved = service.get(profile_id)
        assert retrieved is not None
        assert len(retrieved.args) == 1
        assert retrieved.args[0].name == "--x"

    def test_delete_removes_row_and_directory(
        self,
        service: ToolArgProfilesService,
        tmp_path: Path,
    ) -> None:
        profile = service.create(
            tool_name="gitleaks",
            name="to-delete",
            args=[FileArgInput("--rules", data=b"rules")],
        )

        profile_id = profile.id
        profile_dir = tmp_path / "arg_files" / str(profile_id)

        assert profile_dir.exists()

        service.delete(profile_id)

        assert service.get(profile_id) is None
        assert not profile_dir.exists()

    def test_full_round_trip(
        self,
        service: ToolArgProfilesService,
    ) -> None:
        profile = service.create(
            tool_name="semgrep",
            name="full-test",
            args=[
                FlagArgInput("--json"),
                StringArgInput("--max-workers", value="4"),
                FileArgInput("--rules", data=b"semgrep-rules"),
            ],
        )

        profile_id = profile.id

        items, total = service.list()
        assert total == 1
        assert len(items) == 1
        assert items[0].id == profile_id

        retrieved = service.get(profile_id)
        assert retrieved is not None
        assert retrieved.tool_name == "semgrep"
        assert retrieved.name == "full-test"
        assert len(retrieved.args) == 3

        file_bytes = service.read_file_arg(profile_id, "--rules")
        assert file_bytes == b"semgrep-rules"
