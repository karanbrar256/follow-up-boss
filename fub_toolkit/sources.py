"""
Data sources for the toolkit.

Every source returns the same FUB-shaped bundle::

    {"people": [...], "tasks": [...], "notes": [...], "calls": [...],
     "textMessages": [...], "appointments": [...], "events": [...]}

* ``MockSource``       – realistic fictional data (default; no network).
* ``JsonFileSource``   – a bundle saved to disk (e.g. a redacted export).
* ``LiveReadOnlySource`` – Follow Up Boss API, GET requests only. Disabled
  unless ``FUB_TOOLKIT_ALLOW_LIVE=1`` is set. See docs/FUB_TOOLKIT.md.
"""

import json
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .models import Appointment, Interaction, Lead, Note, PropertyEvent, Task

Bundle = Dict[str, List[Dict[str, Any]]]
BUNDLE_KEYS = (
    "people",
    "tasks",
    "notes",
    "calls",
    "textMessages",
    "appointments",
    "events",
)


class LiveAccessDisabled(RuntimeError):
    """Raised when live access is attempted without explicit opt-in."""


class ReadOnlyViolation(PermissionError):
    """Raised if anything tries to write to Follow Up Boss through the toolkit."""


class MockSource:
    def __init__(self, as_of: datetime) -> None:
        self.as_of = as_of

    def load(self) -> Bundle:
        from .mock_data import build_mock_bundle

        return build_mock_bundle(self.as_of)


class JsonFileSource:
    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> Bundle:
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        return {key: list(data.get(key, [])) for key in BUNDLE_KEYS}


def make_read_only_client(api_key: Optional[str] = None, **kwargs: Any) -> Any:
    """Build an SDK client whose write methods are hard-disabled."""
    from follow_up_boss.client import FollowUpBossApiClient

    class ReadOnlyClient(FollowUpBossApiClient):
        def _request(self, method: str, endpoint: str, *args: Any, **kw: Any) -> Any:
            if method.upper() != "GET":
                raise ReadOnlyViolation(
                    f"Toolkit is read-only; blocked {method} {endpoint}"
                )
            return super()._request(method, endpoint, *args, **kw)

        def _post(self, *args: Any, **kw: Any) -> Any:
            raise ReadOnlyViolation("Toolkit is read-only; POST blocked")

        def _put(self, *args: Any, **kw: Any) -> Any:
            raise ReadOnlyViolation("Toolkit is read-only; PUT blocked")

        def _delete(self, *args: Any, **kw: Any) -> Any:
            raise ReadOnlyViolation("Toolkit is read-only; DELETE blocked")

    return ReadOnlyClient(api_key=api_key, **kwargs)


class LiveReadOnlySource:
    """Pulls data from Follow Up Boss using GET requests only.

    Not exercised against a real account yet — parameter names below follow
    the existing SDK and FUB docs but must be verified in a supervised dry run
    before trusting the output. Guard rails:

    * requires ``FUB_TOOLKIT_ALLOW_LIVE=1`` in the environment;
    * the client refuses any non-GET request;
    * caps the number of people and pages fetched;
    * never writes client data to disk itself.
    """

    def __init__(
        self,
        client: Any = None,
        max_people: int = 1000,
        page_size: int = 100,
        max_pages: int = 20,
        per_request_pause: float = 0.2,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        env = dict(os.environ if env is None else env)
        if env.get("FUB_TOOLKIT_ALLOW_LIVE") != "1":
            raise LiveAccessDisabled(
                "Live Follow Up Boss access is disabled. Complete the checklist in "
                "docs/FUB_TOOLKIT.md, then set FUB_TOOLKIT_ALLOW_LIVE=1."
            )
        self.client = client or make_read_only_client(
            api_key=env.get("FOLLOW_UP_BOSS_API_KEY")
        )
        self.max_people = max_people
        self.page_size = page_size
        self.max_pages = max_pages
        self.pause = per_request_pause

    def _with_backoff(self, fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        """Call ``fn``; on a rate-limit (429) wait and retry up to 3 times."""
        from follow_up_boss.client import FollowUpBossRateLimitError

        for attempt in range(4):
            time.sleep(self.pause)
            try:
                return fn()
            except FollowUpBossRateLimitError:
                if attempt == 3:
                    raise
                time.sleep(10 * (attempt + 1))
        return {}  # pragma: no cover

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        response: Dict[str, Any] = self._with_backoff(
            lambda: self.client._get(endpoint, params=params)
        )
        return response

    def _paged(
        self, endpoint: str, key: str, params: Dict[str, Any], limit: int
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        response = self._get(endpoint, dict(params, limit=self.page_size))
        for _ in range(self.max_pages):
            out.extend(response.get(key, []))
            next_link = (response.get("_metadata") or {}).get("nextLink")
            if len(out) >= limit or not next_link:
                break
            response = self._with_backoff(lambda: self.client.get_absolute(next_link))
        return out[:limit]

    def load(self) -> Bundle:
        bundle: Bundle = {key: [] for key in BUNDLE_KEYS}
        people = self._paged("people", "people", {"sort": "-updated"}, self.max_people)
        bundle["people"] = people
        bundle["tasks"] = self._paged(
            "tasks", "tasks", {}, self.page_size * self.max_pages
        )
        bundle["appointments"] = self._paged(
            "appointments", "appointments", {}, self.page_size
        )
        from .playbook import EXCLUDED_STAGES

        for person in people:
            pid = person.get("id")
            if pid is None or str(person.get("stage", "")).lower() in EXCLUDED_STAGES:
                continue  # Trash/Closed: no need to pull their history
            for endpoint, key in (
                ("notes", "notes"),
                ("calls", "calls"),
                ("textMessages", "textmessages"),
                ("events", "events"),
            ):
                resp = self._get(
                    endpoint, {"personId": pid, "limit": 25, "sort": "-created"}
                )
                items = resp.get(key) or resp.get(endpoint) or []
                bundle[endpoint].extend(items)
        return bundle


def build_leads(bundle: Bundle) -> List[Lead]:
    """Normalize a bundle and attach each record to its lead."""
    leads = {
        int(p["id"]): Lead.from_fub(p)
        for p in bundle.get("people", [])
        if p.get("id") is not None
    }

    def attach(
        items: List[Dict[str, Any]], factory: Callable[[Dict[str, Any]], Any], attr: str
    ) -> None:
        for raw in items:
            obj = factory(raw)
            pid = getattr(obj, "person_id", None)
            if pid is not None and int(pid) in leads:
                getattr(leads[int(pid)], attr).append(obj)

    attach(bundle.get("tasks", []), Task.from_fub, "tasks")
    attach(bundle.get("notes", []), Note.from_fub, "notes")
    attach(bundle.get("calls", []), Interaction.from_call, "interactions")
    attach(bundle.get("textMessages", []), Interaction.from_text, "interactions")
    attach(bundle.get("events", []), PropertyEvent.from_fub, "events")
    for raw in bundle.get("appointments", []):
        appt = Appointment.from_fub(raw)
        for pid in appt.person_ids:
            if pid in leads:
                leads[pid].appointments.append(appt)
    return list(leads.values())
