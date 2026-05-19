from app.services.segment_filter_dsl import (
    SegmentDefinitionError,
    normalize_definition,
    validate_definition,
)


def test_normalize_legacy_group_definition():
    legacy = {
        "operator": "and",
        "conditions": [
            {"field": "name", "operator": "contains", "value": "john"},
            {"field": "phone", "operator": "eq", "value": "+100"},
        ],
    }
    normalized = normalize_definition(legacy)
    assert normalized["op"] == "and"
    assert len(normalized["children"]) == 2
    assert normalized["children"][0]["op"] == "contains"


def test_validate_nested_and_or_groups():
    definition = {
        "op": "and",
        "children": [
            {"op": "has_tag", "tag": "vip"},
            {
                "op": "or",
                "children": [
                    {"op": "eq", "field": "name", "value": "Alice"},
                    {"op": "contains", "field": "phone", "value": "+1"},
                ],
            },
        ],
    }
    validate_definition(definition)


def test_validate_rejects_malformed_payload():
    malformed = {"op": "and", "children": []}
    try:
        validate_definition(malformed)
    except SegmentDefinitionError as exc:
        assert "requires non-empty children" in str(exc)
    else:
        raise AssertionError("Expected SegmentDefinitionError")


def test_validate_empty_conditions_rejected():
    malformed = {"operator": "or", "conditions": []}
    try:
        validate_definition(malformed)
    except SegmentDefinitionError as exc:
        assert "requires non-empty children" in str(exc)
    else:
        raise AssertionError("Expected SegmentDefinitionError")
