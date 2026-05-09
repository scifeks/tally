"""Storage port for arg-profile file uploads.

Files persist under projects/<name>/arg_files/<profile_id>/<sanitized-arg-name>
per concept-and-schemas.md section 2.10. The port boundary works in
profile_id + arg_name, not filesystem paths; the adapter resolves
paths through ProjectPaths.arg_profile_dir and rejects names that
escape the profile directory.
"""

from __future__ import annotations

from typing import Protocol


class ArgFileNameError(ValueError):
    """Raised when an arg name sanitizes to a path outside the profile directory."""


class ArgFilesStoragePort(Protocol):
    def write(
        self,
        profile_id: int,
        arg_name: str,
        data: bytes,
        original_filename: str | None = None,
    ) -> str: ...
    def read(self, profile_id: int, arg_name: str) -> bytes | None: ...
    def delete(self, profile_id: int, arg_name: str) -> None: ...
    def delete_profile_dir(self, profile_id: int) -> None: ...
