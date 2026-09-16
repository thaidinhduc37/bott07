"""Port of `chat/chat.controller.ts`. Mounted at `/chat`. Every route requires
auth (current user from the JWT cookie/bearer token)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import AuthenticatedUser, get_current_user, get_db, rate_limit, require_roles
from app.models.enums import RoleCode
from app.schemas.chat import AskDto
from app.services.admin_dashboard_service import AdminDashboardService
from app.services.chat_service import ChatService
from app.services.documents_service import DocumentsService
from app.services.forms_service import FormsService

router = APIRouter(prefix="/chat", tags=["chat"])


def _parse_uuid4(value: str) -> str:
    try:
        parsed = uuid.UUID(value, version=4)
    except ValueError:
        raise HTTPException(status_code=400, detail={"message": "id không hợp lệ"})
    return str(parsed)


def _chat_rate_limit():
    s = get_settings()
    # A single query can cost up to 6 Gemini calls, so disabling the Send
    # button client-side isn't enough — the limit must be enforced server-side.
    return rate_limit("chat_ask", s.rate_limit_chat_per_min)


@router.post("/ask", dependencies=[Depends(_chat_rate_limit())])
async def ask(
    dto: AskDto,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ChatService(db).ask(user.id, dto)


@router.get("/modes")
async def modes(db: AsyncSession = Depends(get_db), _user: AuthenticatedUser = Depends(get_current_user)):
    return await ChatService(db).modes_ready()


@router.get("/courses")
async def courses(db: AsyncSession = Depends(get_db), _user: AuthenticatedUser = Depends(get_current_user)):
    return await ChatService(db).available_courses()


@router.get("/conversations")
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, alias="pageSize"),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ChatService(db).list_conversations(user.id, page=page, page_size=page_size)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation_id = _parse_uuid4(conversation_id)
    return await ChatService(db).get_conversation(user.id, conversation_id)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation_id = _parse_uuid4(conversation_id)
    return await ChatService(db).delete_conversation(user.id, conversation_id)


admin_dashboard_router = APIRouter(prefix="/admin/dashboard", tags=["admin"])


@admin_dashboard_router.get("/rag", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def admin_dashboard_rag(db: AsyncSession = Depends(get_db)):
    return await ChatService(db).get_admin_stats()


@admin_dashboard_router.get("/forms", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def admin_dashboard_forms(db: AsyncSession = Depends(get_db)):
    return await FormsService(db).get_admin_stats()


@admin_dashboard_router.get("/documents", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def admin_dashboard_documents(db: AsyncSession = Depends(get_db)):
    return await DocumentsService(db).get_admin_stats()


@admin_dashboard_router.get("/activity", dependencies=[Depends(require_roles(RoleCode.ADMIN.value))])
async def admin_dashboard_activity(db: AsyncSession = Depends(get_db)):
    return await AdminDashboardService(db).get_activity_stats()
