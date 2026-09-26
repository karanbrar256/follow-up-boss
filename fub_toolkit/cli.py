"""
Command-line entry point.

    python -m fub_toolkit daily                 # morning call sheet (mock data)
    python -m fub_toolkit daily --format csv --out today.csv
    python -m fub_toolkit daily --day shift         # shift day targets
    python -m fub_toolkit lead 101              # one lead in detail
    python -m fub_toolkit tasks                 # overdue tasks only
    python -m fub_toolkit criteria              # buyer criteria for every lead
    python -m fub_toolkit daily --source file --file bundle.json
    python -m fub_toolkit daily --source live   # blocked until you opt in
"""

import argparse
import os
import sys
from datetime import datetime
from typing import List, Optional

from .engine import build_insight
from .models import LOCAL_TZ
from .report import (
    build_report,
    render_csv,
    render_json,
    render_lead_card,
    render_markdown,
)
from .sources import (
    JsonFileSource,
    LiveAccessDisabled,
    LiveReadOnlySource,
    MockSource,
    build_leads,
)


def _as_of(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(LOCAL_TZ)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    if len(value) == 10:  # date only -> 8 a.m. local, i.e. "this morning"
        parsed = parsed.replace(hour=8)
    return parsed


def _load(args: argparse.Namespace, as_of: datetime):  # type: ignore[no-untyped-def]
    if args.source == "mock":
        return MockSource(as_of).load()
    if args.source == "file":
        if not args.file:
            raise SystemExit("--file is required with --source file")
        return JsonFileSource(args.file).load()
    return LiveReadOnlySource(max_people=args.max_people).load()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fub_toolkit",
        description="Daily lead follow-up toolkit for Follow Up Boss (prototype).",
    )
    parser.add_argument(
        "--source",
        choices=["mock", "file", "live"],
        default="mock",
        help="Where data comes from (default: mock)",
    )
    parser.add_argument("--file", help="Path to a JSON bundle when --source file")
    parser.add_argument(
        "--as-of",
        help="Pretend it's this date/time (YYYY-MM-DD or ISO). Default: now, Vancouver time",
    )
    parser.add_argument(
        "--agent",
        default=os.getenv("AGENT_NAME", "Karan"),
        help="Your first name for text drafts",
    )
    parser.add_argument(
        "--max-people", type=int, default=1000, help="Live mode: cap on people fetched"
    )
    sub = parser.add_subparsers(dest="command")

    daily = sub.add_parser("daily", help="Morning call sheet")
    daily.add_argument("--format", choices=["md", "csv", "json"], default="md")
    daily.add_argument(
        "--top",
        type=int,
        default=None,
        help="Max leads per Smart List (default: the list's own daily cap)",
    )
    daily.add_argument(
        "--day",
        choices=["office", "shift", "minimum"],
        default=os.getenv("DAY_TYPE", "office"),
        help="Day type: office (40 dials), shift (15 dials + 30 texts), minimum (called in: 15 dials)",
    )
    daily.add_argument("--out", help="Write to this file instead of the screen")

    lead = sub.add_parser("lead", help="Detail card for one lead")
    lead.add_argument("person_id", type=int)

    sub.add_parser("tasks", help="Overdue tasks")
    sub.add_parser("criteria", help="Extracted buyer criteria for every lead")

    args = parser.parse_args(argv)
    command = args.command or "daily"
    as_of = _as_of(args.as_of)

    try:
        bundle = _load(args, as_of)
    except LiveAccessDisabled as exc:
        print(f"Blocked: {exc}", file=sys.stderr)
        return 2

    if command == "daily":
        report = build_report(
            bundle,
            as_of,
            agent=args.agent,
            top=getattr(args, "top", None),
            day=getattr(args, "day", os.getenv("DAY_TYPE", "office")),
        )
        fmt = getattr(args, "format", "md")
        text = {"md": render_markdown, "csv": render_csv, "json": render_json}[fmt](
            report
        )
        out = getattr(args, "out", None)
        if out:
            with open(out, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            print(f"Wrote {fmt} report to {out}")
        else:
            print(text)
        return 0

    leads = build_leads(bundle)
    if command == "lead":
        match = [x for x in leads if x.id == args.person_id]
        if not match:
            print(f"No lead with id {args.person_id}", file=sys.stderr)
            return 1
        print(render_lead_card(build_insight(match[0], as_of, args.agent), as_of))
        return 0

    report = build_report(bundle, as_of, agent=args.agent)
    if command == "tasks":
        if not report.overdue:
            print("No overdue tasks.")
        for o in report.overdue:
            print(
                f"{o.days_overdue:>3}d overdue · {o.task.name} · {o.lead_name} ({o.task.type})"
            )
        return 0

    # criteria
    for i in sorted(report.insights, key=lambda x: x.lead.name):
        c = i.criteria
        missing = ", ".join(c.missing_labels()) or "nothing"
        print(
            f"{i.lead.name} [{i.temperature}]\n  {c.one_line()}\n  missing: {missing}"
        )
        if c.flags:
            print(f"  flags: {', '.join(c.flags)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
