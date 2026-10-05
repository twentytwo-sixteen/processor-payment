from datetime import UTC, datetime

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


def utcnow() -> datetime:
    return datetime.now(UTC)
