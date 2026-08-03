"""Unit tests for document upload, list, and delete endpoints."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile

from web.api._errors import NotFound, ValidationError
from web.api.documents import (
    delete_document,
    list_documents,
    upload_document,
)


class TestDocumentsAPI:
    """Tests for document upload/list/delete endpoints."""

    @pytest.mark.parametrize(
        "filename",
        [
            "test.py",
            "script.js",
            "data.json",
            "image.png",
            "archive.zip",
        ],
    )
    async def test_upload_with_unsupported_extension_raises_validation_error(
        self, filename: str
    ) -> None:
        """Upload with unsupported extension raises ValidationError."""
        content = b"test content"
        upload_file = UploadFile(file=io.BytesIO(content), filename=filename)
        request = MagicMock()

        with pytest.raises(ValidationError) as exc_info:
            await upload_document(project_id=1, request=request, file=upload_file)

        assert "Unsupported file type" in str(exc_info.value.message)
        assert exc_info.value.details.get("filename") == filename

    async def test_upload_with_valid_md_file_stores_and_returns_count(
        self,
    ) -> None:
        """Upload .md file calls store.add_chunks and returns response."""
        content = b"# Test Markdown\n\nSome content here."
        upload_file = UploadFile(file=io.BytesIO(content), filename="test.md")
        mock_store = MagicMock()
        mock_store.add_chunks.return_value = 2
        request = MagicMock()

        with patch(
            "web.api.documents._resolve_document_store",
            return_value=mock_store,
        ):
            response = await upload_document(
                project_id=1, request=request, file=upload_file
            )

        assert response.filename == "test.md"
        assert response.chunks == 2
        mock_store.add_chunks.assert_called_once()
        args, _kwargs = mock_store.add_chunks.call_args
        assert args[0] == "test.md"
        assert isinstance(args[1], list)

    async def test_upload_with_valid_txt_file_stores_and_returns_count(
        self,
    ) -> None:
        """Upload .txt file calls store.add_chunks and returns response."""
        content = b"Plain text content here."
        upload_file = UploadFile(file=io.BytesIO(content), filename="notes.txt")
        mock_store = MagicMock()
        mock_store.add_chunks.return_value = 1
        request = MagicMock()

        with patch(
            "web.api.documents._resolve_document_store",
            return_value=mock_store,
        ):
            response = await upload_document(
                project_id=1, request=request, file=upload_file
            )

        assert response.filename == "notes.txt"
        assert response.chunks == 1

    async def test_upload_with_empty_file_raises_validation_error(
        self,
    ) -> None:
        """Upload empty file raises ValidationError."""
        upload_file = UploadFile(file=io.BytesIO(b""), filename="empty.md")
        request = MagicMock()

        with pytest.raises(ValidationError) as exc_info:
            await upload_document(project_id=1, request=request, file=upload_file)

        assert "empty or whitespace-only" in str(exc_info.value.message)

    async def test_upload_with_whitespace_only_file_raises_validation_error(
        self,
    ) -> None:
        """Upload whitespace-only file raises ValidationError."""
        content = b"   \n\n  \t\t  \n   "
        upload_file = UploadFile(file=io.BytesIO(content), filename="whitespace.md")
        request = MagicMock()

        with pytest.raises(ValidationError) as exc_info:
            await upload_document(project_id=1, request=request, file=upload_file)

        assert "empty or whitespace-only" in str(exc_info.value.message)

    async def test_upload_exceeding_max_size_raises_validation_error(
        self,
    ) -> None:
        """Upload exceeding 1 MiB limit raises ValidationError."""
        content = b"x" * (1_048_576 + 1)
        upload_file = UploadFile(file=io.BytesIO(content), filename="large.md")
        request = MagicMock()

        with pytest.raises(ValidationError) as exc_info:
            await upload_document(project_id=1, request=request, file=upload_file)

        assert "exceeds" in str(exc_info.value.message).lower()
        assert "KiB" in str(exc_info.value.message)

    async def test_upload_with_non_utf8_content_raises_validation_error(
        self,
    ) -> None:
        """Upload with non-UTF-8 content raises ValidationError."""
        content = b"\x80\x81\x82\x83"
        upload_file = UploadFile(file=io.BytesIO(content), filename="bad.md")
        request = MagicMock()

        with pytest.raises(ValidationError) as exc_info:
            await upload_document(project_id=1, request=request, file=upload_file)

        assert "UTF-8" in str(exc_info.value.message)

    async def test_list_documents_returns_sources_from_store(self) -> None:
        """List endpoint returns document sources from store."""
        mock_store = MagicMock()
        mock_store.list_sources.return_value = [
            {"name": "readme.md", "chunks": 3},
            {"name": "guide.txt", "chunks": 2},
        ]
        request = MagicMock()

        with patch(
            "web.api.documents._resolve_document_store",
            return_value=mock_store,
        ):
            response = await list_documents(project_id=1, request=request)

        assert len(response.items) == 2
        assert response.items[0].name == "readme.md"
        assert response.items[0].chunks == 3
        assert response.items[1].name == "guide.txt"
        assert response.items[1].chunks == 2

    async def test_delete_nonexistent_document_raises_not_found(
        self,
    ) -> None:
        """Delete nonexistent filename raises NotFound."""
        mock_store = MagicMock()
        mock_store.remove_by_filename.return_value = 0
        request = MagicMock()

        with patch(
            "web.api.documents._resolve_document_store",
            return_value=mock_store,
        ):
            with pytest.raises(NotFound) as exc_info:
                await delete_document(
                    project_id=1,
                    filename="nonexistent.md",
                    request=request,
                )

        assert "no document found" in str(exc_info.value.message)

    async def test_delete_existing_document_returns_removed_count(
        self,
    ) -> None:
        """Delete existing filename returns removed count."""
        mock_store = MagicMock()
        mock_store.remove_by_filename.return_value = 5
        request = MagicMock()

        with patch(
            "web.api.documents._resolve_document_store",
            return_value=mock_store,
        ):
            response = await delete_document(
                project_id=1,
                filename="readme.md",
                request=request,
            )

        assert response.filename == "readme.md"
        assert response.chunks_removed == 5
        mock_store.remove_by_filename.assert_called_once_with("readme.md")

    async def test_upload_filename_with_no_extension_raises_validation_error(
        self,
    ) -> None:
        """Upload file with no extension raises ValidationError."""
        content = b"some content"
        upload_file = UploadFile(file=io.BytesIO(content), filename="noextension")
        request = MagicMock()

        with pytest.raises(ValidationError) as exc_info:
            await upload_document(project_id=1, request=request, file=upload_file)

        assert "Unsupported file type" in str(exc_info.value.message)

    async def test_upload_filename_with_multiple_dots(self) -> None:
        """Upload file with multiple dots uses rightmost extension."""
        content = b"# Test\n\nContent"
        upload_file = UploadFile(file=io.BytesIO(content), filename="my.backup.md")
        mock_store = MagicMock()
        mock_store.add_chunks.return_value = 1
        request = MagicMock()

        with patch(
            "web.api.documents._resolve_document_store",
            return_value=mock_store,
        ):
            response = await upload_document(
                project_id=1, request=request, file=upload_file
            )

        assert response.filename == "my.backup.md"
        assert response.chunks == 1
