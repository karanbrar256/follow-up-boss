"""
Activity analysis and recent-notes summaries.

Answers the questions you ask yourself before picking up the phone:
When did I last reach them? Did they reply and I missed it? How many times
have I tried since we last spoke? Have I sent listings? Is a showing booked?
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from .models import Appointment, Lead, PropertyEvent

_CONVERSATION_NOTE = re.compile(
    r"\b(spoke|talked|chatted|met with|call with|connected with|had a (?:great |good )?(?:call|chat|conversation))\b"
)
_NEGATED_CONVERSATION = re.compile(
    r"\b(?:didn'?t|did not|couldn'?t|could not|never|no)\s+(?:\w+\s+)?(?:speak|talk|connect|chat)"
)
_LISTINGS_SENT = re.compile(
    r"sent (?:\w+ )?(?:\d+ )?(?:listings?|homes|properties|options)|listing alert|saved search|set up (?:an? )?(?:alert|search)|here are (?:a few|some|\d+)|mls\.ca|realtor\.ca/|rew\.ca/"
)
_SHOWING = re.compile(
    r"\bshowing\b|\bshowed\b|\bviewed .* with\b|\btour(?:ed)?\b|walk-?through"
)


@dataclass
class ActivitySnapshot:
    last_outbound: Optional[datetime] = None
    last_inbound: Optional[datetime] = None
    last_inbound_text: str = ""
    last_inbound_channel: str = ""
    last_conversation: Optional[datetime] = None
    conversations: int = 0
    attempts_since_conversation: int = 0
    unanswered_inbound: bool = False
    listings_sent: bool = False
    listing_alert_set: bool = False
    showing_done: bool = False
    next_appointment: Optional[Appointment] = None
    last_appointment: Optional[Appointment] = None
    recent_property_events: List[PropertyEvent] = field(default_factory=list)
    summary_lines: List[str] = field(default_factory=list)

    @property
    def ever_contacted(self) -> bool:
        return self.last_outbound is not None or self.conversations > 0

    def days_since(self, when: Optional[datetime], as_of: datetime) -> Optional[int]:
        if when is None:
            return None
        return max(0, (as_of.date() - when.astimezone(as_of.tzinfo).date()).days)


def _short(text: str, limit: int = 110) -> str:
    text = " ".join(text.split())
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(first) < 40 and len(text) > len(first):
        first = text
    return first if len(first) <= limit else first[: limit - 1] + "…"


def analyze_activity(
    lead: Lead, as_of: datetime, summary_days: int = 30, summary_limit: int = 4
) -> ActivitySnapshot:
    snap = ActivitySnapshot()
    timeline: List[Tuple[datetime, str]] = []
    conversation_times: List[datetime] = []
    outbound_times: List[datetime] = []

    for ix in lead.interactions:
        if ix.created is None or ix.created > as_of:
            continue
        if ix.incoming:
            if snap.last_inbound is None or ix.created > snap.last_inbound:
                snap.last_inbound = ix.created
                snap.last_inbound_text = ix.text
                snap.last_inbound_channel = ix.channel
        else:
            outbound_times.append(ix.created)
            if ix.channel == "text" and _LISTINGS_SENT.search(ix.text.lower()):
                snap.listings_sent = True
        if ix.is_conversation:
            conversation_times.append(ix.created)

        if ix.channel == "call":
            direction = "in" if ix.incoming else "out"
            outcome = f" ({ix.outcome})" if ix.outcome else ""
            detail = f": {_short(ix.text)}" if ix.text else ""
            timeline.append((ix.created, f"Call {direction}{outcome}{detail}"))
        else:
            direction = "Text in" if ix.incoming else "Text out"
            timeline.append((ix.created, f"{direction}: “{_short(ix.text, 90)}”"))

    for note in lead.notes:
        if note.created is None or note.created > as_of:
            continue
        body = f"{note.subject}. {note.body}".lower()
        if _CONVERSATION_NOTE.search(body) and not _NEGATED_CONVERSATION.search(body):
            conversation_times.append(note.created)
        if _LISTINGS_SENT.search(body):
            snap.listings_sent = True
        if re.search(
            r"listing alert|saved search|set up (?:an? )?(?:alert|search)", body
        ):
            snap.listing_alert_set = True
        if _SHOWING.search(body) and re.search(
            r"\b(showed|toured|viewed|walked through|went through)\b", body
        ):
            snap.showing_done = True
        text = note.body or note.subject
        timeline.append((note.created, f"Note: {_short(text)}"))

    if lead.has_tag("Listings Sent", "Listing Alert", "Saved Search"):
        snap.listings_sent = True
    if lead.has_tag("Listing Alert", "Saved Search"):
        snap.listing_alert_set = True

    for appt in sorted(lead.appointments, key=lambda a: a.start or as_of):
        if appt.start is None:
            continue
        if appt.start >= as_of:
            if snap.next_appointment is None:
                snap.next_appointment = appt
        else:
            snap.last_appointment = appt
            if _SHOWING.search(appt.title.lower()):
                snap.showing_done = True
            conversation_times.append(appt.start)

    recent_cutoff = as_of - timedelta(days=7)
    snap.recent_property_events = sorted(
        (
            e
            for e in lead.events
            if e.created
            and recent_cutoff <= e.created <= as_of
            and "property" in e.type.lower()
        ),
        key=lambda e: e.created or as_of,
        reverse=True,
    )

    snap.conversations = len(conversation_times)
    snap.last_conversation = max(conversation_times) if conversation_times else None
    snap.last_outbound = max(outbound_times) if outbound_times else None
    snap.attempts_since_conversation = sum(
        1
        for t in outbound_times
        if snap.last_conversation is None or t > snap.last_conversation
    )
    snap.unanswered_inbound = snap.last_inbound is not None and (
        snap.last_outbound is None or snap.last_inbound > snap.last_outbound
    )

    cutoff = as_of - timedelta(days=summary_days)
    recent = sorted(
        (t for t in timeline if t[0] >= cutoff), key=lambda t: t[0], reverse=True
    )
    snap.summary_lines = [
        f"{when.astimezone(as_of.tzinfo).strftime('%b %d')} · {text}"
        for when, text in recent[:summary_limit]
    ]
    return snap
