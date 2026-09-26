"""
Daily-operations toolkit for a Follow Up Boss lead workflow (prototype).

Ranks leads by follow-up urgency, flags overdue tasks, summarizes recent
notes, extracts buyer criteria and recommends the next action for each lead.
Runs on mock data by default; live access is read-only and opt-in.
"""

from .criteria import BuyerCriteria, extract_criteria
from .engine import Action, LeadInsight, build_insight, rank
from .report import DailyReport, build_report, render_csv, render_json, render_markdown
from .sources import JsonFileSource, LiveReadOnlySource, MockSource, build_leads

__all__ = [
    "Action",
    "BuyerCriteria",
    "DailyReport",
    "JsonFileSource",
    "LeadInsight",
    "LiveReadOnlySource",
    "MockSource",
    "build_insight",
    "build_leads",
    "build_report",
    "extract_criteria",
    "rank",
    "render_csv",
    "render_json",
    "render_markdown",
]
