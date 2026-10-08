"""Đăng ký và tra cứu chữ ký điện tử. Chỉ PNG, tối đa 2MB (`StorageService` kiểm chữ ký tệp và dung lượng).

Đăng ký chữ ký mới sẽ vô hiệu (không xóa) chữ ký đang dùng: tài liệu cũ có thể cần dựng lại với ảnh chữ ký cũ
(`get_image_by_id`). Rộng và cao đọc thẳng từ chunk IHDR của PNG (byte 16–23, cặp uint32 big-endian) thay vì kéo Pillow vào
cho hai số nguyên.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import ElectronicSignature
from app.services.documents.storage_service import StorageError, StorageService

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class PngDimensions:
    width: int
    height: int


def parse_png_dimensions(data: bytes) -> PngDimensions | None:
    """IHDR is always the first chunk, right after the 8-byte PNG signature:
    4 bytes length, 4 bytes 'IHDR', 4 bytes width, 4 bytes height, ... Bytes
    16-23 (0-indexed) are therefore always (width, height) as big-endian
    uint32, for any well-formed PNG."""
    if len(data) < 24 or not data.startswith(_PNG_SIGNATURE):
        return None
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return PngDimensions(width=width, height=height)


class SignaturesService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = StorageService()

    async def register(self, *, user_id: str, file_bytes: bytes, original_filename: str) -> dict:
        try:
            stored = self.storage.save(
                data=file_bytes,
                original_filename=original_filename or "signature.png",
                subdir="signatures",
                accept=[".png"],
            )
        except StorageError as e:
            raise HTTPException(status_code=400, detail={"message": e.message, "code": e.code}) from e

        dims = parse_png_dimensions(file_bytes)

        # Deactivate (never delete) the previous active signature — needed
        # so historical documents signed with it can still be re-rendered
        # exactly as they were.
        await self.db.execute(
            update(ElectronicSignature)
            .where(ElectronicSignature.user_id == user_id, ElectronicSignature.is_active.is_(True))
            .values(is_active=False)
        )

        sig = ElectronicSignature(
            user_id=user_id,
            file_path=stored.relative_path,
            mime_type=stored.mime_type,
            file_hash=stored.hash,
            width_px=dims.width if dims else None,
            height_px=dims.height if dims else None,
            is_active=True,
        )
        self.db.add(sig)
        await self.db.flush()
        await self.db.commit()

        return self._present(sig)

    async def get_active_for_user(self, user_id: str) -> ElectronicSignature | None:
        stmt = select(ElectronicSignature).where(
            ElectronicSignature.user_id == user_id, ElectronicSignature.is_active.is_(True)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_my_signature(self, user_id: str) -> dict | None:
        sig = await self.get_active_for_user(user_id)
        return self._present(sig) if sig else None

    async def get_image_by_id(self, signature_id: str) -> ElectronicSignature | None:
        """Fetches the EXACT historical signature row (not necessarily the
        user's current active one) — used when re-rendering a document that
        was signed by an approver who has since replaced their signature."""
        return await self.db.get(ElectronicSignature, signature_id)

    def read_image_bytes(self, sig: ElectronicSignature) -> bytes:
        path = self.storage.absolute(sig.file_path)
        return path.read_bytes()

    @staticmethod
    def _present(sig: ElectronicSignature) -> dict:
        return {
            "id": str(sig.id),
            "fileHash": sig.file_hash,
            "createdAt": sig.created_at,
            "mimeType": sig.mime_type,
            "widthPx": sig.width_px,
            "heightPx": sig.height_px,
            "isActive": sig.is_active,
        }
