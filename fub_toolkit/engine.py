"""
Urgency scoring, lead temperature and next-best-action recommendations.

Every point awarded comes with a plain-English reason so the ranking can be
checked (and tuned) instead of trusted blindly. Weights live in ``WEIGHTS``.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .activity import ActivitySnapshot, analyze_activity
from .criteria import AREAS, BuyerCriteria, extract_criteria, fmt_price
from .models import Lead, Task

WEIGHTS: Dict[str, int] = {
    "unanswered_inbound": 100,
    "new_lead_uncontacted": 90,
    "new_lead_under_24h_bonus": 10,
    "old_lead_uncontacted": 60,
    "appointment_within_48h": 40,
    "overdue_task_each": 12,
    "overdue_task_max_days_bonus": 15,
    "due_today_task_each": 8,
    "follow_up_due": 25,
    "follow_up_overdue_per_day": 3,
    "follow_up_overdue_cap": 20,
    "property_activity_3d": 20,
    "property_activity_7d": 10,
    "timeline_3m": 20,
    "timeline_6m": 10,
    "financing_ready": 10,
    "low_intent_penalty": -15,
    "unreachable_penalty": -20,
}

CLOSED_STAGES = {"closed", "trash", "archived"}
TRANSACTION_STAGES = {"pending", "under contract"}
SPHERE_STAGES = {"past client", "sphere"}
HOT_STAGES = {"hot prospect", "hot", "active client"}
NURTURE_STAGES = {"nurture", "cold", "long term"}
STOP_FLAGS = {
    "Do not contact",
    "Bad number",
    "Already bought",
    "Working with another agent",
}

# Days between touches once you've had a conversation.
CADENCE_DAYS = {"Hot": 2, "Warm": 4, "Nurture": 21, "Sphere": 90}
UNREACHABLE_ATTEMPTS = 6


@dataclass
class Action:
    code: str
    label: str
    channel: str  # "Call" | "Text" | "Email" | "CRM"
    why: str
    text_draft: str = ""
    talking_points: List[str] = field(default_factory=list)
    crm_update: str = ""
    follow_up: Optional[date] = None


@dataclass
class LeadInsight:
    lead: Lead
    criteria: BuyerCriteria
    activity: ActivitySnapshot
    overdue_tasks: List[Task]
    due_today_tasks: List[Task]
    temperature: str
    score: int
    reasons: List[str]
    action: Action
    due: bool
    excluded_reason: str = ""

    @property
    def on_call_list(self) -> bool:
        return not self.excluded_reason and self.due and self.action.channel == "Call"

    @property
    def on_value_list(self) -> bool:
        return (
            not self.excluded_reason
            and self.due
            and self.action.channel in {"Text", "Email"}
        )


_PROPER = {w.lower() for name in AREAS.values() for w in re.findall(r"[A-Za-z]+", name)}
_RESOURCE = re.compile(
    r"\b(guide|report|checklist|webinar|seminar|list|ebook|calculator)$", re.I
)


def ad_topic(lead: Lead, criteria: BuyerCriteria) -> str:
    """Turn 'Facebook - Langley Townhomes Ad' into 'Langley townhomes'.

    Place names keep their capitals; free resources get 'the' in front
    ("the first-time buyer guide").
    """
    parts = re.split(r"\s[-–|:]\s", lead.source, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        topic = re.sub(
            r"\b(ad|ads|campaign|lead form|form)\b", "", parts[1], flags=re.I
        ).strip()
        if topic:
            words = [
                (
                    w
                    if w.lower() in _PROPER or not w.isalpha() and "-" not in w
                    else w.lower()
                )
                for w in topic.split()
            ]
            topic = " ".join(words)
            return f"the {topic}" if _RESOURCE.search(topic) else topic
    return search_phrase(criteria) or "homes in the area"


def search_phrase(c: BuyerCriteria) -> str:
    kind = c.property_types[0].split(" / ")[0].lower() if c.property_types else "homes"
    if kind in {"townhouse", "condo", "duplex", "rancher"}:
        kind += "s"
    elif kind == "detached":
        kind = "detached homes"
    elif kind == "acreage":
        kind = "acreages"
    where = f" in {c.areas[0]}" if c.areas else ""
    budget = f" {c.budget_label}" if c.budget_label else ""
    return f"{kind}{where}{budget}".strip() if (c.property_types or c.areas) else ""


def _temperature(
    lead: Lead, c: BuyerCriteria, a: ActivitySnapshot, as_of: datetime
) -> str:
    stage = lead.stage.lower()
    if stage in SPHERE_STAGES:
        return "Sphere"
    unreachable = (
        a.conversations == 0 and a.attempts_since_conversation >= UNREACHABLE_ATTEMPTS
    )
    if stage in NURTURE_STAGES or "Just browsing" in c.flags or unreachable:
        return "Nurture"
    if c.timeline_months is not None and c.timeline_months > 6:
        return "Nurture"
    recent_inbound = a.unanswered_inbound and a.days_since(a.last_inbound, as_of) in (
        0,
        1,
    )
    if (
        stage in HOT_STAGES
        or (c.timeline_months is not None and c.timeline_months <= 3)
        or recent_inbound
        or a.next_appointment is not None
        or len(a.recent_property_events) >= 2
        or (c.pre_approved and c.timeline_months is not None and c.timeline_months <= 6)
    ):
        return "Hot"
    return "Warm"


def _next_touch_due(temp: str, lead: Lead, a: ActivitySnapshot) -> Optional[datetime]:
    """When the next outbound touch is due, based on cadence."""
    last = a.last_outbound
    if last is None:
        return lead.created
    if a.conversations == 0:
        n = a.attempts_since_conversation
        gap = 1 if n < 3 else 3 if n < UNREACHABLE_ATTEMPTS else 14
        return last + timedelta(days=gap)
    reference = max(t for t in (last, a.last_conversation) if t is not None)
    return reference + timedelta(days=CADENCE_DAYS.get(temp, 4))


def _weekday_options(as_of: datetime) -> str:
    first = as_of + timedelta(days=1)
    second = as_of + timedelta(days=2)
    return f"{first.strftime('%A')} or {second.strftime('%A')}"


def _recommend(
    lead: Lead,
    c: BuyerCriteria,
    a: ActivitySnapshot,
    temp: str,
    as_of: datetime,
    agent: str,
) -> Action:
    today = as_of.date()
    first = lead.first_name
    topic = ad_topic(lead, c)
    looking = search_phrase(c) or topic
    questions = c.missing_questions()

    if a.unanswered_inbound:
        hours = (
            int((as_of - a.last_inbound).total_seconds() // 3600)
            if a.last_inbound
            else 0
        )
        said = (
            f"“{a.last_inbound_text.strip()[:120]}”"
            if a.last_inbound_text
            else "(incoming call)"
        )
        return Action(
            code="reply_now",
            label="Reply now — they reached out",
            channel="Call",
            why=f"Their last {a.last_inbound_channel or 'message'} ({hours}h ago) hasn't been answered: {said}",
            text_draft=f"Hi {first}, thanks for getting back to me — happy to help with that. Do you have 5 minutes for a quick call today?",
            talking_points=["Answer their question first"] + questions,
            follow_up=today + timedelta(days=1),
        )

    appt = a.next_appointment
    if appt and appt.start and appt.start - as_of <= timedelta(hours=48):
        local = appt.start.astimezone(as_of.tzinfo)
        day = (
            "tomorrow"
            if local.date() == today + timedelta(days=1)
            else "today" if local.date() == today else local.strftime("%A")
        )
        clock = f"{local.hour % 12 or 12}:{local.minute:02d} {'a.m.' if local.hour < 12 else 'p.m.'}"
        kind, _, detail = appt.title.partition(" - ")
        what = f"our {kind.strip().lower()}" + (
            f" ({detail.strip()})" if detail.strip() else ""
        )
        points = ["Confirm all decision makers are attending"]
        if not c.cash_buyer and c.pre_approved is not True:
            points.append("Check where they are with pre-approval")
        return Action(
            code="confirm_appointment",
            label="Confirm appointment",
            channel="Text",
            why=f"{appt.title} is booked for {day} at {clock}",
            text_draft=f"Hi {first}, just confirming {what} {day} at {clock}{' — meeting at ' + appt.location if appt.location else ''}. Looking forward to it!",
            talking_points=points,
            follow_up=local.date(),
        )

    if not a.ever_contacted:
        return Action(
            code="speed_to_lead",
            label="New lead — call now",
            channel="Call",
            why=f"New {lead.source} lead, not contacted yet. Speed to lead matters most in the first hour.",
            text_draft=f"Hi {first}, it's {agent} — I saw you were checking out {topic} on Facebook. Are you looking to buy in the next few months, or keeping an eye on the market for now?",
            talking_points=["Call twice back-to-back, then send the text if no answer"]
            + questions,
            crm_update="Log the call outcome in FUB",
            follow_up=today + timedelta(days=1),
        )

    if a.conversations == 0:
        n = a.attempts_since_conversation
        if n >= UNREACHABLE_ATTEMPTS:
            return Action(
                code="move_to_nurture",
                label="Move to long-term nurture",
                channel="Text",
                why=f"{n} attempts with no conversation. Stop chasing; switch to value-based nurture.",
                text_draft=f"Hi {first}, I haven't been able to catch you, so I'll stop reaching out for now. If you'd like me to keep an eye out for {topic}, just reply and I'll set it up.",
                crm_update="Move stage to Nurture; add to monthly market-update email",
                follow_up=today + timedelta(days=30),
            )
        if n >= 3:
            draft = (
                f"Hi {first}, {agent} here. A few new {looking} just came up — want me to send them over?"
                if n < 5
                else f"Hi {first}, quick one — are you still looking at {topic}, or should I check back in a few months?"
            )
        else:
            draft = f"Hi {first}, it's {agent} following up on your enquiry about {topic}. When's a good time for a quick call?"
        return Action(
            code="attempt_contact",
            label=f"Contact attempt #{n + 1}",
            channel="Call",
            why=f"{n} attempt{'s' if n != 1 else ''} so far, no conversation yet.",
            text_draft=draft,
            talking_points=questions,
            follow_up=today + timedelta(days=1 if n < 3 else 3),
        )

    if temp == "Sphere":
        return Action(
            code="referral_touch",
            label="Past client check-in",
            channel="Call",
            why="Keep in touch with past clients and sphere; ask for referrals.",
            text_draft=f"Hi {first}, {agent} here — just checking in. How's everything with the house? If anyone you know is thinking of buying or selling, I'd be glad to help.",
            follow_up=today + timedelta(days=90),
        )

    if temp == "Nurture":
        area = c.areas[0] if c.areas else "your area"
        return Action(
            code="nurture_value",
            label="Send something of value",
            channel="Text",
            why="Long-term lead. Stay useful and top of mind without pushing.",
            text_draft=f"Hi {first}, {agent} here. I'm keeping an eye on {looking or 'the market'} for you. Want me to send the latest listings or a quick {area} market snapshot?",
            talking_points=[
                "Attach current stats from the FVREB/GVR monthly report — don't quote numbers from memory"
            ],
            crm_update="Confirm they're on a listing alert and monthly market email",
            follow_up=today
            + timedelta(
                days=14 if c.timeline_months and c.timeline_months <= 9 else 30
            ),
        )

    if not c.is_qualified:
        return Action(
            code="qualify",
            label="Qualification call",
            channel="Call",
            why="Talked before but still missing: "
            + ", ".join(c.missing_labels()[:4])
            + ".",
            text_draft=f"Hi {first}, {agent} here. So I only send you homes that actually fit, can we take 5 minutes today to go over what you're looking for?",
            talking_points=questions,
            follow_up=today + timedelta(days=2),
        )

    if (
        c.pre_approved is not True
        and not c.cash_buyer
        and (c.timeline_months or 12) <= 6
    ):
        return Action(
            code="broker_intro",
            label="Offer mortgage broker intro",
            channel="Call",
            why="Qualified and buying within 6 months, but no confirmed pre-approval.",
            text_draft=f"Hi {first}, before we start viewing it's worth getting pre-approved so you know your exact number and can move quickly. I work with a couple of great mortgage brokers — want an intro?",
            talking_points=[
                "Offer 2 broker names",
                "Book the showing once pre-approval is under way",
            ],
            crm_update="Add tag 'Broker Intro' and a task to check in with the broker",
            follow_up=today + timedelta(days=3),
        )

    if not a.listings_sent:
        return Action(
            code="send_listings",
            label="Set up alert + send 3 listings",
            channel="Text",
            why="Criteria are clear but no listings have been sent yet.",
            text_draft=f"Hi {first}, I set up a search for {looking}. Here are 3 that stand out — let me know which ones you'd like to see in person.",
            talking_points=["Hand-pick 3 listings; don't just forward the alert"],
            crm_update="Add tag 'Listing Alert' once the saved search is live",
            follow_up=today + timedelta(days=2),
        )

    if a.showing_done:
        return Action(
            code="showing_follow_up",
            label="Showing debrief + next step",
            channel="Call",
            why="They've seen homes with you. Lock in the next step while it's fresh.",
            text_draft=f"Hi {first}, what did you think after seeing those homes? I have a couple more that fit what you liked — want to see them {_weekday_options(as_of)}?",
            talking_points=[
                "What did they like/dislike?",
                "Adjust criteria",
                "Book the next showing or a buyer consultation",
            ],
            follow_up=today + timedelta(days=2),
        )

    event = a.recent_property_events[0] if a.recent_property_events else None
    viewed = (
        f"I noticed you were looking at {event.address}. "
        if event and event.address
        else ""
    )
    return Action(
        code="book_showing",
        label="Book a showing",
        channel="Call",
        why="Listings sent, criteria clear, no showing booked yet."
        + (f" Recently viewed {event.address}." if event and viewed else ""),
        text_draft=(
            f"Hi {first}, {viewed}Want to go see it in person? I have {_weekday_options(as_of)} open."
            if viewed
            else f"Hi {first}, want to go see a few of the homes from your search in person? I have {_weekday_options(as_of)} open."
        ),
        talking_points=["Offer two specific times", "Confirm who needs to be there"],
        follow_up=today + timedelta(days=2),
    )


def build_insight(lead: Lead, as_of: datetime, agent: str = "Karan") -> LeadInsight:
    c = extract_criteria(lead, as_of)
    a = analyze_activity(lead, as_of)
    today = as_of.date()
    open_tasks = [t for t in lead.tasks if not t.completed and t.due]
    overdue = sorted(
        (t for t in open_tasks if t.due and t.due < today), key=lambda t: t.due or today
    )
    due_today = [t for t in open_tasks if t.due == today]
    temp = _temperature(lead, c, a, as_of)

    stage = lead.stage.lower()
    excluded = ""
    if stage in CLOSED_STAGES:
        excluded = f"Stage is {lead.stage}"
    elif stage in TRANSACTION_STAGES:
        excluded = "Under contract — manage in your transaction workflow"
    elif lead.has_tag("DNC", "Do Not Contact"):
        excluded = "Tagged Do Not Contact"
    else:
        stop = [f for f in c.flags if f in STOP_FLAGS]
        if stop:
            excluded = f"Flagged in notes: {', '.join(stop)} — review and update stage"

    score = 0
    reasons: List[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    if a.unanswered_inbound:
        add(WEIGHTS["unanswered_inbound"], "They replied and haven't heard back")
    if not a.ever_contacted:
        age_h = (as_of - lead.created).total_seconds() / 3600 if lead.created else 999
        if age_h <= 24 * 7:
            add(WEIGHTS["new_lead_uncontacted"], "New lead, never contacted")
            if age_h <= 24:
                add(WEIGHTS["new_lead_under_24h_bonus"], "Came in within the last 24h")
        else:
            add(
                WEIGHTS["old_lead_uncontacted"],
                f"Never contacted ({int(age_h // 24)} days old)",
            )
    if (
        a.next_appointment
        and a.next_appointment.start
        and a.next_appointment.start - as_of <= timedelta(hours=48)
    ):
        add(WEIGHTS["appointment_within_48h"], "Appointment in the next 48h")
    if overdue:
        worst = (today - overdue[0].due).days  # type: ignore[operator]
        add(
            WEIGHTS["overdue_task_each"] * min(3, len(overdue))
            + min(WEIGHTS["overdue_task_max_days_bonus"], worst),
            f"{len(overdue)} overdue task{'s' if len(overdue) > 1 else ''} (oldest {worst}d)",
        )
    if due_today:
        add(
            WEIGHTS["due_today_task_each"] * min(2, len(due_today)),
            f"{len(due_today)} task(s) due today",
        )

    next_touch = _next_touch_due(temp, lead, a)
    touch_due = (
        next_touch is not None and next_touch.astimezone(as_of.tzinfo).date() <= today
    )
    if touch_due and a.ever_contacted and not a.unanswered_inbound:
        days_over = (today - next_touch.astimezone(as_of.tzinfo).date()).days  # type: ignore[union-attr]
        since = a.days_since(a.last_outbound, as_of)
        reason = (
            f"Follow-up due ({since}d since last touch; {temp} cadence)"
            if a.conversations
            else f"Next attempt due ({since}d since last try)"
        )
        add(
            WEIGHTS["follow_up_due"]
            + min(
                WEIGHTS["follow_up_overdue_cap"],
                WEIGHTS["follow_up_overdue_per_day"] * days_over,
            ),
            reason,
        )
    if a.recent_property_events:
        newest = a.recent_property_events[0]
        days = a.days_since(newest.created, as_of) or 0
        what = f"{newest.type.lower()} {newest.address}".strip()
        add(
            WEIGHTS["property_activity_3d" if days <= 3 else "property_activity_7d"],
            f"Recent activity: {what}",
        )
    if c.timeline_months is not None and c.timeline_months <= 3:
        add(WEIGHTS["timeline_3m"], f"Timeline: {c.timeline_label}")
    elif c.timeline_months is not None and c.timeline_months <= 6:
        add(WEIGHTS["timeline_6m"], f"Timeline: {c.timeline_label}")
    if c.pre_approved or c.cash_buyer:
        add(WEIGHTS["financing_ready"], "Financing ready (" + c.financing_label + ")")
    if "Just browsing" in c.flags or "Not interested" in c.flags:
        add(WEIGHTS["low_intent_penalty"], "Low intent mentioned")
    if a.conversations == 0 and a.attempts_since_conversation >= UNREACHABLE_ATTEMPTS:
        add(
            WEIGHTS["unreachable_penalty"],
            f"{a.attempts_since_conversation} attempts, never reached",
        )

    action = _recommend(lead, c, a, temp, as_of, agent)
    one_time = action.code == "confirm_appointment" or (
        action.code == "move_to_nurture" and stage not in NURTURE_STAGES
    )
    due = bool(a.unanswered_inbound or overdue or due_today or touch_due or one_time)
    if excluded:
        score = 0
        action = Action(
            code="update_crm",
            label="Update CRM status",
            channel="CRM",
            why=excluded,
            crm_update="Confirm and update stage/tags so this lead stops appearing",
        )
    return LeadInsight(
        lead=lead,
        criteria=c,
        activity=a,
        overdue_tasks=overdue,
        due_today_tasks=due_today,
        temperature=temp,
        score=max(0, score),
        reasons=reasons,
        action=action,
        due=due,
        excluded_reason=excluded,
    )


_TEMP_ORDER = {"Hot": 0, "Warm": 1, "Nurture": 2, "Sphere": 3}


def rank(insights: List[LeadInsight]) -> List[LeadInsight]:
    """Most urgent first: score, then temperature, then oldest overdue task."""

    def key(i: LeadInsight) -> Tuple[int, int, int]:
        oldest = -len(i.overdue_tasks)
        return (-i.score, _TEMP_ORDER.get(i.temperature, 9), oldest)

    return sorted(insights, key=key)


__all__ = ["WEIGHTS", "Action", "LeadInsight", "build_insight", "rank", "fmt_price"]
