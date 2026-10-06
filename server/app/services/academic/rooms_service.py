"""Danh mục phòng học / phòng thi.

`schedules.room` và `exam_schedules.room` vẫn là chuỗi (tương thích nạp CSV) nên danh mục này KHÔNG
là khóa ngoại: nó để chọn, gợi ý, kiểm tra sức chứa và xem lịch phòng. Vì lịch lưu tên phòng dạng chuỗi,
phòng đã có lịch không được đổi mã / tòa nhà (chỉ ngừng sử dụng), tránh lệch giữa hai nơi.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.core.deps import AuthenticatedUser
from app.models.academic import ExamSchedule, Room, Schedule
from app.schemas.rooms import CreateRoomDto, UpdateRoomDto
from app.services.accounts.audit_service import AuditService

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_TIMETABLE_DAYS = 62
_UNSET = ("", "chưa xếp", "chua xep")


def norm(value: str | None) -> str:
    return (value or "").strip().lower()


def is_unset(room: str | None) -> bool:
    n = norm(room)
    # "Chưa xếp", "Chưa xếp phòng"… đều là chưa có phòng.
    return n in _UNSET or n.startswith(("chưa xếp", "chua xep"))


def same_room(a_code: str | None, a_building: str | None, b_code: str | None, b_building: str | None) -> bool:
    """Cùng phòng: cùng mã (không phân biệt hoa thường); tòa nhà chỉ so khi CẢ HAI đều có."""
    if is_unset(a_code) or norm(a_code) != norm(b_code):
        return False
    ab, bb = norm(a_building), norm(b_building)
    return not (ab and bb and ab != bb)


def match_room(rooms: list[Room], code: str | None, building: str | None) -> Room | None:
    """Phòng trong danh mục khớp với (mã, tòa) của một dòng lịch; ưu tiên khớp cả tòa nhà."""
    exact = [r for r in rooms if same_room(r.code, r.building, code, building)]
    if not exact:
        return None
    with_building = [r for r in exact if norm(r.building) == norm(building) and norm(building)]
    return (with_building or exact)[0]


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=404, detail={"message": "Không tìm thấy phòng"}) from exc


class RoomsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------ dùng chung

    async def all_rooms(self) -> list[Room]:
        return list((await self.db.execute(select(Room))).scalars().all())

    async def _usage(self, room: Room) -> int:
        """Số buổi học + ca thi đang dùng phòng này (khớp theo `same_room`)."""
        total = 0
        for model in (Schedule, ExamSchedule):
            rows = (
                await self.db.execute(
                    select(model.room, model.building).where(func.lower(func.btrim(model.room)) == norm(room.code))
                )
            ).all()
            total += sum(1 for r, b in rows if same_room(room.code, room.building, r, b))
        return total

    async def _item(self, room: Room, usage: int | None = None) -> dict:
        return {
            "id": str(room.id),
            "code": room.code,
            "building": room.building,
            "capacity": room.capacity,
            "kind": room.kind,
            "note": room.note,
            "isActive": room.is_active,
            "usageCount": usage if usage is not None else await self._usage(room),
        }

    async def check_capacity(self, *, room: str | None, building: str | None, headcount: int | None) -> None:
        """Phòng có trong danh mục và có sức chứa mà `headcount` vượt quá → 400 ROOM_TOO_SMALL."""
        if headcount is None or is_unset(room):
            return
        found = match_room(await self.all_rooms(), room, building)
        if found is None or found.capacity is None or headcount <= found.capacity:
            return
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Phòng {found.code} chỉ chứa {found.capacity} chỗ, nhưng cần {headcount} chỗ",
                "code": "ROOM_TOO_SMALL",
            },
        )

    # ------------------------------------------------------------ danh sách

    async def list(self, *, active_only: bool, search: str | None) -> dict:
        stmt = select(Room).order_by(func.lower(func.coalesce(Room.building, "")), func.lower(Room.code))
        if active_only:
            stmt = stmt.where(Room.is_active.is_(True))
        rows = (await self.db.execute(stmt)).scalars().all()
        if search and search.strip():
            q = search.strip().lower()
            rows = [r for r in rows if q in r.code.lower() or q in (r.building or "").lower()]

        # Đếm dùng cho cả danh sách bằng hai truy vấn thay vì N.
        usage = {r.id: 0 for r in rows}
        for model in (Schedule, ExamSchedule):
            for r_code, r_building in (await self.db.execute(select(model.room, model.building))).all():
                for room in rows:
                    if same_room(room.code, room.building, r_code, r_building):
                        usage[room.id] += 1
        return {"items": [await self._item(r, usage[r.id]) for r in rows]}

    # ------------------------------------------------------------ CRUD

    async def _assert_unique(self, code: str, building: str | None, exclude: uuid.UUID | None) -> None:
        stmt = select(Room).where(
            func.lower(Room.code) == code.lower(),
            func.lower(func.coalesce(Room.building, "")) == (building or "").lower(),
        )
        if exclude:
            stmt = stmt.where(Room.id != exclude)
        if (await self.db.execute(stmt)).first():
            raise HTTPException(
                status_code=409, detail={"message": f"Phòng {code} đã có trong danh mục", "code": "ROOM_TAKEN"}
            )

    async def create(self, dto: CreateRoomDto, user: AuthenticatedUser, request: Request | None) -> dict:
        code = dto.code.strip()
        building = dto.building.strip() if dto.building and dto.building.strip() else None
        if not code:
            raise HTTPException(status_code=400, detail={"message": "Mã phòng không được để trống"})
        await self._assert_unique(code, building, None)
        row = Room(
            code=code, building=building, capacity=dto.capacity,
            kind=dto.kind.strip() if dto.kind and dto.kind.strip() else None,
            note=dto.note.strip() if dto.note and dto.note.strip() else None,
        )
        self.db.add(row)
        await self.db.flush()
        rid = row.id
        await self.audit.log(
            action="ROOM_CREATE", user_id=user.id, entity_type="Room", entity_id=str(rid),
            detail={"code": code, "building": building}, request=request,
        )
        await self.db.commit()
        return await self._item(await self.db.get(Room, rid))

    async def update(self, room_id: str, dto: UpdateRoomDto, user: AuthenticatedUser, request: Request | None) -> dict:
        rid = _parse_uuid(room_id)
        row = await self.db.get(Room, rid)
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy phòng"})
        payload = dto.model_dump(exclude_unset=True)
        changes: dict = {}

        new_code = (payload["code"] or "").strip() if "code" in payload else row.code
        new_building = row.building
        if "building" in payload:
            new_building = payload["building"].strip() if payload["building"] and payload["building"].strip() else None
        renamed = norm(new_code) != norm(row.code) or norm(new_building) != norm(row.building)
        if renamed:
            if not new_code:
                raise HTTPException(status_code=400, detail={"message": "Mã phòng không được để trống"})
            if await self._usage(row) > 0:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Phòng đã có lịch nên không đổi mã hoặc tòa nhà được — hãy ngừng sử dụng và tạo phòng mới",
                        "code": "ROOM_IN_USE",
                    },
                )
            await self._assert_unique(new_code, new_building, rid)
        if new_code != row.code:
            changes["code"] = {"from": row.code, "to": new_code}
            row.code = new_code
        if new_building != row.building:
            changes["building"] = {"from": row.building, "to": new_building}
            row.building = new_building
        for field in ("capacity", "kind", "note"):
            if field in payload:
                value = payload[field]
                if isinstance(value, str):
                    value = value.strip() or None
                if value != getattr(row, field):
                    changes[field] = {"from": getattr(row, field), "to": value}
                    setattr(row, field, value)
        if payload.get("is_active") is not None and payload["is_active"] != row.is_active:
            changes["isActive"] = {"from": row.is_active, "to": payload["is_active"]}
            row.is_active = payload["is_active"]

        if changes:
            await self.db.flush()
            await self.audit.log(
                action="ROOM_UPDATE", user_id=user.id, entity_type="Room", entity_id=str(rid),
                detail=changes, request=request,
            )
            await self.db.commit()
        return await self._item(await self.db.get(Room, rid))

    async def delete(self, room_id: str, user: AuthenticatedUser, request: Request | None) -> dict:
        rid = _parse_uuid(room_id)
        row = await self.db.get(Room, rid)
        if not row:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy phòng"})
        n = await self._usage(row)
        if n > 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Phòng còn {n} buổi học/ca thi nên chỉ có thể ngừng sử dụng, không xóa được",
                    "code": "ROOM_IN_USE",
                },
            )
        await self.db.delete(row)
        await self.audit.log(action="ROOM_DELETE", user_id=user.id, entity_type="Room", entity_id=str(rid), request=request)
        await self.db.commit()
        return {"message": "Đã xóa phòng"}

    # ------------------------------------------------------------ lịch phòng

    async def timetable(self, room_id: str, from_: str | None, to: str | None) -> dict:
        rid = _parse_uuid(room_id)
        room = await self.db.get(Room, rid)
        if not room:
            raise HTTPException(status_code=404, detail={"message": "Không tìm thấy phòng"})
        try:
            start_day = date.fromisoformat(from_) if from_ else datetime.now(VN_TZ).date()
            end_day = date.fromisoformat(to) if to else start_day + timedelta(days=14)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"message": "Ngày không hợp lệ (YYYY-MM-DD)"}) from exc
        if end_day < start_day:
            raise HTTPException(status_code=400, detail={"message": "Ngày kết thúc phải sau ngày bắt đầu"})
        if (end_day - start_day).days > MAX_TIMETABLE_DAYS:
            raise HTTPException(status_code=400, detail={"message": f"Chỉ xem tối đa {MAX_TIMETABLE_DAYS} ngày một lần"})

        lo = datetime.combine(start_day, time.min, tzinfo=VN_TZ)
        hi = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=VN_TZ)
        items: list[dict] = []
        for model, kind in ((Schedule, "SESSION"), (ExamSchedule, "EXAM")):
            rows = (
                await self.db.execute(
                    select(model)
                    .options(selectinload(model.course), selectinload(model.study_class))
                    .where(
                        model.starts_at < hi, model.ends_at > lo,
                        func.lower(func.btrim(model.room)) == norm(room.code),
                    )
                )
            ).scalars().unique().all()
            for r in rows:
                if not same_room(room.code, room.building, r.room, r.building):
                    continue
                items.append(
                    {
                        "entryKind": kind,
                        "id": str(r.id),
                        "course": {"code": r.course.code, "name": r.course.name} if r.course else None,
                        "class": {"code": r.study_class.code} if r.study_class else None,
                        "startsAt": r.starts_at.isoformat(),
                        "endsAt": r.ends_at.isoformat(),
                    }
                )
        items.sort(key=lambda x: x["startsAt"])
        return {"room": await self._item(room), "from": start_day.isoformat(), "to": end_day.isoformat(), "items": items}
