"""
Morning report: build it once, render it as Markdown, CSV or JSON.
"""

import csv
import io
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .engine import LeadInsight, build_insight, rank
from .models import Lead, Task
from .sources import Bundle, build_leads


@dataclass
class OverdueTask:
    task: Task
    lead_name: str
    days_overdue: int


@dataclass
class DailyReport:
    as_of: datetime
    agent: str
    insights: List[LeadInsight]
    overdue: List[OverdueTask]
    call_list: List[LeadInsight] = field(default_factory=list)
    value_list: List[LeadInsight] = field(default_factory=list)
    upcoming: List[LeadInsight] = field(default_factory=list)
    cleanup: List[LeadInsight] = field(default_factory=list)
    not_due: List[LeadInsight] = field(default_factory=list)


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
    bundle: Bundle, as_of: datetime, agent: str = "Karan", top: int = 20
) -> DailyReport:
    leads = build_leads(bundle)
    insights = rank([build_insight(lead, as_of, agent) for lead in leads])
    all_tasks = [Task.from_fub(t) for t in bundle.get("tasks", [])]
    report = DailyReport(
        as_of=as_of,
        agent=agent,
        insights=insights,
        overdue=find_overdue_tasks(all_tasks, leads, as_of.date()),
    )
    report.call_list = [i for i in insights if i.on_call_list][:top]
    report.value_list = [i for i in insights if i.on_value_list]
    report.upcoming = [
        i for i in insights if i.activity.next_appointment and not i.excluded_reason
    ]
    report.cleanup = [i for i in insights if i.excluded_reason]
    report.not_due = [i for i in insights if not i.excluded_reason and not i.due]
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


def _lead_block(n: int, i: LeadInsight, today: date) -> List[str]:
    lead, c, a, act = i.lead, i.criteria, i.activity, i.action
    lines = [
        f"### {n}. {lead.name} — {act.label}",
        f"**{lead.phone or 'no phone'}** · {i.temperature} · score {i.score} · {lead.stage} · {lead.source}",
        "",
        f"- **Why now:** {'; '.join(i.reasons) or act.why}",
    ]
    if act.why and act.why not in i.reasons:
        lines.append(f"- **Context:** {act.why}")
    if i.temperature != "Sphere":
        lines.append(f"- **Wants:** {c.one_line()}")
    current = ", ".join(f"currently in {a_}" for a_ in c.current_areas)
    extra = [x for x in (", ".join(c.situation), current, ", ".join(c.motivation)) if x]
    if extra:
        lines.append(f"- **Situation:** {' · '.join(extra)}")
    if c.decision_makers:
        lines.append(f"- **Decision makers:** lead + {', '.join(c.decision_makers)}")
    if a.summary_lines:
        lines.append("- **Recent:**")
        lines.extend(f"  - {s}" for s in a.summary_lines[:3])
    for t in i.overdue_tasks:
        lines.append(f"- **Overdue task:** {t.name} ({(today - t.due).days}d)")  # type: ignore[operator]
    if act.talking_points:
        lines.append("- **Ask / cover:**")
        lines.extend(f"  - {p}" for p in act.talking_points)
    if act.text_draft:
        lines.append(f"- **Text if no answer:** “{act.text_draft}”")
    if act.crm_update:
        lines.append(f"- **FUB:** {act.crm_update}")
    lines.append(f"- **Next follow-up:** {_fmt_date(act.follow_up, today)}")
    lines.append("")
    return lines


