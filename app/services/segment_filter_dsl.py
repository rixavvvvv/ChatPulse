from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, not_, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.contact import Contact
from app.models.contact_intelligence import (
    AttributeDefinition,
    ContactAttributeValue,
    ContactTag,
    Tag,
)


class SegmentDefinitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CompiledFilter:
    where_clause: ColumnElement[bool]


def validate_definition(definition: dict[str, Any]) -> None:
    if not isinstance(definition, dict):
        raise SegmentDefinitionError("definition must be an object")
    op = definition.get("op")
    if op not in {"and", "or", "not", "eq", "neq", "contains", "in", "gt", "gte", "lt", "lte", "has_tag", "attr"}:
        raise SegmentDefinitionError(f"unsupported op: {op}")

    if op in {"and", "or"}:
        children = definition.get("children")
        if not isinstance(children, list) or not children:
            raise SegmentDefinitionError(f"{op} requires non-empty children")
        for child in children:
            validate_definition(child)
        return

    if op == "not":
        child = definition.get("child")
        if not isinstance(child, dict):
            raise SegmentDefinitionError("not requires child object")
        validate_definition(child)
        return

    if op in {"eq", "neq", "contains", "in", "gt", "gte", "lt", "lte"}:
        field = definition.get("field")
        if field not in {"name", "phone", "created_at"}:
            raise SegmentDefinitionError("invalid field")
        if op == "in":
            values = definition.get("values")
            if not isinstance(values, list) or not values:
                raise SegmentDefinitionError("in requires non-empty values")
        else:
            if "value" not in definition:
                raise SegmentDefinitionError(f"{op} requires value")
        return

    if op == "has_tag":
        tag = definition.get("tag")
        if not isinstance(tag, str) or not tag.strip():
            raise SegmentDefinitionError("has_tag requires tag")
        return

    if op == "attr":
        key = definition.get("key")
        if not isinstance(key, str) or not key.strip():
            raise SegmentDefinitionError("attr requires key")
        cmp_op = definition.get("cmp")
        if cmp_op not in {"eq", "neq", "contains", "gt", "gte", "lt", "lte"}:
            raise SegmentDefinitionError("attr cmp unsupported")
        if "value" not in definition:
            raise SegmentDefinitionError("attr requires value")
        return


def compile_to_where_clause(*, workspace_id: int, definition: dict[str, Any]) -> CompiledFilter:
    validate_definition(definition)
    clause = _compile_node(workspace_id=workspace_id, node=definition)
    return CompiledFilter(where_clause=clause)


def _compile_node(*, workspace_id: int, node: dict[str, Any]) -> ColumnElement[bool]:
    op = node["op"]

    if op == "and":
        return and_(*[_compile_node(workspace_id=workspace_id, node=c) for c in node["children"]])
    if op == "or":
        return or_(*[_compile_node(workspace_id=workspace_id, node=c) for c in node["children"]])
    if op == "not":
        return not_(_compile_node(workspace_id=workspace_id, node=node["child"]))

    if op in {"eq", "neq", "contains", "in", "gt", "gte", "lt", "lte"}:
        field = node["field"]
        col = _contact_field(field)
        if op == "in":
            values = node["values"]
            return col.in_(values)
        value = node.get("value")
        if field == "created_at" and isinstance(value, str):
            value = _parse_iso(value)
        if op == "eq":
            return col == value
        if op == "neq":
            return col != value
        if op == "contains":
            if not isinstance(value, str):
                raise SegmentDefinitionError("contains requires string value")
            return col.ilike(f"%{value}%")
        if op == "gt":
            return col > value
        if op == "gte":
            return col >= value
        if op == "lt":
            return col < value
        if op == "lte":
            return col <= value

    if op == "has_tag":
        tag_name = node["tag"].strip()
        tag_subq = (
            select(Tag.id)
            .where(Tag.workspace_id == workspace_id, Tag.name == tag_name)
            .subquery()
        )
        return exists(
            select(ContactTag.id).where(
                ContactTag.workspace_id == workspace_id,
                ContactTag.contact_id == Contact.id,
                ContactTag.tag_id.in_(select(tag_subq.c.id)),
            )
        )

    if op == "attr":
        key = node["key"].strip()
        cmp_op = node["cmp"]
        value = node.get("value")

        def_subq = (
            select(AttributeDefinition.id, AttributeDefinition.type)
            .where(AttributeDefinition.workspace_id == workspace_id, AttributeDefinition.key == key)
            .subquery()
        )

        # Existence + predicate on the correct value column.
        base = (
            select(ContactAttributeValue.id)
            .where(
                ContactAttributeValue.workspace_id == workspace_id,
                ContactAttributeValue.contact_id == Contact.id,
                ContactAttributeValue.attribute_definition_id.in_(select(def_subq.c.id)),
            )
        )

        # Conservative: treat non-string values as direct comparisons; caller should align types.
        if cmp_op == "contains":
            if not isinstance(value, str):
                raise SegmentDefinitionError("attr contains requires string value")
            pred = ContactAttributeValue.value_text.ilike(f"%{value}%")
        else:
            # Compare across all columns; only one should be set for a given def.
            if cmp_op == "eq":
                pred = or_(
                    ContactAttributeValue.value_text == value,
                    ContactAttributeValue.value_number == value,
                    ContactAttributeValue.value_bool == value,
                )
            elif cmp_op == "neq":
                pred = or_(
                    ContactAttributeValue.value_text != value,
                    ContactAttributeValue.value_number != value,
                    ContactAttributeValue.value_bool != value,
                )
            elif cmp_op in {"gt", "gte", "lt", "lte"}:
                col = ContactAttributeValue.value_number
                if cmp_op == "gt":
                    pred = col > value
                elif cmp_op == "gte":
                    pred = col >= value
                elif cmp_op == "lt":
                    pred = col < value
                else:
                    pred = col <= value
            else:
                raise SegmentDefinitionError("attr cmp unsupported")

        return exists(base.where(pred))

    raise SegmentDefinitionError(f"unsupported op: {op}")


def _contact_field(field: str):
    if field == "name":
        return Contact.name
    if field == "phone":
        return Contact.phone
    if field == "created_at":
        return Contact.created_at
    raise SegmentDefinitionError("invalid field")


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SegmentDefinitionError("created_at must be ISO datetime") from exc

