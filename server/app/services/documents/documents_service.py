"""Port of `documents/documents.service.ts`."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.core.db import AsyncSessionLocal
from app.core.deps import AuthenticatedUser
from app.models.academic import Course
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentType, IndexStatus, RoleCode
from app.models.notifications import Notification, NotificationType
from app.schemas.documents import UploadDocumentDto
from app.schemas.rag import IngestPayload
from app.services.accounts.audit_service import AuditService
from app.services.chat.rag_client import RagClientService, get_rag_client
from app.services.documents.storage_service import StorageError, StorageService

logger = logging.getLogger("documents")

# Only these two document types are fed into the search index. KHAC is a
# lecturer's own teaching material: stored, but never indexed.
INDEXABLE: set[DocumentType] = {DocumentType.QUYCHE, DocumentType.GIAOTRINH}


def _rag_type(t: DocumentType) -> str:
    return "quyche" if t == DocumentType.QUYCHE else "giaotrinh"


def _is_rag_manager(user_roles: list[str]) -> bool:
    roles = set(user_roles)
    return RoleCode.ADMIN.value in roles or RoleCode.ACADEMIC_MANAGER.value in roles


class DocumentsService:
    def __init__(self, db):
        self.db = db
        self.storage = StorageService()
        self.rag: RagClientService = get_rag_client()
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ quyền

    def _assert_can_manage(self, user: AuthenticatedUser, document_type: DocumentType) -> None:
        """Who may manage which document type.

        Plan: "Only ACADEMIC_MANAGER and ADMIN manage RAG sources. Course
        lecturers only manage teaching material outside RAG."

        This is a business-layer check that runs AFTER the router's
        `require_roles` guard — the guard only knows "is this a LECTURER",
        this check knows "this LECTURER is trying to load a QUYCHE file into
        the index".
        """
        is_rag_manager = _is_rag_manager(user.roles)

        if document_type in INDEXABLE:
            if not is_rag_manager:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "message": (
                            'Chỉ quản trị viên và cán bộ quản lý đào tạo được nạp tài liệu vào chỉ mục '
                            'tìm kiếm. Giáo viên bộ môn tải tài liệu giảng dạy với loại "KHAC".'
                        ),
                        "code": "RAG_SOURCE_FORBIDDEN",
                    },
                )
            return

        if not is_rag_manager and RoleCode.LECTURER.value not in set(user.roles):
            raise HTTPException(status_code=403, detail={"message": "Bạn không có quyền quản lý tài liệu"})

    # ------------------------------------------------------------------ upload

    async def upload(
        self,
        *,
        file_bytes: bytes,
        original_filename: str,
        dto: UploadDocumentDto,
        user: AuthenticatedUser,
        request: Request | None,
        background_tasks,
    ) -> dict:
        self._assert_can_manage(user, dto.document_type)

        if dto.document_type == DocumentType.GIAOTRINH and not dto.course_id:
            raise HTTPException(
                status_code=400,
                detail={"message": "Tài liệu giáo trình phải gắn với một môn học để lọc theo môn khi hỏi đáp"},
            )
        if dto.course_id:
            course = (await self.db.execute(select(Course).where(Course.id == dto.course_id))).scalar_one_or_none()
            if not course:
                raise HTTPException(status_code=400, detail={"message": "Không tìm thấy môn học"})

        issued_at: date | None = None
        if dto.issued_at:
            try:
                issued_at = datetime.strptime(dto.issued_at, "%Y-%m-%d").date()
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail={"message": "Ngày ban hành không hợp lệ (định dạng YYYY-MM-DD)"}
                ) from exc

        try:
            stored = self.storage.save(
                data=file_bytes,
                original_filename=original_filename,
                subdir="uploads/documents",
                accept=[".pdf", ".docx", ".txt", ".md", ".csv"],
                allow_text=True,
            )
        except StorageError as e:
            raise HTTPException(status_code=400, detail={"message": e.message, "code": e.code}) from e

        # If this exact content is already indexed, don't ingest again —
        # loading a 177-page syllabus costs hundreds of LLM calls.
        dup_stmt = (
            select(DocumentVersion)
            .options(selectinload(DocumentVersion.document))
            .where(DocumentVersion.file_hash == stored.hash, DocumentVersion.index_status == IndexStatus.INDEXED)
            .limit(1)
        )
        duplicate = (await self.db.execute(dup_stmt)).scalar_one_or_none()
        if duplicate:
            self.storage.remove(stored.relative_path)
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f'Nội dung tệp này đã được lập chỉ mục dưới tài liệu "{duplicate.document.title}".',
                    "code": "DUPLICATE_CONTENT",
                    "existingDocumentId": str(duplicate.document.id),
                },
            )

        document = Document(
            title=dto.title,
            document_type=dto.document_type,
            course_id=dto.course_id,
            reference_no=dto.reference_no,
            issued_at=issued_at,
            uploaded_by_id=user.id,
        )
        self.db.add(document)
        await self.db.flush()

        version = DocumentVersion(
            document_id=document.id,
            version=1,
            file_path=stored.relative_path,
            file_name=stored.file_name,
            mime_type=stored.mime_type,
            file_size=stored.size,
            file_hash=stored.hash,
            index_status=IndexStatus.UPLOADED if dto.document_type in INDEXABLE else IndexStatus.INDEXED,
        )
        self.db.add(version)
        await self.db.flush()

        await self.audit.log(
            action="DOCUMENT_UPLOAD",
            user_id=user.id,
            entity_type="Document",
            entity_id=str(document.id),
            detail={"title": dto.title, "type": dto.document_type.value, "size": stored.size, "hash": stored.hash},
            request=request,
        )
        await self.db.commit()

        # Indexing runs in the background: ingest takes minutes to tens of
        # minutes and can't hold an HTTP request open that long. Using
        # FastAPI's BackgroundTasks means it starts only AFTER the response
        # is sent — the caller never waits on it.
        if dto.document_type in INDEXABLE:
            background_tasks.add_task(index_in_background, str(document.id), str(version.id), str(user.id))

        return await self.get(str(document.id), user)

    # ------------------------------------------------------------------- đọc

    async def list(
        self,
        *,
        document_type: DocumentType | None,
        course_id: str | None,
        search: str | None,
        page: int,
        page_size: int,
        user: AuthenticatedUser,
    ) -> dict:
        is_rag_manager = _is_rag_manager(user.roles)

        stmt = select(Document).options(
            selectinload(Document.course), selectinload(Document.uploaded_by), selectinload(Document.versions)
        ).execution_options(populate_existing=True)
        count_stmt = select(func.count(func.distinct(Document.id))).select_from(Document)

        conditions = []
        if document_type is not None:
            conditions.append(Document.document_type == document_type)
        if course_id is not None:
            conditions.append(Document.course_id == course_id)
        if search:
            conditions.append(Document.title.ilike(f"%{search}%"))

        if not is_rag_manager:
            # Course lecturers only see their own teaching material and their
            # own course's documents.
            stmt = stmt.outerjoin(Course, Document.course_id == Course.id)
            count_stmt = count_stmt.outerjoin(Course, Document.course_id == Course.id)
            conditions.append(or_(Document.uploaded_by_id == user.id, Course.lecturer_id == user.id))

        for c in conditions:
            stmt = stmt.where(c)
            count_stmt = count_stmt.where(c)

        total = (await self.db.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(stmt)).unique().scalars().all()

        items = [self._present_summary(d) for d in rows]
        return {"total": total, "page": page, "pageSize": page_size, "items": items}

    @staticmethod
    def _present_summary(d: Document) -> dict:
        latest = max(d.versions, key=lambda v: v.version) if d.versions else None
        return {
            "id": str(d.id),
            "title": d.title,
            "documentType": d.document_type,
            "referenceNo": d.reference_no,
            "issuedAt": d.issued_at,
            "createdAt": d.created_at,
            "course": (
                {"id": str(d.course.id), "code": d.course.code, "name": d.course.name} if d.course else None
            ),
            "uploadedBy": {"id": str(d.uploaded_by.id), "fullName": d.uploaded_by.full_name},
            "latestVersion": (
                {
                    "id": str(latest.id),
                    "version": latest.version,
                    "fileName": latest.file_name,
                    "fileSize": latest.file_size,
                    "mimeType": latest.mime_type,
                    "indexStatus": latest.index_status,
                    "indexError": latest.index_error,
                    "indexedAt": latest.indexed_at,
                    "pageCount": latest.page_count,
                    "chunkCount": latest.chunk_count,
                    "contextualCount": latest.contextual_count,
                }
                if latest
                else None
            ),
        }

    async def get(self, id: str, user: AuthenticatedUser) -> dict:
        if not _is_valid_uuid(id):
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy tài liệu"})
        stmt = (
            select(Document)
            .options(
                selectinload(Document.course), selectinload(Document.uploaded_by), selectinload(Document.versions)
            )
            .where(Document.id == id)
            # `upload()` calls this right after creating+committing a Document
            # in the SAME session: that object is already in the identity map
            # with its `uploaded_by`/`course` relationships in their default
            # unloaded state (never touched, since only the *_id FK columns
            # were set on construction). Without `populate_existing`,
            # SQLAlchemy returns that cached instance as-is instead of letting
            # `selectinload` fill the relationships in, and `uploaded_by`
            # comes back None even though the FK is set correctly in the row.
            .execution_options(populate_existing=True)
        )
        doc = (await self.db.execute(stmt)).scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy tài liệu"})

        is_rag_manager = _is_rag_manager(user.roles)
        is_owner = str(doc.uploaded_by_id) == str(user.id) or (
            doc.course is not None and str(doc.course.lecturer_id) == str(user.id)
        )
        if not is_rag_manager and not is_owner:
            # 404, not 403: confirming "this document exists but you can't see
            # it" is itself an information leak.
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy tài liệu"})

        versions_sorted = sorted(doc.versions, key=lambda v: v.version, reverse=True)
        return {
            "id": str(doc.id),
            "title": doc.title,
            "documentType": doc.document_type,
            "referenceNo": doc.reference_no,
            "issuedAt": doc.issued_at,
            "createdAt": doc.created_at,
            "course": (
                {"id": str(doc.course.id), "code": doc.course.code, "name": doc.course.name}
                if doc.course
                else None
            ),
            "uploadedBy": {"id": str(doc.uploaded_by.id), "fullName": doc.uploaded_by.full_name},
            "versions": [
                {
                    "id": str(v.id),
                    "version": v.version,
                    "fileName": v.file_name,
                    "fileSize": v.file_size,
                    "mimeType": v.mime_type,
                    "indexStatus": v.index_status,
                    "indexError": v.index_error,
                    "indexedAt": v.indexed_at,
                    "pageCount": v.page_count,
                    "chunkCount": v.chunk_count,
                    "contextualCount": v.contextual_count,
                    "createdAt": v.created_at,
                }
                for v in versions_sorted
            ],
        }

    # ------------------------------------------------------------------- xóa

    async def remove(self, id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        stmt = select(Document).options(selectinload(Document.versions)).where(Document.id == id)
        doc = (await self.db.execute(stmt)).scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy tài liệu"})

        self._assert_can_manage(user, doc.document_type)

        vectors_removed = 0
        if doc.document_type in INDEXABLE:
            # Vectors are deleted BEFORE the Postgres row. If the Postgres
            # delete ran first and Qdrant then failed, we'd be left with
            # orphaned vectors still cited for a document that no longer
            # exists — and no row left to know to clean them up.
            result = await self.rag.delete_document(str(id), _rag_type(doc.document_type))
            vectors_removed = result.total

            indexed_chunks = sum(v.chunk_count or 0 for v in doc.versions)
            if indexed_chunks > 0 and vectors_removed == 0:
                logger.warning(f"Tài liệu {id} ghi nhận {indexed_chunks} đoạn nhưng Qdrant không xóa được điểm nào")

        for v in doc.versions:
            self.storage.remove(v.file_path)

        title = doc.title
        doc_type = doc.document_type
        versions_count = len(doc.versions)
        await self.db.delete(doc)

        await self.audit.log(
            action="DOCUMENT_DELETE",
            user_id=user.id,
            entity_type="Document",
            entity_id=str(id),
            detail={"title": title, "type": doc_type.value, "vectorsRemoved": vectors_removed},
            request=request,
        )
        await self.db.commit()

        return {"message": f'Đã xóa "{title}"', "vectorsRemoved": vectors_removed, "filesRemoved": versions_count}

    # -------------------------------------------------------------- lập lại chỉ mục

    async def reindex(self, id: str, user: AuthenticatedUser, request: Request | None, background_tasks) -> dict:
        stmt = select(Document).options(selectinload(Document.versions)).where(Document.id == id)
        doc = (await self.db.execute(stmt)).scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy tài liệu"})
        self._assert_can_manage(user, doc.document_type)

        if doc.document_type not in INDEXABLE:
            raise HTTPException(status_code=400, detail={"message": "Tài liệu loại này không nằm trong chỉ mục tìm kiếm"})

        version = max(doc.versions, key=lambda v: v.version) if doc.versions else None
        if not version:
            raise HTTPException(status_code=400, detail={"message": "Tài liệu chưa có phiên bản tệp nào"})
        if version.index_status == IndexStatus.PROCESSING:
            raise HTTPException(status_code=400, detail={"message": "Tài liệu đang được lập chỉ mục, vui lòng đợi"})

        await self.audit.log(
            action="DOCUMENT_REINDEX", user_id=user.id, entity_type="Document", entity_id=str(id), request=request
        )
        await self.db.commit()

        background_tasks.add_task(index_in_background, str(id), str(version.id), str(user.id))
        return {"message": f'Đang lập lại chỉ mục cho "{doc.title}"', "status": "PROCESSING"}

    # -------------------------------------------------------------- trạng thái

    async def index_status(self) -> dict:
        """Reconcile PostgreSQL against Qdrant. A mismatch is a sign ingestion
        broke halfway through."""
        rows = (
            await self.db.execute(
                select(DocumentVersion.index_status, func.count(), func.sum(DocumentVersion.chunk_count)).group_by(
                    DocumentVersion.index_status
                )
            )
        ).all()
        try:
            health = await self.rag.health()
        except HTTPException:
            health = None

        by_status = {status: {"versions": count, "chunks": chunks or 0} for status, count, chunks in rows}
        expected_chunks = by_status.get(IndexStatus.INDEXED, {}).get("chunks", 0)
        actual_points = (
            sum(c.get("dense_points", 0) for c in health.collections.values()) if health is not None else None
        )

        if health is not None:
            rag_service_out = {
                "reachable": True,
                "collections": health.collections,
                "llm": health.dependencies.get("llm"),
            }
        else:
            rag_service_out = {"reachable": False}

        if actual_points is None:
            consistency = "unknown"
        elif actual_points == expected_chunks:
            consistency = "in_sync"
        else:
            consistency = f"lệch: PostgreSQL ghi {expected_chunks} đoạn, Qdrant có {actual_points} điểm"

        return {
            "postgres": {k.value: v for k, v in by_status.items()},
            "ragService": rag_service_out,
            "consistency": consistency,
        }

    async def get_admin_stats(self) -> dict:
        status = await self.index_status()
        by_type_rows = (
            await self.db.execute(select(Document.document_type, func.count()).group_by(Document.document_type))
        ).all()
        failed_stmt = (
            select(DocumentVersion)
            .options(selectinload(DocumentVersion.document))
            .where(DocumentVersion.index_status == IndexStatus.FAILED)
            .order_by(DocumentVersion.created_at.desc())
            .limit(10)
        )
        failed_versions = (await self.db.execute(failed_stmt)).scalars().all()

        return {
            "byIndexStatus": status["postgres"],
            "ragConsistency": status["consistency"],
            "byType": [{"documentType": t, "count": count} for t, count in by_type_rows],
            "failedList": [
                {
                    "documentTitle": v.document.title,
                    "version": v.version,
                    "indexError": v.index_error,
                    "failedAt": v.created_at,
                }
                for v in failed_versions
            ],
        }


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _describe_error(e: Exception) -> str:
    detail = getattr(e, "detail", None)
    if isinstance(detail, dict) and detail.get("message"):
        return str(detail["message"])
    return str(e)


async def index_in_background(document_id: str, version_id: str, actor_id: str) -> None:
    """Runs detached from the request (its own DB session, since the request's
    session is closed by the time a FastAPI BackgroundTask executes). Plan's
    acceptance criteria: "no orphaned record when ingestion fails" — so a
    `FAILED` status is written with the raw error message, and the row stays
    around for staff to see and retry, rather than being silently deleted.
    """
    rag = get_rag_client()
    async with AsyncSessionLocal() as db:
        stmt = (
            select(Document).options(selectinload(Document.versions)).where(Document.id == document_id)
        )
        document = (await db.execute(stmt)).scalar_one_or_none()
        if not document:
            return
        version = next((v for v in document.versions if str(v.id) == version_id), None)
        if not version:
            return

        version.index_status = IndexStatus.PROCESSING
        version.index_error = None
        await db.commit()

        try:
            result = await rag.ingest(
                IngestPayload(
                    file_path=version.file_path,
                    document_id=document_id,
                    document_type=_rag_type(document.document_type),
                    title=document.title,
                    course_id=str(document.course_id) if document.course_id else None,
                )
            )

            version.index_status = IndexStatus.INDEXED
            version.indexed_at = datetime.now(timezone.utc)
            version.index_error = " | ".join(result.warnings) if result.warnings else None
            version.page_count = result.pages
            version.chunk_count = result.chunks
            version.contextual_count = result.contextualised
            await db.commit()

            body = f'"{document.title}" đã sẵn sàng để hỏi đáp: {result.pages} trang, {result.chunks} đoạn.'
            if result.warnings:
                body += f" Cảnh báo: {result.warnings[0]}"
            db.add(
                Notification(
                    user_id=actor_id,
                    type=NotificationType.DOCUMENT_INDEXED,
                    title="Đã lập chỉ mục tài liệu",
                    body=body,
                    link_to="/quan-tri/tai-lieu",
                )
            )
            await db.commit()
            logger.info(f'Đã lập chỉ mục "{document.title}": {result.chunks} đoạn trong {result.seconds}s')
        except Exception as e:  # noqa: BLE001 - must never propagate; this runs detached
            message = _describe_error(e)
            logger.error(f'Lập chỉ mục thất bại cho "{document.title}": {message}')

            version.index_status = IndexStatus.FAILED
            version.index_error = message[:2000]
            await db.commit()

            db.add(
                Notification(
                    user_id=actor_id,
                    type=NotificationType.DOCUMENT_INDEXED,
                    title="Lập chỉ mục thất bại",
                    body=f'"{document.title}" chưa lập chỉ mục được: {message[:300]}',
                    link_to="/quan-tri/tai-lieu",
                )
            )
            await db.commit()
