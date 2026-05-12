import re

NUMBER_VARIABLE_PATTERN = re.compile(r"\{\{\s*(\d+)\s*\}\}")


def extract_number_placeholders(text: str) -> list[int]:
    numbers: list[int] = []
    seen: set[int] = set()
    for match in NUMBER_VARIABLE_PATTERN.finditer(text):
        number = int(match.group(1))
        if number in seen:
            continue
        seen.add(number)
        numbers.append(number)
    numbers.sort()
    return numbers


def build_order_event_template_parameters(
    text: str,
    *,
    customer_name: str,
    order_id: str,
    amount: str,
    phone: str,
) -> list[str]:
    """Map Meta-style {{1}}..{{n}} in template body/header to order fields for Cloud API."""
    placeholders = extract_number_placeholders(text)
    if not placeholders:
        return []

    mapping: dict[int, str] = {
        1: customer_name or "Customer",
        2: order_id or "",
        3: amount or "",
        4: phone or "",
    }
    return [str(mapping.get(i, f"Value {i}")) for i in placeholders]


def build_numbered_template_parameters(text: str, name: str, phone: str) -> list[str]:
    placeholders = extract_number_placeholders(text)
    if not placeholders:
        return []

    values: list[str] = []
    for index in placeholders:
        if index == 1:
            values.append(name or "Customer")
        elif index == 2:
            values.append(phone)
        else:
            values.append(f"Value {index}")
    return values
