"""Unit tests for CredentialsService."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.credentials.service import CredentialsService  # noqa: E402


class TestReencryptRepos:
    """Tests for reencrypt_repos method."""

    def test_reencrypt_updates_repos_with_auth(self) -> None:
        """Verify update() is called only for repos with auth."""
        repo_with_auth = MagicMock()
        repo_with_auth.id = 1
        repo_with_auth.auth = MagicMock()

        repo_without_auth = MagicMock()
        repo_without_auth.id = 2
        repo_without_auth.auth = None

        repo_port = MagicMock()
        repo_port.list_active.return_value = [repo_with_auth, repo_without_auth]

        service = CredentialsService(repo_port)
        service.reencrypt_repos()

        repo_port.update.assert_called_once_with(1, repo_with_auth)

    def test_reencrypt_skips_repos_without_id(self) -> None:
        """Verify repos with id=None are skipped."""
        repo_no_id = MagicMock()
        repo_no_id.id = None
        repo_no_id.auth = MagicMock()

        repo_with_id_and_auth = MagicMock()
        repo_with_id_and_auth.id = 1
        repo_with_id_and_auth.auth = MagicMock()

        repo_port = MagicMock()
        repo_port.list_active.return_value = [repo_no_id, repo_with_id_and_auth]

        service = CredentialsService(repo_port)
        service.reencrypt_repos()

        repo_port.update.assert_called_once_with(1, repo_with_id_and_auth)

    def test_reencrypt_noop_when_no_repos(self) -> None:
        """Verify no update calls when list is empty."""
        repo_port = MagicMock()
        repo_port.list_active.return_value = []

        service = CredentialsService(repo_port)
        service.reencrypt_repos()

        repo_port.update.assert_not_called()

    def test_reencrypt_noop_when_repos_have_no_auth(self) -> None:
        """Verify no update calls when all repos lack auth."""
        repo1 = MagicMock()
        repo1.id = 1
        repo1.auth = None

        repo2 = MagicMock()
        repo2.id = 2
        repo2.auth = None

        repo_port = MagicMock()
        repo_port.list_active.return_value = [repo1, repo2]

        service = CredentialsService(repo_port)
        service.reencrypt_repos()

        repo_port.update.assert_not_called()


class TestChangeKey:
    """Tests for change_key method."""

    def test_change_key_calls_bulk_update_with_encrypted_values(
        self,
    ) -> None:
        """Verify update_auth_json_bulk receives encrypted auth."""
        repo = MagicMock()
        repo.id = 1
        repo.auth = MagicMock()
        repo.auth.model_dump.return_value = {"type": "form", "url": "http://example"}

        repo_port = MagicMock()
        repo_port.list_active.return_value = [repo]

        paths = MagicMock()
        paths.credentials_key = Path("/tmp/creds.key")

        with (
            patch("application.credentials.service.create_key_file") as mock_create,
            patch("application.credentials.service.encrypt_value") as mock_encrypt,
            patch.object(CredentialsService, "_swap_key_files"),
        ):
            mock_create.return_value = b"new-key-bytes"
            mock_encrypt.return_value = "encrypted-auth-json"

            service = CredentialsService(repo_port)
            service.change_key(paths, "new-passphrase", Path("/tmp/final.key"))

            repo_port.update_auth_json_bulk.assert_called_once_with(
                [(1, "encrypted-auth-json")]
            )

    def test_change_key_swaps_files_on_success(self, tmp_path: Path) -> None:
        """Verify key files are swapped after successful bulk update."""
        key_path = tmp_path / "credentials.key"
        final_dest = tmp_path / "credentials.key.final"

        key_path.write_text("old key data")

        repo = MagicMock()
        repo.id = 1
        repo.auth = MagicMock()
        repo.auth.model_dump.return_value = {}

        repo_port = MagicMock()
        repo_port.list_active.return_value = [repo]

        paths = MagicMock()
        paths.credentials_key = key_path

        with (
            patch("application.credentials.service.create_key_file") as mock_create,
            patch("application.credentials.service.encrypt_value") as mock_encrypt,
        ):

            def create_side_effect(passphrase: str, path: Path) -> bytes:
                path.write_text("new key data")
                return b"new-key-bytes"

            mock_create.side_effect = create_side_effect
            mock_encrypt.return_value = "encrypted"

            service = CredentialsService(repo_port)
            service.change_key(paths, "new-passphrase", final_dest)

            assert final_dest.exists()
            assert final_dest.read_text() == "new key data"
            assert not key_path.exists() or key_path.is_symlink()
            assert key_path.resolve() == final_dest.resolve()

    def test_change_key_cleans_up_temp_key_on_db_failure(self, tmp_path: Path) -> None:
        """Verify temp key is deleted if bulk update fails."""
        key_path = tmp_path / "credentials.key"
        final_dest = tmp_path / "credentials.key.final"
        key_path.write_text("old")

        repo = MagicMock()
        repo.id = 1
        repo.auth = MagicMock()
        repo.auth.model_dump.return_value = {}

        repo_port = MagicMock()
        repo_port.list_active.return_value = [repo]
        repo_port.update_auth_json_bulk.side_effect = RuntimeError("DB failure")

        paths = MagicMock()
        paths.credentials_key = key_path

        with (
            patch("application.credentials.service.create_key_file") as mock_create,
            patch("application.credentials.service.encrypt_value") as mock_encrypt,
        ):
            temp_key_file = tmp_path / "credentials.key.new"

            def create_side_effect(passphrase: str, path: Path) -> bytes:
                path.write_text("new key")
                return b"new-key-bytes"

            mock_create.side_effect = create_side_effect
            mock_encrypt.return_value = "encrypted"

            service = CredentialsService(repo_port)

            with pytest.raises(RuntimeError, match="DB failure"):
                service.change_key(paths, "new-passphrase", final_dest)

            assert not temp_key_file.exists()
            assert key_path.exists()
            assert key_path.read_text() == "old"

    def test_change_key_same_location_no_symlink(self, tmp_path: Path) -> None:
        """Verify no symlink when final_dest resolves to key_path."""
        key_path = tmp_path / "credentials.key"
        final_dest = key_path  # Same path

        key_path.write_text("old")

        repo = MagicMock()
        repo.id = 1
        repo.auth = MagicMock()
        repo.auth.model_dump.return_value = {}

        repo_port = MagicMock()
        repo_port.list_active.return_value = [repo]

        paths = MagicMock()
        paths.credentials_key = key_path

        with (
            patch("application.credentials.service.create_key_file") as mock_create,
            patch("application.credentials.service.encrypt_value") as mock_encrypt,
        ):

            def create_side_effect(passphrase: str, path: Path) -> bytes:
                path.write_text("new")
                return b"new-key-bytes"

            mock_create.side_effect = create_side_effect
            mock_encrypt.return_value = "encrypted"

            service = CredentialsService(repo_port)
            service.change_key(paths, "new-passphrase", final_dest)

            assert key_path.exists()
            assert key_path.read_text() == "new"
            assert not key_path.is_symlink()

    def test_change_key_symlink_old_target_deleted(self, tmp_path: Path) -> None:
        """Verify old target is deleted after symlink replacement."""
        old_target = tmp_path / "old.key"
        key_path = tmp_path / "credentials.key"
        final_dest = tmp_path / "new.key"

        old_target.write_text("old key")
        key_path.symlink_to(old_target)

        repo = MagicMock()
        repo.id = 1
        repo.auth = MagicMock()
        repo.auth.model_dump.return_value = {}

        repo_port = MagicMock()
        repo_port.list_active.return_value = [repo]

        paths = MagicMock()
        paths.credentials_key = key_path

        with (
            patch("application.credentials.service.create_key_file") as mock_create,
            patch("application.credentials.service.encrypt_value") as mock_encrypt,
        ):

            def create_side_effect(passphrase: str, path: Path) -> bytes:
                path.write_text("new key")
                return b"new-key-bytes"

            mock_create.side_effect = create_side_effect
            mock_encrypt.return_value = "encrypted"

            service = CredentialsService(repo_port)
            service.change_key(paths, "new-passphrase", final_dest)

            assert not old_target.exists()
            assert final_dest.exists()
            assert key_path.resolve() == final_dest.resolve()

    def test_change_key_no_repos_with_auth_still_swaps_files(
        self, tmp_path: Path
    ) -> None:
        """Verify files are swapped even when no repos have auth."""
        key_path = tmp_path / "credentials.key"
        final_dest = tmp_path / "credentials.key.final"

        key_path.write_text("old")

        repo_port = MagicMock()
        repo_port.list_active.return_value = []

        paths = MagicMock()
        paths.credentials_key = key_path

        with (
            patch("application.credentials.service.create_key_file") as mock_create,
            patch("application.credentials.service.encrypt_value") as mock_encrypt,
        ):

            def create_side_effect(passphrase: str, path: Path) -> bytes:
                path.write_text("new")
                return b"new-key-bytes"

            mock_create.side_effect = create_side_effect
            mock_encrypt.return_value = "encrypted"

            service = CredentialsService(repo_port)
            service.change_key(paths, "new-passphrase", final_dest)

            assert final_dest.exists()
            repo_port.update_auth_json_bulk.assert_called_once_with([])

    def test_change_key_encrypts_all_repos_with_auth(
        self,
    ) -> None:
        """Verify all repos with auth are encrypted with new key."""
        repo1 = MagicMock()
        repo1.id = 1
        repo1.auth = MagicMock()
        repo1.auth.model_dump.return_value = {"type": "form"}

        repo2 = MagicMock()
        repo2.id = 2
        repo2.auth = MagicMock()
        repo2.auth.model_dump.return_value = {"type": "header"}

        repo3 = MagicMock()
        repo3.id = 3
        repo3.auth = None

        repo_port = MagicMock()
        repo_port.list_active.return_value = [repo1, repo2, repo3]

        paths = MagicMock()
        paths.credentials_key = Path("/tmp/creds.key")

        with (
            patch("application.credentials.service.create_key_file") as mock_create,
            patch("application.credentials.service.encrypt_value") as mock_encrypt,
            patch.object(CredentialsService, "_swap_key_files"),
        ):
            mock_create.return_value = b"new-key-bytes"

            def encrypt_side_effect(plaintext: str, key: bytes) -> str:
                return f"encrypted:{plaintext[:20]}"

            mock_encrypt.side_effect = encrypt_side_effect

            service = CredentialsService(repo_port)
            service.change_key(paths, "new-passphrase", Path("/tmp/final.key"))

            bulk_update_calls = repo_port.update_auth_json_bulk.call_args_list
            assert len(bulk_update_calls) == 1
            updates = bulk_update_calls[0][0][0]
            assert len(updates) == 2
            repo_ids = [update[0] for update in updates]
            assert sorted(repo_ids) == [1, 2]
