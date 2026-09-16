"""Shared Pydantic v2 base model.

The React client sends/expects camelCase JSON (it talks to the Nest API
today); Python code stays snake_case internally. `CamelModel` bridges the two
via `alias_generator=to_camel` + `populate_by_name=True`, and sets
`extra="forbid"` everywhere to replicate Nest's `whitelist: true,
forbidNonWhitelisted: true` validation pipe (reject any field the DTO didn't
declare). Every schema in every future phase should subclass this.
"""

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
