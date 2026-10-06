"""Port of `common/storage/storage.service.ts`.

Not DB-backed — pure filesystem service. Not wired into any route yet (that
starts in Phase 2 with documents/forms/signatures); included now so later
phases don't need to design it from scratch.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

_MAGIC_BYTES: dict[str, bytes] = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
}
_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}


@dataclass
class StoredFile:
    relative_path: str
    absolute_path: str
    file_name: str
    mime_type: str
    size: int
    hash: str


class StorageError(Exception):
    def __init__(self, message: str, code: str = "STORAGE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class StorageService:
    def __init__(self):
        s = get_settings()
        # storage_root_path already points at .../server/storage; repo root is two levels up.
        self.repo_root = s.storage_root_path.parent.parent
        self.storage_root = s.storage_root_path
        self.max_bytes = s.max_upload_bytes

    def absolute(self, relative_path: str) -> Path:
        """Path-traversal guard: resolved path must stay under repo root."""
        candidate = (self.repo_root / relative_path).resolve()
        root = self.repo_root.resolve()
        if root not in candidate.parents and candidate != root:
            raise StorageError("Đường dẫn không hợp lệ", "PATH_TRAVERSAL")
        return candidate

    @staticmethod
    def hash_buffer(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _validate_magic_bytes(self, ext: str, data: bytes, allow_text: bool) -> None:
        sig = _MAGIC_BYTES.get(ext)
        if sig is not None:
            if not data.startswith(sig):
                raise StorageError(f"Nội dung file không khớp định dạng {ext}", "INVALID_FILE_SIGNATURE")
            return
        if ext in _TEXT_EXTENSIONS and allow_text:
            if b"\x00" in data:
                raise StorageError("File văn bản chứa byte NUL không hợp lệ", "INVALID_TEXT_FILE")
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as e:
                raise StorageError("File không phải UTF-8 hợp lệ", "INVALID_TEXT_FILE") from e
            return
        raise StorageError(f"Định dạng {ext} không được hỗ trợ", "UNSUPPORTED_EXTENSION")

    def save(
        self,
        *,
        data: bytes,
        original_filename: str,
        subdir: str,
        accept: list[str] | None = None,
        allow_text: bool = False,
    ) -> StoredFile:
        if not data:
            raise StorageError("File rỗng", "EMPTY_FILE")
        if len(data) > self.max_bytes:
            raise StorageError("File vượt quá dung lượng cho phép", "FILE_TOO_LARGE")

        ext = Path(original_filename).suffix.lower()
        if accept is not None and ext not in accept:
            raise StorageError(f"Định dạng {ext} không được chấp nhận", "EXTENSION_NOT_ACCEPTED")

        self._validate_magic_bytes(ext, data, allow_text)

        safe_name = f"{uuid.uuid4()}{ext}"
        target_dir = self.storage_root / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_name
        target_path.write_bytes(data)

        relative_path = str(target_path.relative_to(self.repo_root)).replace("\\", "/")
        return StoredFile(
            relative_path=relative_path,
            absolute_path=str(target_path),
            file_name=original_filename[:255],
            mime_type=_guess_mime(ext),
            size=len(data),
            hash=self.hash_buffer(data),
        )

    def write_named(self, subdir: str, filename: str, data: bytes) -> tuple[str, str]:
        """Write `data` to a caller-chosen, deterministic filename (overwriting
        any existing file) — unlike `save()`, which always picks a random
        UUID name. Used for generated DOCX files (`{code}.docx`,
        `{code}-signed.docx}`), which must be addressable by submission code
        and re-written in place on every re-render/re-sign."""
        target_dir = self.storage_root / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
        target_path.write_bytes(data)
        relative_path = str(target_path.relative_to(self.repo_root)).replace("\\", "/")
        return relative_path, self.hash_buffer(data)

    def remove(self, relative_path: str) -> None:
        try:
            self.absolute(relative_path).unlink()
        except FileNotFoundError:
            pass


def _guess_mime(ext: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
    }.get(ext, "application/octet-stream")
