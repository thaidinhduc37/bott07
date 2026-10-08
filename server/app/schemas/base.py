"""Model Pydantic v2 nền: client React gửi và nhận JSON camelCase, mã Python giữ snake_case (`alias_generator=to_camel`,
`populate_by_name=True`). `extra="forbid"` từ chối mọi trường mà DTO không khai báo."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        from_attributes=True,
    )


class CamelReadModel(BaseModel):
    """Same camelCase aliasing as `CamelModel` but WITHOUT `extra="forbid"` —
    for response models built from ORM objects / dicts we assemble ourselves,
    where forbidding extra fields serves no security purpose and would only
    make the model brittle to add to."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
