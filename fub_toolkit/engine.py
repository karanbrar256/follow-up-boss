"""
Sorts every lead into Karan's 7 Smart Lists, decides who is due today,
ranks them within each list and recommends the next action.

Business rules (stages, cadences, Plan A, texts) come from ``playbook.py``.
Every point in a score comes with a plain-English reason; weights are in
``WEIGHTS``.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from . import playbook as pb
from .activity import ActivitySnapshot, analyze_activity
from .criteria import BuyerCriteria, extract_criteria, fmt_price
from .models import Lead, Task

WEIGHTS: Dict[str, int] = {
    "unanswered_inbound": 100,
    "new_lead_uncontacted": 90,
    "new_lead_under_24h_bonus": 10,
    "old_lead_uncontacted": 40,
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
}

STOP_FLAGS = {"Do not contact", "Bad number", "Already bought"}
HOT_LISTS = {2, 3}
PLAN_A_STAGES = {"lead", "attempted contact"}


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
    voicemail: str = ""


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
    smart_list: int = 0
    campaign: str = ""
    excluded_reason: str = ""

    @property
    def active(self) -> bool:
        return not self.excluded_reason and self.due

    @property
    def on_call_list(self) -> bool:
        return self.active and self.action.channel == "Call"

    @property
    def on_value_list(self) -> bool:
        return self.active and self.action.channel in {"Text", "Email"}


def search_phrase(c: BuyerCriteria) -> str:
    kind = c.property_types[0].split(" / ")[0].lower() if c.property_types else "homes"
    kind = {
        "townhouse": "townhouses",
        "condo": "condos",
        "duplex": "duplexes",
        "detached": "detached homes",
        "acreage": "acreages",
        "land": "land",
        "industrial": "industrial properties",
        "commercial": "commercial properties",
    }.get(kind, kind)
    acres = f" ({c.acres_label})" if c.acres_label else ""
    where = f" in {c.areas[0]}" if c.areas else ""
    budget = f" {c.budget_label}" if c.budget_label else ""
    return (
        f"{kind}{acres}{where}{budget}".strip() if (c.property_types or c.areas) else ""
    )


def _days_in(lead: Lead, as_of: datetime) -> int:
    if lead.created is None:
        return 999
    return max(0, (as_of.date() - lead.created.astimezone(as_of.tzinfo).date()).days)


def _smart_list(lead: Lead, as_of: datetime) -> Tuple[int, int]:
    """(smart list number, cadence days) for a lead's stage."""
    stage = lead.stage.lower()
    number, cadence = pb.STAGES.get(stage, (5, 14))
    if number == 1 and _days_in(lead, as_of) > pb.NEW_LEAD_DAYS:
        number = 4
    return number, cadence


def _temperature(
    lead: Lead, c: BuyerCriteria, a: ActivitySnapshot, smart_list: int, as_of: datetime
) -> str:
    if smart_list == 7:
        return "Sphere"
    if smart_list in HOT_LISTS or a.next_appointment is not None:
        return "Hot"
    if c.timeline_months is not None and c.timeline_months <= 3:
        return "Hot"
    if a.unanswered_inbound and a.days_since(a.last_inbound, as_of) in (0, 1):
        return "Hot"
    if smart_list == 6 or "Just browsing" in c.flags:
        return "Nurture"
    if c.timeline_months is not None and c.timeline_months > 12:
        return "Nurture"
    return "Warm"


def _weekday_options(as_of: datetime) -> str:
    first = as_of + timedelta(days=1)
    second = as_of + timedelta(days=2)
    return f"{first.strftime('%A')} or {second.strftime('%A')}"


def _clock(dt: datetime) -> str:
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'a.m.' if dt.hour < 12 else 'p.m.'}"