def render_markdown(r: DailyReport) -> str:
    today = r.as_of.date()
    n_calls = len(r.call_list)
    convo_target = math.ceil(n_calls * 0.4)
    hot = sum(1 for i in r.insights if i.temperature == "Hot" and not i.excluded_reason)
    out = [
        f"# Daily Call Sheet — {r.as_of.strftime('%A, %B %d, %Y')}",
        "",
        f"Leads reviewed: **{len(r.insights)}** · Hot: **{hot}** · Calls today: **{n_calls}** · "
        f"Texts/emails: **{len(r.value_list)}** · Overdue tasks: **{len(r.overdue)}** · Appointments ahead: **{len(r.upcoming)}**",
        "",
        f"**Targets:** work all {n_calls} calls before 11 a.m. · {convo_target}+ conversations · 1+ appointment set · "
        f"every lead touched gets a follow-up date in FUB.",
        "",
        "## 1. Call list (in this order)",
        "",
    ]
    if not r.call_list:
        out += [
            "Nothing due. Use the time to prospect your sphere or past clients.",
            "",
        ]
    for n, i in enumerate(r.call_list, 1):
        out += _lead_block(n, i, today)

    out += ["## 2. Texts & emails to send", ""]
    if not r.value_list:
        out += ["None due today.", ""]
    for i in r.value_list:
        out += [
            f"- **{i.lead.name}** ({i.lead.phone}) — {i.action.label}. {i.action.why}",
            f"  - “{i.action.text_draft}”",
        ]
        for tp in i.action.talking_points:
            out.append(f"  - Note: {tp}")
        if i.action.crm_update:
            out.append(f"  - FUB: {i.action.crm_update}")
        out.append(f"  - Next follow-up: {_fmt_date(i.action.follow_up, today)}")
    out.append("")

    out += ["## 3. Overdue tasks", ""]
    if not r.overdue:
        out += ["None.", ""]
    else:
        out += ["| Days overdue | Task | Contact | Type |", "|---:|---|---|---|"]
        out += [
            f"| {o.days_overdue} | {o.task.name} | {o.lead_name} | {o.task.type} |"
            for o in r.overdue
        ]
        out.append("")

    out += ["## 4. Upcoming appointments", ""]
    if not r.upcoming:
        out += ["None booked. Aim to set at least one today.", ""]
    for i in r.upcoming:
        appt = i.activity.next_appointment
        if appt and appt.start:
            local = appt.start.astimezone(r.as_of.tzinfo)
            when = f"{local.strftime('%a %b %d')} {local.hour % 12 or 12}:{local.minute:02d} {'a.m.' if local.hour < 12 else 'p.m.'}"
            out.append(
                f"- {when} — **{appt.title}** with {i.lead.name}{' @ ' + appt.location if appt.location else ''}"
            )
    out.append("")

    out += ["## 5. Clean up in Follow Up Boss", ""]
    if not r.cleanup:
        out += ["Nothing to clean up.", ""]
    for i in r.cleanup:
        out.append(f"- **{i.lead.name}** — {i.excluded_reason}")
    out.append("")

    if r.not_due:
        out += ["## 6. Not due today", ""]
        for i in r.not_due:
            out.append(
                f"- {i.lead.name} ({i.temperature}) — next: {i.action.label.lower()}, {_fmt_date(i.action.follow_up, today)}"
            )
        out.append("")

    out.append(
        "_Prototype output from mock data. Criteria and flags are extracted automatically — check the notes before quoting them back to a client._"
    )
    return "\n".join(out) + "\n"


CSV_COLUMNS = [
    "rank",
    "name",
    "phone",
    "email",
    "temperature",
    "score",
    "stage",
    "source",
    "action",
    "why",
    "wants",
    "missing_questions",
    "text_draft",
    "overdue_tasks",
    "next_follow_up",
    "fub_person_id",
]


def render_csv(r: DailyReport) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for n, i in enumerate(r.call_list + r.value_list, 1):
        writer.writerow(
            {
                "rank": n,
                "name": i.lead.name,
                "phone": i.lead.phone or "",
                "email": i.lead.email or "",
                "temperature": i.temperature,
                "score": i.score,
                "stage": i.lead.stage,
                "source": i.lead.source,
                "action": i.action.label,
                "why": "; ".join(i.reasons) or i.action.why,
                "wants": i.criteria.one_line(),
                "missing_questions": " | ".join(i.criteria.missing_questions()),
                "text_draft": i.action.text_draft,
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
            "talking_points": act.talking_points,
            "crm_update": act.crm_update,
            "follow_up": act.follow_up.isoformat() if act.follow_up else None,
        },
    }


def render_json(r: DailyReport) -> str:
    payload = {
        "as_of": r.as_of.isoformat(),
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
        lines += [f"**Excluded from call list:** {i.excluded_reason}", ""]
    return "\n".join(lines)
