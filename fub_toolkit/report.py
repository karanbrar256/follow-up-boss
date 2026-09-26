"""
Morning report, laid out like Karan's day: reply-nows, overdue tasks, then
Smart Lists 1 → 7 (with the daily caps), clean-up, and the scorecard line.
Rendered as Markdown (to read), CSV (to print / dialer) or JSON.
"""

import csv
import re
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from . import playbook as pb
from .engine import LeadInsight, build_insight, rank
from .models import Lead, Task
from .sources import Bundle, build_leads


@dataclass
class OverdueTask:
    task: Task
    lead_name: str
    days_overdue: int


@dataclass
class ListSection:
    smart_list: pb.SmartList
    items: List[LeadInsight]
    held_over: int  # due but beyond today's cap


@dataclass
class DailyReport:
    as_of: datetime
    agent: str
    day_type: pb.DayType
    insights: List[LeadInsight]
    overdue: List[OverdueTask]
    reply_now: List[LeadInsight] = field(default_factory=list)
    sections: List[ListSection] = field(default_factory=list)
    upcoming: List[LeadInsight] = field(default_factory=list)
    cleanup: List[LeadInsight] = field(default_factory=list)

    @property
    def worklist(self) -> List[LeadInsight]:
        """Everything to work today, in order."""
        return self.reply_now + [i for s in self.sections for i in s.items]

    @property
    def call_list(self) -> List[LeadInsight]:
        return [i for i in self.worklist if i.action.channel == "Call"]

    @property
    def value_list(self) -> List[LeadInsight]:
        return [i for i in self.worklist if i.action.channel in {"Text", "Email"}]

    @property
    def not_due(self) -> List[LeadInsight]:
        return [i for i in self.insights if not i.excluded_reason and not i.due]


def find_overdue_tasks(
    tasks: List[Task], leads: List[Lead], today: date
) -> List[OverdueTask]:
    names = {lead.id: lead.name for lead in leads}
    out = [
        OverdueTask(
            t, names.get(t.person_id or -1, "(no contact linked)"), (today - t.due).days
        )
        for t in tasks
        if not t.completed and t.due and t.due < today
    ]
    return sorted(out, key=lambda o: -o.days_overdue)


def build_report(
    bundle: Bundle,
    as_of: datetime,
    agent: str = pb.AGENT,
    top: Optional[int] = None,
    day: str = "office",
) -> DailyReport:
    leads = build_leads(bundle)
    insights = rank([build_insight(lead, as_of, agent) for lead in leads])
    all_tasks = [Task.from_fub(t) for t in bundle.get("tasks", [])]
    day_type = pb.DAY_TYPES[day]
    report = DailyReport(
        as_of=as_of,
        agent=agent,
        day_type=day_type,
        insights=insights,
        overdue=find_overdue_tasks(all_tasks, leads, as_of.date()),
    )
    report.reply_now = [
        i for i in insights if i.active and i.action.code == "reply_now"
    ]
    taken = {i.lead.id for i in report.reply_now}
    lists = [1, 2, 3] if day == "minimum" else list(pb.SMART_LISTS)
    for number in lists:
        sl = pb.SMART_LISTS[number]
        due = [
            i
            for i in insights
            if i.active and i.smart_list == number and i.lead.id not in taken
        ]
        cap = sl.daily_cap if sl.daily_cap is not None else len(due)
        if top is not None:
            cap = min(cap, top)
        report.sections.append(ListSection(sl, due[:cap], max(0, len(due) - cap)))
    report.upcoming = sorted(
        (i for i in insights if i.activity.next_appointment and not i.excluded_reason),
        key=lambda i: i.activity.next_appointment.start,  # type: ignore[union-attr,arg-type,return-value]
    )
    report.cleanup = [i for i in insights if i.excluded_reason]
    return report