def _recommend(
    lead: Lead,
    c: BuyerCriteria,
    a: ActivitySnapshot,
    smart_list: int,
    campaign: pb.Campaign,
    as_of: datetime,
) -> Action:
    today = as_of.date()
    stage = lead.stage.lower()
    days_in = _days_in(lead, as_of)
    values = {
        "name": lead.first_name,
        "area": c.areas[0] if c.areas else "",
        "timeline": c.timeline_label,
        "topic": search_phrase(c) or "homes in the area",
    }

    def text(key: str) -> str:
        return pb.fill(campaign.texts[key], **values)

    voicemail = pb.fill(campaign.voicemail, **values)
    questions = [q for q in c.missing_questions()] or campaign.qualifiers[:2]
    seller = (
        ["Seller script: " + s for s in pb.SELLER_SCRIPT]
        if lead.has_tag("Seller-Potential")
        else []
    )

    if a.unanswered_inbound:
        hours = (
            int((as_of - a.last_inbound).total_seconds() // 3600)
            if a.last_inbound
            else 0
        )
        said = (
            f"“{a.last_inbound_text.strip()[:140]}”"
            if a.last_inbound_text
            else "(incoming call)"
        )
        return Action(
            code="reply_now",
            label="Reply now — they reached out",
            channel="Call",
            why=f"Their last {a.last_inbound_channel or 'message'} ({hours}h ago) hasn't been answered: {said}",
            text_draft=f"Hi {lead.first_name}, thanks for getting back to me — happy to help with that. Do you have 5 minutes for a quick call today?",
            talking_points=["Answer their question first, then book the next step"]
            + questions,
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
        points = ["Confirm everyone involved in the decision is coming"]
        if not c.cash_buyer and c.pre_approved is not True:
            points.append("Check where they are with a lender")
        return Action(
            code="confirm_appointment",
            label="Confirm appointment (text B)",
            channel="Text",
            why=f"{appt.title} is booked for {day} at {_clock(local)}",
            text_draft=pb.fill(
                campaign.texts["B"], day=day, time=_clock(local), **values
            ),
            talking_points=points,
            follow_up=local.date(),
        )

    never_spoke = a.conversations == 0
    if never_spoke and (stage in PLAN_A_STAGES or stage not in pb.STAGES):
        fresh = days_in <= pb.NEW_LEAD_DAYS or a.last_outbound is not None
        if days_in <= 14 and fresh:
            _, key, step = pb.plan_a_step(days_in)
            channel = "Email" if key == "email" else "Call"
            return Action(
                code="plan_a",
                label=f"Plan A · day {days_in}: {step}",
                channel=channel,
                why=f"{campaign.name} lead, no conversation yet ({a.attempts_since_conversation} attempts).",
                text_draft=text(key) if key in campaign.texts else "",
                talking_points=(
                    ["Email 3 hand-picked listings that match the ad"]
                    if key == "email"
                    else campaign.qualifiers
                )
                + seller,
                voicemail=voicemail if channel == "Call" else "",
                crm_update=(
                    "Stage: Attempted Contact"
                    if stage == "lead" and a.attempts_since_conversation
                    else ""
                ),
                follow_up=today + timedelta(days=1),
            )
        if a.last_outbound is None:
            return Action(
                code="first_contact",
                label="Never contacted — call, then text 1",
                channel="Call",
                why=f"Came in {days_in} days ago from the {campaign.name} ad and has never been called or texted.",
                text_draft=text("1"),
                talking_points=campaign.qualifiers + seller,
                voicemail=voicemail,
                crm_update="Stage: Attempted Contact if no answer",
                follow_up=today + timedelta(days=pb.UNREACHED_GAP_DAYS),
            )
        if a.attempts_since_conversation < 5:
            return Action(
                code="unreached_retry",
                label="Unreached — try again",
                channel="Call",
                why=f"{a.attempts_since_conversation} attempts, never reached.",
                text_draft=text("3"),
                talking_points=campaign.qualifiers + seller,
                voicemail=voicemail,
                follow_up=today + timedelta(days=pb.UNREACHED_GAP_DAYS),
            )
        return Action(
            code="close_loop",
            label="Close the loop (text 5), then move to Nurture",
            channel="Text",
            why=f"{a.attempts_since_conversation} attempts over {days_in} days, never reached.",
            text_draft=text("5"),
            crm_update="No reply in 3 days → Stage: Nurture (Plan B starts automatically)",
            follow_up=today + timedelta(days=3),
        )

    stage_fix = ""
    if stage in PLAN_A_STAGES and not never_spoke:
        stage_fix = "You've talked — update stage: Hot Prospect (0–3 mo), Spoke with Customer (3–12 mo) or Nurture (12+ mo)"

    if smart_list == 7:
        return Action(
            code="referral_touch",
            label="Sphere / past client touch",
            channel="Call",
            why="Monthly touch. Your sphere converts far better than cold leads.",
            text_draft=f"Hi {lead.first_name}, {pb.AGENT} here — just checking in. How's everything with you? If anyone you know is thinking of buying or selling, I'd be glad to help.",
            talking_points=[
                "Personal first, real estate second",
                "Offer a free equity check if they own",
            ],
            follow_up=today + timedelta(days=30),
        )

    if smart_list == 6:
        return Action(
            code="nurture_value",
            label="Nurture text (N)",
            channel="Text",
            why="Long-term lead on Plan B. Stay useful without pushing.",
            text_draft=text("N"),
            talking_points=[
                "If they reply with a change in timing, move them to Hot Prospect or Spoke with Customer"
            ],
            follow_up=today + timedelta(days=45),
        )

    if stage == "under contract" or stage == "pending":
        return Action(
            code="deal_check_in",
            label="Deal check-in",
            channel="Call",
            why="Under contract. Keep subjects, deposit and dates on track.",
            talking_points=[
                "Subject removal date and status (financing, inspection, strata docs)",
                "Deposit received?",
                "Lawyer/notary chosen?",
            ],
            follow_up=today + timedelta(days=3),
        )

    if stage == "active listing":
        return Action(
            code="seller_update",
            label="Seller update",
            channel="Call",
            why="Your listing is live. Sellers who hear from you stay happy.",
            talking_points=[
                "Showings and feedback this week",
                "New competition and recent sales nearby",
                "Price or marketing adjustments if needed",
            ],
            follow_up=today + timedelta(days=3),
        )

    looking = search_phrase(c) or campaign.name
    points_fix = [stage_fix] if stage_fix else []

    if not c.is_qualified:
        return Action(
            code="qualify",
            label="Fill in the gaps",
            channel="Call",
            why="Talked before, but still missing: "
            + ", ".join(c.missing_labels()[:4])
            + ".",
            text_draft=f"Hi {lead.first_name}, {pb.AGENT} here. So I only send you places that actually fit, can we take 5 minutes today to go over what you're looking for?",
            talking_points=questions + seller + points_fix,
            crm_update=stage_fix,
            follow_up=today + timedelta(days=2),
        )

    if smart_list == 5:
        return Action(
            code="prospect_check_in",
            label="Prospect check-in (new listings + timing)",
            channel="Call",
            why="3–12 month buyer. Every 2 weeks: something new to look at, and check if timing changed.",
            text_draft=f"Hi {lead.first_name}, {pb.AGENT} here. A few new {looking} came up since we talked. Want me to send them over? Anything changed on your timing?",
            talking_points=[
                "Has the timeline moved up? If 0–3 months → Hot Prospect",
                "Is their MLS saved search still right?",
            ]
            + seller,
            crm_update=stage_fix,
            follow_up=today + timedelta(days=14),
        )

    financing_needed = (
        c.pre_approved is not True
        and not c.cash_buyer
        and (c.timeline_months or 12) <= 6
    )
    if financing_needed:
        return Action(
            code="broker_intro",
            label="Offer mortgage broker intro",
            channel="Call",
            why="Ready to look soon but no confirmed financing.",
            text_draft=f"Hi {lead.first_name}, before we start viewing it's worth getting pre-approved so you know your exact number and can move quickly. I work with a great mortgage broker — want an intro?",
            talking_points=(
                [
                    "Acreage and land financing can differ from a regular house — broker should confirm"
                ]
                if c.is_land
                else []
            )
            + ["Book the showing once pre-approval is under way"]
            + points_fix,
            crm_update=stage_fix,
            follow_up=today + timedelta(days=3),
        )

    if not a.listings_sent:
        return Action(
            code="send_listings",
            label="Set up MLS saved search + send 3 listings",
            channel="Text",
            why="Criteria are clear but no listings have gone out yet.",
            text_draft=f"Hi {lead.first_name}, I set up a search for {looking}. Here are 3 that stand out — let me know which ones you'd like to see in person.",
            talking_points=["Hand-pick 3; don't just forward the alert"] + points_fix,
            crm_update=stage_fix or "Tag 'Listing Alert' once the saved search is live",
            follow_up=today + timedelta(days=2),
        )

    if a.showing_done:
        return Action(
            code="showing_follow_up",
            label="Showing debrief + next step",
            channel="Call",
            why="They've seen properties with you. Lock in the next step while it's fresh.",
            text_draft=f"Hi {lead.first_name}, what did you think after seeing those? I have a couple more that fit what you liked — want to see them {_weekday_options(as_of)}?",
            talking_points=[
                "What did they like and dislike?",
                "Adjust the search",
                "Book the next showing or a buyer consultation",
            ]
            + points_fix,
            crm_update=stage_fix,
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
        label="Book a showing (two-choice close)",
        channel="Call",
        why="Criteria clear and listings sent, but nothing booked."
        + (f" Recently viewed {event.address}." if event and viewed else ""),
        text_draft=(
            f"Hi {lead.first_name}, {viewed}Want to go see it in person? I've got Thursday after 4 or Saturday morning."
            if viewed
            else f"Hi {lead.first_name}, the easiest next step is to see a couple in person. I've got Thursday after 4 or Saturday morning — which works better?"
        ),
        talking_points=["Offer two specific times", "Confirm who needs to be there"]
        + points_fix,
        crm_update=stage_fix
        or "Booked → Stage: Appointment Set + calendar event + text B",
        follow_up=today + timedelta(days=2),
    )


def build_insight(lead: Lead, as_of: datetime, agent: str = pb.AGENT) -> LeadInsight:
    c = extract_criteria(lead, as_of)
    if c.timeline_months is None and lead.has_tag("0-3mo"):
        c.timeline_months, c.timeline_label = 3, "0–3 months (tag)"
    a = analyze_activity(lead, as_of)
    today = as_of.date()
    stage = lead.stage.lower()
    smart_list, cadence = _smart_list(lead, as_of)
    campaign = pb.campaign_for(lead.tags, lead.source)
    temp = _temperature(lead, c, a, smart_list, as_of)

    open_tasks = [t for t in lead.tasks if not t.completed and t.due]
    overdue = sorted(
        (t for t in open_tasks if t.due and t.due < today), key=lambda t: t.due or today
    )
    due_today = [t for t in open_tasks if t.due == today]

    excluded = ""
    if stage in pb.EXCLUDED_STAGES:
        excluded = f"Stage is {lead.stage}"
    elif lead.has_tag(*pb.STOP_TAGS):
        excluded = "Tagged " + ", ".join(t for t in lead.tags if t in pb.STOP_TAGS)
    else:
        stop = [f for f in c.flags if f in STOP_FLAGS]
        if stop:
            excluded = f"Notes say: {', '.join(stop)} — move to Trash"
        elif "Working with another agent" in c.flags and not lead.has_tag(
            *pb.AGENT_TAGS
        ):
            excluded = "Notes say they have a Realtor — signed: Trash; just chatting: tag Has-Agent + Nurture"

    score = 0
    reasons: List[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    if a.unanswered_inbound:
        add(WEIGHTS["unanswered_inbound"], "They replied and haven't heard back")
    if not a.ever_contacted:
        age_h = (as_of - lead.created).total_seconds() / 3600 if lead.created else 9999
        if age_h <= 24 * pb.NEW_LEAD_DAYS:
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
        worst = (today - (overdue[0].due or today)).days
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

    # When is the next touch due?
    touch_due = False
    if smart_list == 1:
        touches_today = sum(
            1 for t in a.outbound_times if t.astimezone(as_of.tzinfo).date() == today
        )
        touch_due = touches_today < 2 and a.conversations == 0
        if touch_due and a.ever_contacted:
            reasons.append(
                f"Plan A day {_days_in(lead, as_of)}: {a.attempts_since_conversation} tries so far, not reached yet"
            )
    elif smart_list == 4:
        touch_due = (
            a.last_outbound is None
            or (a.days_since(a.last_outbound, as_of) or 0) >= pb.UNREACHED_GAP_DAYS
        )
    else:
        last = max(
            (t for t in (a.last_outbound, a.last_conversation) if t is not None),
            default=None,
        )
        if last is None:
            touch_due = True
        else:
            next_touch = (
                (last + timedelta(days=cadence)).astimezone(as_of.tzinfo).date()
            )
            touch_due = next_touch <= today
            if touch_due:
                since = a.days_since(last, as_of)
                days_over = (today - next_touch).days
                add(
                    WEIGHTS["follow_up_due"]
                    + min(
                        WEIGHTS["follow_up_overdue_cap"],
                        WEIGHTS["follow_up_overdue_per_day"] * days_over,
                    ),
                    f"Follow-up due ({since}d since last touch; every {cadence}d for {lead.stage})",
                )
    if smart_list == 4 and touch_due and a.last_outbound is not None:
        reasons.append(f"Last try {a.days_since(a.last_outbound, as_of)}d ago")

    if a.recent_property_events:
        newest = a.recent_property_events[0]
        days = a.days_since(newest.created, as_of) or 0
        add(
            WEIGHTS["property_activity_3d" if days <= 3 else "property_activity_7d"],
            f"Recent activity: {newest.type.lower()} {newest.address}".strip(),
        )
    if c.timeline_months is not None and c.timeline_months <= 3:
        add(WEIGHTS["timeline_3m"], f"Timeline: {c.timeline_label}")
    elif c.timeline_months is not None and c.timeline_months <= 6:
        add(WEIGHTS["timeline_6m"], f"Timeline: {c.timeline_label}")
    if c.pre_approved or c.cash_buyer:
        add(WEIGHTS["financing_ready"], "Financing ready (" + c.financing_label + ")")
    if "Just browsing" in c.flags or "Not interested" in c.flags:
        add(WEIGHTS["low_intent_penalty"], "Low intent mentioned")

    action = _recommend(lead, c, a, smart_list, campaign, as_of)
    due = bool(
        a.unanswered_inbound
        or overdue
        or due_today
        or touch_due
        or action.code == "confirm_appointment"
    )
    if excluded:
        score = 0
        action = Action(
            code="update_crm", label="Update stage/tags", channel="CRM", why=excluded
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
        smart_list=smart_list,
        campaign=campaign.name,
        excluded_reason=excluded,
    )


def rank(insights: List[LeadInsight]) -> List[LeadInsight]:
    """Smart List order first (1 → 7), then most urgent within each list."""

    def key(i: LeadInsight) -> Tuple[int, int, float]:
        # Unreached: newest leads first (they're likelier to answer).
        created = -(i.lead.created.timestamp() if i.lead.created else 0)
        tiebreak = created if i.smart_list == 4 else -len(i.overdue_tasks)
        return (-i.score, i.smart_list, tiebreak)

    ordered = sorted(insights, key=key)
    return sorted(
        ordered,
        key=lambda i: (
            bool(i.excluded_reason),
            i.smart_list if not i.activity.unanswered_inbound else 0,
        ),
    )


__all__ = [
    "WEIGHTS",
    "Action",
    "LeadInsight",
    "build_insight",
    "rank",
    "fmt_price",
    "search_phrase",
]
