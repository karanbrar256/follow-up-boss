"""
Normalized data models for the daily-operations toolkit.

Follow Up Boss returns loosely-typed JSON (booleans as 0/1, optional keys,
several timestamp formats). Everything is normalized here once so the rest of
the toolkit can work with clean, typed objects.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

try:  # Python 3.9+
    from zoneinfo import ZoneInfo

    LOCAL_TZ: Any = ZoneInfo("America/Vancouver")
except Exception:  # pragma: no cover - tzdata missing (e.g. bare Windows)
    LOCAL_TZ = datetime.now().astimezone().tzinfo


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse an FUB timestamp into an aware datetime (UTC if no offset given)."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=LOCAL_TZ)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_date(value: Any) -> Optional[date]:
    """Parse an FUB due date (``YYYY-MM-DD`` or full timestamp) into a local date."""
    if not value:
        return None
    text = str(value).strip()
    if len(text) == 10:
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    dt = parse_dt(text)
    return dt.astimezone(LOCAL_TZ).date() if dt else None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _primary(values: Any) -> Optional[str]:
    """Return the primary (or first) ``value`` from an FUB emails/phones list."""
    if not isinstance(values, list) or not values:
        return None
    for item in values:
        if isinstance(item, dict) and _truthy(item.get("isPrimary")):
            return item.get("value")
    first = values[0]
    return first.get("value") if isinstance(first, dict) else None


@dataclass
class Task:
    id: int
    person_id: Optional[int]
    name: str
    type: str
    due: Optional[date]
    completed: bool

    @classmethod
    def from_fub(cls, raw: Dict[str, Any]) -> "Task":
        return cls(
            id=int(raw.get("id", 0)),
            person_id=raw.get("personId"),
            name=str(raw.get("name") or raw.get("description") or "Task"),
            type=str(raw.get("type") or "Follow Up"),
            due=parse_date(raw.get("dueDate") or raw.get("dueDateTime")),
            completed=_truthy(raw.get("isCompleted") or raw.get("completed")),
        )


@dataclass
class Note:
    id: int
    person_id: Optional[int]
    subject: str
    body: str
    created: Optional[datetime]

    @classmethod
    def from_fub(cls, raw: Dict[str, Any]) -> "Note":
        return cls(
            id=int(raw.get("id", 0)),
            person_id=raw.get("personId"),
            subject=str(raw.get("subject") or ""),
            body=str(raw.get("body") or ""),
            created=parse_dt(raw.get("created")),
        )


@dataclass
class Interaction:
    """A call or text message, in either direction."""

    channel: str  # "call" | "text"
    person_id: Optional[int]
    incoming: bool
    created: Optional[datetime]
    text: str = ""
    outcome: str = ""
    duration: int = 0

    @classmethod
    def from_call(cls, raw: Dict[str, Any]) -> "Interaction":
        return cls(
            channel="call",
            person_id=raw.get("personId"),
            incoming=_truthy(raw.get("isIncoming")),
            created=parse_dt(raw.get("created")),
            text=str(raw.get("note") or ""),
            outcome=str(raw.get("outcome") or ""),
            duration=int(raw.get("duration") or 0),
        )

    @classmethod
    def from_text(cls, raw: Dict[str, Any]) -> "Interaction":
        return cls(
            channel="text",
            person_id=raw.get("personId"),
            incoming=_truthy(raw.get("isIncoming")),
            created=parse_dt(raw.get("created")),
            text=str(raw.get("message") or ""),
        )

    @property
    def is_conversation(self) -> bool:
        """True when this interaction means we actually reached the person."""
        if self.channel == "text":
            return self.incoming
        if self.incoming and self.duration > 0:
            return True
        reached = {"interested", "not interested", "spoke", "connected", "talked"}
        return self.outcome.strip().lower() in reached or self.duration >= 60


@dataclass
class Appointment:
    id: int
    title: str
    start: Optional[datetime]
    person_ids: List[int]
    location: str = ""

    @classmethod
    def from_fub(cls, raw: Dict[str, Any]) -> "Appointment":
        invitees = raw.get("invitees") or []
        ids = [
            int(i["personId"])
            for i in invitees
            if isinstance(i, dict) and i.get("personId")
        ]
        return cls(
            id=int(raw.get("id", 0)),
            title=str(raw.get("title") or "Appointment"),
            start=parse_dt(raw.get("start")),
            person_ids=ids,
            location=str(raw.get("location") or ""),
        )


@dataclass
class PropertyEvent:
    """A website/portal event such as 'Viewed Property' or 'Saved Property'."""

    person_id: Optional[int]
    type: str
    created: Optional[datetime]
    address: str = ""
    price: Optional[int] = None

    @classmethod
    def from_fub(cls, raw: Dict[str, Any]) -> "PropertyEvent":
        prop = raw.get("property") or {}
        address = ", ".join(p for p in [prop.get("street"), prop.get("city")] if p)
        price = prop.get("price")
        return cls(
            person_id=raw.get("personId"),
            type=str(raw.get("type") or ""),
            created=parse_dt(raw.get("created")),
            address=address,
            price=int(price) if price else None,
        )


@dataclass
class Lead:
    id: int
    name: str
    first_name: str
    stage: str
    source: str
    phone: Optional[str]
    email: Optional[str]
    created: Optional[datetime]
    tags: List[str]
    background: str = ""
    price: Optional[int] = None
    custom: Dict[str, Any] = field(default_factory=dict)
    notes: List[Note] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)
    interactions: List[Interaction] = field(default_factory=list)
    appointments: List[Appointment] = field(default_factory=list)
    events: List[PropertyEvent] = field(default_factory=list)

    @classmethod
    def from_fub(cls, raw: Dict[str, Any]) -> "Lead":
        name = str(raw.get("name") or "").strip()
        first = str(raw.get("firstName") or (name.split(" ")[0] if name else "there"))
        custom = {
            k: v
            for k, v in raw.items()
            if k.startswith("custom") and v not in (None, "")
        }
        price = raw.get("price")
        return cls(
            id=int(raw.get("id", 0)),
            name=name or first,
            first_name=first,
            stage=str(raw.get("stage") or "Lead"),
            source=str(raw.get("source") or "Unknown"),
            phone=_primary(raw.get("phones")),
            email=_primary(raw.get("emails")),
            created=parse_dt(raw.get("created")),
            tags=[str(t) for t in (raw.get("tags") or [])],
            background=str(raw.get("background") or ""),
            price=int(price) if price else None,
            custom=custom,
        )

    def has_tag(self, *names: str) -> bool:
        lowered = {t.lower() for t in self.tags}
        return any(n.lower() in lowered for n in names)