def _fmt_date(d: Optional[date], today: date) -> str:
    if d is None:
        return "—"
    delta = (d - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return d.strftime("%a %b %d")


def _lead_block(n: int, i: LeadInsight, today: date, full: bool = True) -> List[str]:
    lead, c, a, act = i.lead, i.criteria, i.activity, i.action
    lines = [
        f"### {n}. {lead.name} — {act.label}",
        f"**{lead.phone or 'no phone'}** · {i.temperature} · {lead.stage} · {i.campaign}",
        "",
        f"- **Why now:** {'; '.join(i.reasons) or act.why}",
    ]
    if act.why and act.why not in i.reasons:
        lines.append(f"- **Context:** {act.why}")
    if i.smart_list != 7 and i.action.code not in {"deal_check_in", "seller_update"}:
        lines.append(f"- **Wants:** {c.one_line()}")
    current = ", ".join(f"currently in {x}" for x in c.current_areas)
    extra = [x for x in (", ".join(c.situation), current, ", ".join(c.motivation)) if x]
    if extra:
        lines.append(f"- **Situation:** {' · '.join(extra)}")
    if c.decision_makers:
        lines.append(f"- **Decision makers:** lead + {', '.join(c.decision_makers)}")
    if full and a.summary_lines:
        lines.append("- **Recent:**")
        lines.extend(f"  - {s}" for s in a.summary_lines[:2])
    for t in i.overdue_tasks:
        lines.append(
            f"- **Overdue task:** {t.name} ({(today - (t.due or today)).days}d)"
        )
    if act.talking_points:
        lines.append("- **Ask / cover:**")
        lines.extend(f"  - {p}" for p in act.talking_points[:3])
    if act.voicemail:
        lines.append(f"- **Voicemail:** “{act.voicemail}”")
    if act.text_draft:
        label = "Text" if act.channel == "Text" else "Text if no answer"
        lines.append(f"- **{label}:** “{act.text_draft}”")
    if act.crm_update:
        lines.append(f"- **FUB:** {act.crm_update}")
    lines.append(f"- **Next follow-up:** {_fmt_date(act.follow_up, today)}")
    lines.append("")
    return lines


def render_markdown(r: DailyReport) -> str:
    today = r.as_of.date()
    d = r.day_type
    calls = len(r.call_list)
    texts = len(r.value_list)
    out = [
        f"# {r.agent}'s Day — {r.as_of.strftime('%A, %B %d, %Y')} · {d.name}",
        "",
        f"**Targets:** {d.dials} dials · {d.conversations}+ conversations · 1 appointment set this week "
        f"· {d.texts} texts · **every conversation gets a dated task**",
        "",
        f"{d.note}",
        "",
        f"On today's sheet: **{calls} calls**, **{texts} texts/emails**, **{len(r.overdue)} overdue tasks**, "
        f"**{len(r.upcoming)} appointments ahead**.",
    ]
    if r.as_of.weekday() >= 5:
        out += [
            "",
            "**Weekend:** open house 2–4 p.m. Invite 20 neighbours 1–2 p.m. Same evening: load sign-ins into FUB and send OH1.",
        ]
    out.append("")

    n = 0
    if r.reply_now:
        out += ["## Start here — they replied", ""]
        for i in r.reply_now:
            n += 1
            out += _lead_block(n, i, today)

    out += ["## Overdue tasks — clear these first", ""]
    if not r.overdue:
        out += ["None.", ""]
    else:
        out += ["| Days overdue | Task | Contact |", "|---:|---|---|"]
        out += [
            f"| {o.days_overdue} | {o.task.name} | {o.lead_name} |" for o in r.overdue
        ]
        out.append("")

    out += ["## Appointments ahead", ""]
    if not r.upcoming:
        out += ["None booked. Aim to set one today.", ""]
    for i in r.upcoming:
        appt = i.activity.next_appointment
        if appt and appt.start:
            local = appt.start.astimezone(r.as_of.tzinfo)
            when = f"{local.strftime('%a %b %d')} {local.hour % 12 or 12}:{local.minute:02d} {'a.m.' if local.hour < 12 else 'p.m.'}"
            out.append(
                f"- {when} — **{appt.title}** with {i.lead.name}{' @ ' + appt.location if appt.location else ''}"
            )
    out.append("")

    for section in r.sections:
        sl = section.smart_list
        out += [f"## List {sl.number} · {sl.name} — {sl.target}", ""]
        if not section.items:
            out += ["Nobody due.", ""]
            continue
        if sl.number in (1, 4):
            by_ad: Dict[str, LeadInsight] = {}
            for i in section.items:
                n += 1
                a = i.activity
                tries = (
                    f"{a.attempts_since_conversation} tries"
                    if a.last_outbound
                    else "never contacted"
                )
                days = (
                    (today - i.lead.created.astimezone(r.as_of.tzinfo).date()).days
                    if i.lead.created
                    else 0
                )
                out.append(
                    f"{n}. **{i.lead.name}** · {i.lead.phone} · {i.campaign} · {days}d old · {tries} — {i.action.label}"
                )
                by_ad.setdefault(f"{i.campaign}|{i.action.label.split(':')[-1]}", i)
            out += ["", "**Scripts for this list** ({name} = their first name):", ""]
            for i in by_ad.values():
                act = i.action

                def generic(msg: str, first: str = i.lead.first_name) -> str:
                    if not first:
                        return msg
                    return re.sub(rf"\b{re.escape(first)}\b", "{name}", msg)

                out.append(f"- *{i.campaign} — {act.label}*")
                if act.voicemail:
                    out.append(f"  - Voicemail: \u201c{generic(act.voicemail)}\u201d")
                if act.text_draft:
                    out.append(f"  - Text: \u201c{generic(act.text_draft)}\u201d")
            out.append("")
        elif sl.channel == "Text":
            for i in section.items:
                n += 1
                out.append(
                    f"{n}. **{i.lead.name}** ({i.lead.phone}) — {i.action.label}"
                )
                if i.action.text_draft:
                    out.append(f"   - “{i.action.text_draft}”")
                if i.action.crm_update:
                    out.append(f"   - FUB: {i.action.crm_update}")
            out.append("")
        else:
            for i in section.items:
                n += 1
                out += _lead_block(n, i, today, full=sl.number in (1, 2, 3))
        if section.held_over:
            out += [
                f"_+{section.held_over} more due in this list. They roll to tomorrow._",
                "",
            ]

    if r.cleanup:
        out += ["## Clean up in FUB", ""]
        out += [f"- **{i.lead.name}** — {i.excluded_reason}" for i in r.cleanup]
        out.append("")

    out += [
        "## Scorecard (log at end of day)",
        "",
        "Dials ___ · Conversations ___ · Appointments set ___ · Sphere touches ___ · Leads without a next task ___",
        "",
        "_Criteria and flags are pulled from notes automatically. Check the note before quoting it back to a client. Replace anything in {braces} before sending a text._",
    ]
    return "\n".join(out) + "\n"


CSV_COLUMNS = [
    "order",
    "smart_list",
    "name",
    "phone",
    "email",
    "temperature",
    "stage",
    "ad",
    "action",
    "why",
    "wants",
    "questions",
    "text",
    "voicemail",
    "overdue_tasks",
    "next_follow_up",
    "fub_person_id",
]


def render_csv(r: DailyReport) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for n, i in enumerate(r.worklist, 1):
        writer.writerow(
            {
                "order": n,
                "smart_list": (
                    "Reply now"
                    if i.action.code == "reply_now"
                    else f"{i.smart_list}. {pb.SMART_LISTS[i.smart_list].name}"
                ),
                "name": i.lead.name,
                "phone": i.lead.phone or "",
                "email": i.lead.email or "",
                "temperature": i.temperature,
                "stage": i.lead.stage,
                "ad": i.campaign,
                "action": i.action.label,
                "why": "; ".join(i.reasons) or i.action.why,
                "wants": i.criteria.one_line(),
                "questions": " | ".join(i.action.talking_points[:5]),
                "text": i.action.text_draft,
                "voicemail": i.action.voicemail,
                "overdue_tasks": " | ".join(t.name for t in i.overdue_tasks),
                "next_follow_up": (
                    i.action.follow_up.isoformat() if i.action.follow_up else ""
                ),
                "fub_person_id": i.lead.id,
            }
        )
    return buf.getvalue()


def insight_to_dict(i: LeadInsight) -> Dict[str, Any]:
    c, a, act = i.criteria, i.activity, i.action
    return {
        "id": i.lead.id,
        "name": i.lead.name,
        "phone": i.lead.phone,
        "stage": i.lead.stage,
        "source": i.lead.source,
        "ad": i.campaign,
        "smart_list": i.smart_list,
        "temperature": i.temperature,
        "score": i.score,
        "reasons": i.reasons,
        "due_today": i.due,
        "excluded_reason": i.excluded_reason or None,
        "criteria": {
            "areas": c.areas,
            "property_types": c.property_types,
            "min_price": c.min_price,
            "max_price": c.max_price,
            "bedrooms": c.bedrooms,
            "acres": c.acres_label or None,
            "land_use": c.land_use,
            "timeline_months": c.timeline_months,
            "timeline": c.timeline_label or None,
            "pre_approved": c.pre_approved,
            "cash_buyer": c.cash_buyer,
            "situation": c.situation,
            "must_haves": c.must_haves,
            "motivation": c.motivation,
            "decision_makers": c.decision_makers,
            "flags": c.flags,
            "missing": c.missing(),
            "evidence": c.evidence,
        },
        "activity": {
            "last_conversation": (
                a.last_conversation.isoformat() if a.last_conversation else None
            ),
            "last_outbound": a.last_outbound.isoformat() if a.last_outbound else None,
            "attempts_since_conversation": a.attempts_since_conversation,
            "unanswered_inbound": a.unanswered_inbound,
            "listings_sent": a.listings_sent,
            "showing_done": a.showing_done,
            "recent": a.summary_lines,
        },
        "overdue_tasks": [
            {"id": t.id, "name": t.name, "due": t.due.isoformat() if t.due else None}
            for t in i.overdue_tasks
        ],
        "next_action": {
            "code": act.code,
            "label": act.label,
            "channel": act.channel,
            "why": act.why,
            "text_draft": act.text_draft,
            "voicemail": act.voicemail,
            "talking_points": act.talking_points,
            "crm_update": act.crm_update,
            "follow_up": act.follow_up.isoformat() if act.follow_up else None,
        },
    }


def render_json(r: DailyReport) -> str:
    payload = {
        "as_of": r.as_of.isoformat(),
        "day_type": r.day_type.name,
        "worklist": [i.lead.id for i in r.worklist],
        "call_list": [i.lead.id for i in r.call_list],
        "value_list": [i.lead.id for i in r.value_list],
        "overdue_tasks": [
            {
                "id": o.task.id,
                "name": o.task.name,
                "contact": o.lead_name,
                "days_overdue": o.days_overdue,
            }
            for o in r.overdue
        ],
        "leads": [insight_to_dict(i) for i in r.insights],
    }
    return json.dumps(payload, indent=2)


def render_lead_card(i: LeadInsight, as_of: datetime) -> str:
    today = as_of.date()
    lines = _lead_block(1, i, today)
    lines[0] = f"# {i.lead.name} — {i.action.label}"
    c = i.criteria
    lines.insert(2, f"Smart List {i.smart_list}: {pb.SMART_LISTS[i.smart_list].name}")
    if c.evidence:
        lines += ["## Where the criteria came from", ""]
        lines += [f"- **{k}:** {v}" for k, v in c.evidence.items()]
        lines.append("")
    if c.missing():
        lines += (
            ["## Still unknown", ""] + [f"- {m}" for m in c.missing_labels()] + [""]
        )
    if c.flags:
        lines += ["## Flags", ""] + [f"- {f}" for f in c.flags] + [""]
    if i.excluded_reason:
        lines += [f"**Not on today's lists:** {i.excluded_reason}", ""]
    return "\n".join(lines)


__all__ = [
    "DailyReport",
    "build_report",
    "render_csv",
    "render_json",
    "render_markdown",
    "render_lead_card",
]
