"""
Tests for the daily-operations toolkit (fub_toolkit).

All tests use fictional mock data or tiny inline fixtures. None touch the
network or a real Follow Up Boss account.
"""

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from fub_toolkit import playbook as pb
from fub_toolkit.cli import main
from fub_toolkit.daytype import day_type_for
from fub_toolkit.criteria import (
    extract_criteria,
    fmt_price,
    normalize_form,
    parse_budget,
    parse_financing,
    parse_timeline,
)
from fub_toolkit.engine import WEIGHTS, build_insight, rank
from fub_toolkit.mock_data import build_mock_bundle
from fub_toolkit.models import (
    LOCAL_TZ,
    Interaction,
    Lead,
    Note,
    Task,
    parse_date,
    parse_dt,
)
from fub_toolkit.report import (
    build_report,
    render_csv,
    render_json,
    render_lead_card,
    render_markdown,
)
from fub_toolkit.sources import (
    JsonFileSource,
    LiveAccessDisabled,
    LiveReadOnlySource,
    ReadOnlyViolation,
    build_leads,
    make_read_only_client,
)

AS_OF = datetime(2026, 9, 26, 8, 0, tzinfo=LOCAL_TZ)


@pytest.fixture(scope="module")
def bundle() -> Dict[str, List[Dict[str, Any]]]:
    return build_mock_bundle(AS_OF)


@pytest.fixture(scope="module")
def report(bundle):  # type: ignore[no-untyped-def]
    return build_report(bundle, AS_OF, agent="Karan")


def by_name(report, name):  # type: ignore[no-untyped-def]
    return next(i for i in report.insights if i.lead.name == name)


def make_lead(**kw: Any) -> Lead:
    raw = {
        "id": 1,
        "firstName": "Test",
        "lastName": "Lead",
        "stage": "Lead",
        "source": "Facebook - Test",
        "created": (AS_OF - timedelta(days=10)).isoformat(),
        "phones": [{"value": "604-555-0000"}],
    }
    raw.update(kw)
    return Lead.from_fub(raw)


def note(text: str, days_ago: float = 1) -> Note:
    return Note(
        id=1,
        person_id=1,
        subject="",
        body=text,
        created=AS_OF - timedelta(days=days_ago),
    )


# ---------------------------------------------------------------- parsing


class TestParsing:
    def test_parse_dt_handles_z_and_naive(self) -> None:
        assert parse_dt("2026-09-01T10:00:00Z") == datetime(
            2026, 9, 1, 10, tzinfo=timezone.utc
        )
        assert parse_dt("2026-09-01 10:00:00").tzinfo is not None
        assert parse_dt("") is None and parse_dt("garbage") is None

    def test_parse_date(self) -> None:
        assert str(parse_date("2026-09-20")) == "2026-09-20"
        assert parse_date(None) is None

    def test_task_is_completed_accepts_int_bool_and_string(self) -> None:
        assert Task.from_fub({"id": 1, "isCompleted": 1}).completed
        assert Task.from_fub({"id": 1, "isCompleted": "true"}).completed
        assert not Task.from_fub({"id": 1, "isCompleted": 0}).completed

    def test_primary_phone_preferred(self) -> None:
        lead = make_lead(phones=[{"value": "111"}, {"value": "222", "isPrimary": 1}])
        assert lead.phone == "222"

    def test_call_conversation_detection(self) -> None:
        base = {"personId": 1, "created": AS_OF.isoformat(), "isIncoming": 0}
        assert Interaction.from_call(dict(base, outcome="Interested")).is_conversation
        assert (
            Interaction.from_call(
                dict(base, outcome="Left Message", duration=30)
            ).is_conversation
            is False
        )
        assert Interaction.from_call(
            dict(base, outcome="", duration=120)
        ).is_conversation
        assert Interaction.from_text(
            dict(base, isIncoming=1, message="hi")
        ).is_conversation


# --------------------------------------------------------------- criteria


class TestCriteria:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("budget up to $950k", (None, 950_000)),
            ("between 700k and 800k", (700_000, 800_000)),
            ("$650k-$750k", (650_000, 750_000)),
            ("$700-800k", (700_000, 800_000)),
            ("approved for 1.2M", (None, 1_200_000)),
            ("Budget: 850,000", (None, 850_000)),
            ("under 2.2 million", (None, 2_200_000)),
            ("3-6 months", (None, None)),  # regression: months are not millions
            ("0-3 months, 3 bed 2 bath", (None, None)),
            ("call 604-555-0101", (None, None)),
        ],
    )
    def test_parse_budget(self, text: str, expected: Any) -> None:
        assert parse_budget(text) == expected

    @pytest.mark.parametrize(
        "text,months",
        [
            ("ASAP", 1),
            ("0-3 months", 3),
            ("3-6 months", 6),
            ("12+ months", 12),
            ("in 4 months", 4),
            ("next year", 12),
            ("just browsing", 12),
            ("nothing here", None),
        ],
    )
    def test_parse_timeline(self, text: str, months: Any) -> None:
        assert parse_timeline(text, AS_OF)[0] == months

    def test_season_timeline_is_relative_to_today(self) -> None:
        months, label = parse_timeline("hoping to buy this spring", AS_OF)
        assert label == "Spring" and months == 7  # Sep -> Apr

    def test_financing(self) -> None:
        assert parse_financing("we are pre-approved with RBC") == (True, False)
        assert parse_financing("Not pre-approved yet") == (False, False)
        assert parse_financing("haven't talked to a broker") == (False, False)
        assert parse_financing("paying cash") == (None, True)

    def test_form_question_is_not_the_answer(self) -> None:
        """Regression: 'Are you pre-approved? A: No' used to read as pre-approved."""
        text = normalize_form("Q: Are you pre-approved? A: No")
        assert parse_financing(text) == (False, False)
        text = normalize_form("Q: Are you pre-approved? A: Yes")
        assert parse_financing(text) == (True, False)

    def test_extract_full_profile_with_evidence(self) -> None:
        lead = make_lead()
        lead.notes.append(
            note(
                "Spoke with them. Renting in Burnaby. Want a 3 bed townhouse in Langley or Willoughby, "
                "up to $950k, pre-approved, 2-3 months. Wife wants a double garage and a yard."
            )
        )
        c = extract_criteria(lead, AS_OF)
        assert c.areas == ["Langley", "Willoughby"]
        assert c.current_areas == [
            "Burnaby"
        ]  # where they live, not where they want to buy
        assert c.property_types == ["Townhouse"]
        assert c.bedrooms == 3 and c.max_price == 950_000
        assert c.timeline_months == 3 and c.pre_approved is True
        assert "Renting" in c.situation and "Wife" in c.decision_makers
        assert "Double garage" in c.must_haves and "Garage" not in c.must_haves
        assert c.is_qualified
        assert "areas" in c.evidence and "note" in c.evidence["areas"]

    def test_newer_information_overrides_older(self) -> None:
        lead = make_lead(background="budget up to $700k")
        lead.notes.append(
            note("Budget is now up to $800k after talking to the broker", days_ago=1)
        )
        assert extract_criteria(lead, AS_OF).max_price == 800_000

    def test_north_vancouver_not_double_counted(self) -> None:
        lead = make_lead(background="Looking in North Vancouver")
        assert extract_criteria(lead, AS_OF).areas == ["North Vancouver"]

    def test_negated_flag_is_ignored(self) -> None:
        lead = make_lead()
        lead.notes.append(note("Asked — they are not working with another agent."))
        assert "Working with another agent" not in extract_criteria(lead, AS_OF).flags

    def test_missing_questions_follow_priority(self) -> None:
        lead = make_lead(background="townhouse in Surrey")
        c = extract_criteria(lead, AS_OF)
        assert c.missing()[:2] == ["budget", "timeline"]
        assert len(c.missing_questions()) == 3

    def test_fmt_price(self) -> None:
        assert fmt_price(950_000) == "$950k"
        assert fmt_price(1_250_000) == "$1.25M"
        assert fmt_price(2_000_000) == "$2M"


# --------------------------------------------------------------- playbook & engine


class TestPlaybook:
    def test_campaign_from_facebook_tags(self) -> None:
        assert (
            pb.campaign_for(["2.5M Langley Acreages-copy"], "Facebook").key == "acreage"
        )
        assert (
            pb.campaign_for(["1.5M Langley Homes-copy-copy"], "Facebook").key == "homes"
        )
        assert pb.campaign_for([], "Referral").key == "general"

    def test_plan_a_steps(self) -> None:
        assert pb.plan_a_step(0)[1] == "1"
        assert pb.plan_a_step(1)[1] == "2"
        assert pb.plan_a_step(3)[1] == "email"
        assert pb.plan_a_step(5)[1] == "3"
        assert pb.plan_a_step(14)[1] == "5"

    def test_texts_introduce_the_team(self) -> None:
        for campaign in pb.CAMPAIGNS.values():
            assert "Nimar Gill's team at Sutton" in campaign.texts["1"]

    def test_fill_keeps_unknown_placeholders(self) -> None:
        assert (
            pb.fill("A {listing} in {area}", area="Clayton") == "A {listing} in Clayton"
        )


class TestEngine:
    def test_reply_now_comes_first(self, report) -> None:  # type: ignore[no-untyped-def]
        assert report.worklist[0].lead.name == "Priya Sandhu"
        assert report.worklist[0].action.code == "reply_now"

    def test_leads_land_in_the_right_smart_list(self, report) -> None:  # type: ignore[no-untyped-def]
        expected = {
            "Jason Tran": 1,
            "Maria Gonzalez": 1,
            "Kevin O'Brien": 2,
            "Raj Bains": 2,
            "Aman Gill": 3,
            "Chris Lee": 3,
            "Pam Grewal": 3,
            "Tom Anderson": 4,
            "Unreached1 Lead": 4,
            "Sarah Thompson": 5,
            "Lisa Wong": 6,
            "Grace Nguyen": 7,
            "Jas Toor": 7,
        }
        assert {name: by_name(report, name).smart_list for name in expected} == expected

    def test_recommendation_paths(self, report) -> None:  # type: ignore[no-untyped-def]
        expected = {
            "Jason Tran": "plan_a",
            "Maria Gonzalez": "plan_a",
            "Daniel Kim": "plan_a",
            "Unreached1 Lead": "first_contact",
            "Unreached4 Lead": "unreached_retry",
            "Tom Anderson": "close_loop",
            "Aman Gill": "confirm_appointment",
            "Sarah Thompson": "qualify",
            "Kevin O'Brien": "broker_intro",
            "Harpreet Dhillon": "send_listings",
            "Emily Chen": "book_showing",
            "Mike Patel": "showing_follow_up",
            "Chris Lee": "deal_check_in",
            "Pam Grewal": "seller_update",
            "Lisa Wong": "nurture_value",
            "Grace Nguyen": "referral_touch",
            "Rachel Martin": "update_crm",
            "Alyn Brooks": "update_crm",
        }
        actual = {name: by_name(report, name).action.code for name in expected}
        assert actual == expected

    def test_plan_a_uses_the_ad_specific_text(self, report) -> None:  # type: ignore[no-untyped-def]
        jason = by_name(report, "Jason Tran").action
        assert "day 0" in jason.label and "Cloverdale homes list" in jason.text_draft
        assert "Cloverdale homes list" in jason.voicemail
        maria = by_name(report, "Maria Gonzalez").action
        assert maria.channel == "Email"  # day 2: email 3 listings

    def test_exclusions(self, report) -> None:  # type: ignore[no-untyped-def]
        assert "Realtor" in by_name(report, "Rachel Martin").excluded_reason
        assert "Do Not Contact" in by_name(report, "Alyn Brooks").excluded_reason
        listed = {i.lead.name for i in report.worklist}
        assert not {"Rachel Martin", "Alyn Brooks"} & listed

    def test_not_due_leads_stay_off_the_sheet(self, report) -> None:  # type: ignore[no-untyped-def]
        for name in ("Nina Kaur", "Brandon Singh"):
            i = by_name(report, name)
            assert not i.due and i not in report.worklist

    def test_daily_caps(self, report) -> None:  # type: ignore[no-untyped-def]
        unreached = next(s for s in report.sections if s.smart_list.number == 4)
        assert len(unreached.items) == 10 and unreached.held_over > 0
        # never-contacted leads first, newest first
        assert unreached.items[0].lead.name == "Unreached1 Lead"

    def test_temperatures(self, report) -> None:  # type: ignore[no-untyped-def]
        assert by_name(report, "Priya Sandhu").temperature == "Hot"
        assert by_name(report, "Lisa Wong").temperature == "Nurture"
        assert by_name(report, "Grace Nguyen").temperature == "Sphere"

    def test_every_listed_lead_has_a_reason_and_date(self, report) -> None:  # type: ignore[no-untyped-def]
        for i in report.worklist:
            assert i.reasons or i.action.why
            assert i.action.follow_up is not None

    def test_land_buyer_criteria(self, report) -> None:  # type: ignore[no-untyped-def]
        raj = by_name(report, "Raj Bains").criteria
        assert (raj.min_price, raj.max_price) == (5_000_000, 7_000_000)
        assert raj.acres_label == "20–40 acres" and raj.down_payment == 3_000_000
        assert "Income" in raj.land_use and "Yard" not in raj.must_haves
        mike = by_name(report, "Mike Patel").criteria
        assert mike.acres_label == "~5 acres"  # "3 acreages" is not "3 acres"

    def test_never_contacted_new_lead_starts_plan_a_at_text_1(self) -> None:
        lead = make_lead(
            tags=["2.5M Langley Acreages-copy"],
            created=(AS_OF - timedelta(days=5)).isoformat(),
        )
        act = build_insight(lead, AS_OF).action
        assert act.code == "plan_a" and "not contacted yet" in act.label
        assert "Langley acreage list" in act.text_draft  # text 1, not text 3

    def test_html_notes_are_read_as_text(self) -> None:
        n = Note.from_fub(
            {
                "id": 1,
                "personId": 1,
                "body": "<p>Wants <b>5 acres</b> in Aldergrove</p>",
                "isHtml": True,
            }
        )
        assert n.body == "Wants 5 acres in Aldergrove"

    def test_priority_order_replied_clients_hot_new_unreached(self, report) -> None:  # type: ignore[no-untyped-def]
        tiers = [i.tier for i in report.worklist]
        assert tiers == sorted(tiers)
        assert tiers[0] == 0  # replied first
        names = [i.lead.name for i in report.worklist]
        first_new = min(
            names.index(i.lead.name) for i in report.worklist if i.smart_list == 1
        )
        for i in report.worklist:
            if i.smart_list in (2, 3):
                assert names.index(i.lead.name) < first_new

    def test_new_leads_never_outrank_clients_or_hot_even_with_high_points(self) -> None:
        fresh = make_lead(
            id=1, created=(AS_OF - timedelta(hours=1)).isoformat(), tags=["0-3mo"]
        )
        client = make_lead(id=2, stage="Active Client")
        client.interactions.append(
            Interaction(
                "call",
                2,
                False,
                AS_OF - timedelta(days=5),
                outcome="Interested",
                duration=300,
            )
        )
        hot = make_lead(id=3, stage="Hot Prospect")
        hot.interactions.append(
            Interaction(
                "call",
                3,
                False,
                AS_OF - timedelta(days=5),
                outcome="Interested",
                duration=300,
            )
        )
        ranked = rank([build_insight(x, AS_OF) for x in (fresh, hot, client)])
        assert [i.lead.id for i in ranked] == [2, 3, 1]

    def test_new_lead_points_lowered(self) -> None:
        assert (
            WEIGHTS["new_lead_uncontacted"] + WEIGHTS["new_lead_under_24h_bonus"]
            < WEIGHTS["follow_up_due"] + WEIGHTS["timeline_3m"]
        )

    def test_hot_leads_ranked_by_buying_signals(self, report) -> None:  # type: ignore[no-untyped-def]
        hot = next(s for s in report.sections if s.smart_list.number == 2).items
        signals = [i.signal_score for i in hot]
        assert signals == sorted(signals, reverse=True)
        top = hot[0]
        assert top.signal_score >= 8 and top.buying_signals
        assert "Buying signals" in render_markdown(report)

    def test_zero_to_three_month_tag_sets_timeline(self) -> None:
        i = build_insight(make_lead(tags=["0-3mo"]), AS_OF)
        assert i.criteria.timeline_months == 3

    def test_unknown_stage_does_not_crash(self) -> None:
        i = build_insight(make_lead(stage="Something Custom"), AS_OF)
        assert i.action.code

    def test_no_placeholder_leaks_except_listing_details(self, report) -> None:  # type: ignore[no-untyped-def]
        allowed = {"{listing}", "{area}", "{price}"}
        import re as _re

        for i in report.worklist:
            left = set(_re.findall(r"\{\w+\}", i.action.text_draft))
            assert left <= allowed, (i.lead.name, left)

    def test_minimum_day_keeps_clients_hot_and_new(self, bundle) -> None:  # type: ignore[no-untyped-def]
        r = build_report(bundle, AS_OF, day="minimum")
        assert [s.smart_list.number for s in r.sections] == [3, 2, 1]
        assert r.day_type.dials == 15


# --------------------------------------------------------------- reports


class TestReports:
    def test_overdue_tasks(self, report) -> None:  # type: ignore[no-untyped-def]
        names = [o.task.name for o in report.overdue]
        assert names[0] == "Send Kevin mortgage broker contact"
        assert "Print open house sign-in QR code" in names  # no contact linked
        assert "Home anniversary card" not in names  # completed
        assert "Send Brandon comparable sales" not in names  # future
        days = [o.days_overdue for o in report.overdue]
        assert days == sorted(days, reverse=True)

    def test_notes_summary(self, report) -> None:  # type: ignore[no-untyped-def]
        lines = by_name(report, "Priya Sandhu").activity.summary_lines
        assert lines[0].startswith("Sep 25 · Text in")
        assert len(lines) <= 4

    def test_markdown_follows_the_day(self, report) -> None:  # type: ignore[no-untyped-def]
        md = render_markdown(report)
        order = [
            "## 1 · Replied — waiting on you",
            "## 2 · Active clients",
            "## 3 · Hot leads",
            "## 4 · New leads",
            "## 5 · Unreached",
            "## 6 · Prospects",
            "## 7 · Nurture",
            "## 8 · Sphere",
            "All overdue tasks",
            "Appointments ahead",
            "Clean up in FUB",
            "Scorecard",
        ]
        positions = [md.index(h) for h in order]
        assert positions == sorted(positions)
        assert "Office day" in md and "40 dials" in md
        assert "Weekend" in md  # Sep 26, 2026 is a Saturday
        assert "Scripts for this list" in md and "Hi {name}," in md

    def test_csv_is_valid_and_in_order(self, report) -> None:  # type: ignore[no-untyped-def]
        rows = list(csv.DictReader(io.StringIO(render_csv(report))))
        assert len(rows) == len(report.worklist)
        assert (
            rows[0]["name"] == "Priya Sandhu" and rows[0]["smart_list"] == "Reply now"
        )
        assert all(r["next_follow_up"] for r in rows)

    def test_json_round_trip(self, report) -> None:  # type: ignore[no-untyped-def]
        data = json.loads(render_json(report))
        assert data["worklist"][0] == 101
        raj = next(x for x in data["leads"] if x["id"] == 118)
        assert raj["criteria"]["acres"] == "20–40 acres"

    def test_lead_card_shows_evidence(self, report) -> None:  # type: ignore[no-untyped-def]
        card = render_lead_card(by_name(report, "Kevin O'Brien"), AS_OF)
        assert "Where the criteria came from" in card and "Clayton" in card
        assert "Smart List 2" in card


# --------------------------------------------------------------- sources & safety


class TestSources:
    def test_json_file_source(self, tmp_path, bundle) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "bundle.json"
        path.write_text(json.dumps(bundle))
        loaded = JsonFileSource(str(path)).load()
        assert len(build_leads(loaded)) == len(bundle["people"])

    def test_build_leads_attaches_children(self, bundle) -> None:  # type: ignore[no-untyped-def]
        leads = {x.id: x for x in build_leads(bundle)}
        assert leads[101].notes and leads[101].tasks and leads[101].interactions
        assert leads[105].appointments

    def test_live_source_disabled_without_opt_in(self) -> None:
        with pytest.raises(LiveAccessDisabled):
            LiveReadOnlySource(env={"FOLLOW_UP_BOSS_API_KEY": "fake"})

    def test_read_only_client_blocks_writes_without_network(self) -> None:
        client = make_read_only_client(api_key="fake-key-not-real")
        for call in (
            lambda: client._post("people", json_data={}),
            lambda: client._put("people/1", {}),
            lambda: client._delete("people/1"),
        ):
            with pytest.raises(ReadOnlyViolation):
                call()
        with pytest.raises(ReadOnlyViolation):
            client._request("POST", "people")

    def test_proxy_credential_mode_sends_no_auth(self) -> None:
        from unittest.mock import MagicMock, patch

        resp = MagicMock(status_code=200, headers={})
        resp.json.return_value = {"people": []}
        with patch("follow_up_boss.client.requests.request", return_value=resp) as req:
            make_read_only_client(api_key=None)._get("people")
        assert "auth" not in req.call_args.kwargs
        with patch("follow_up_boss.client.requests.request", return_value=resp) as req:
            make_read_only_client(api_key="k")._get("people")
        assert req.call_args.kwargs["auth"] == ("k", "")

    def test_live_source_only_issues_gets(self, bundle) -> None:  # type: ignore[no-untyped-def]
        calls: List[str] = []

        class FakeClient:
            def _get(self, endpoint: str, params: Any = None) -> Dict[str, Any]:
                calls.append(endpoint)
                key = {"textMessages": "textmessages"}.get(endpoint, endpoint)
                if endpoint == "people":
                    return {"people": bundle["people"][:2]}
                return {
                    key: [
                        r
                        for r in bundle.get(endpoint, [])
                        if (params or {}).get("personId") in (None, r.get("personId"))
                    ]
                }

            def get_absolute(self, url: str) -> Dict[str, Any]:  # pragma: no cover
                raise AssertionError("no pagination expected")

        src = LiveReadOnlySource(
            client=FakeClient(),
            per_request_pause=0,
            env={"FUB_TOOLKIT_ALLOW_LIVE": "1"},
        )
        data = src.load()
        assert len(data["people"]) == 2
        assert set(calls) <= {
            "people",
            "tasks",
            "appointments",
            "notes",
            "calls",
            "textMessages",
            "events",
        }
        assert data["textMessages"], "per-person text messages should be collected"


# --------------------------------------------------------------- CLI


class TestCli:
    def test_daily_markdown(self, capsys) -> None:  # type: ignore[no-untyped-def]
        assert main(["--as-of", "2026-09-26", "daily"]) == 0
        assert "Priya Sandhu" in capsys.readouterr().out

    def test_daily_csv_to_file(self, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
        out = tmp_path / "today.csv"
        assert (
            main(
                ["--as-of", "2026-09-26", "daily", "--format", "csv", "--out", str(out)]
            )
            == 0
        )
        assert out.read_text().startswith("order,smart_list,name,phone")

    def test_lead_tasks_criteria_commands(self, capsys) -> None:  # type: ignore[no-untyped-def]
        assert main(["--as-of", "2026-09-26", "lead", "107"]) == 0
        assert "Kevin" in capsys.readouterr().out
        assert main(["--as-of", "2026-09-26", "lead", "999"]) == 1
        assert main(["--as-of", "2026-09-26", "tasks"]) == 0
        assert "overdue" in capsys.readouterr().out
        assert main(["--as-of", "2026-09-26", "criteria"]) == 0
        assert "missing:" in capsys.readouterr().out

    def test_live_mode_blocked_by_default(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("FUB_TOOLKIT_ALLOW_LIVE", raising=False)
        assert main(["--source", "live", "daily"]) == 2
        assert "Blocked" in capsys.readouterr().err

    def test_file_source_requires_path(self) -> None:
        with pytest.raises(SystemExit):
            main(["--source", "file", "daily"])


# --------------------------------------------------------------- SDK logging fix


class TestSdkLogging:
    def test_requests_are_silent_by_default(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        from unittest.mock import MagicMock, patch

        from follow_up_boss.client import FollowUpBossApiClient

        monkeypatch.delenv("FOLLOW_UP_BOSS_DEBUG", raising=False)
        resp = MagicMock(status_code=200, headers={})
        resp.json.return_value = {
            "people": [
                {"name": "Private Client", "phones": [{"value": "604-555-9999"}]}
            ]
        }
        with patch("follow_up_boss.client.requests.request", return_value=resp):
            FollowUpBossApiClient(
                api_key="k", x_system="S", x_system_key="secret-key"
            )._get("people")
        assert capsys.readouterr().out == ""

    def test_debug_mode_redacts_system_key(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        from unittest.mock import MagicMock, patch

        from follow_up_boss.client import FollowUpBossApiClient

        monkeypatch.setenv("FOLLOW_UP_BOSS_DEBUG", "1")
        resp = MagicMock(status_code=200, headers={})
        resp.json.return_value = {}
        with patch("follow_up_boss.client.requests.request", return_value=resp):
            FollowUpBossApiClient(
                api_key="k", x_system="S", x_system_key="secret-key"
            )._get("people")
        out = capsys.readouterr().out
        assert "API Request" in out and "secret-key" not in out


# --------------------------------------------------------------- day type from calendar


class TestDayType:
    TODAY = AS_OF.date()

    def ev(self, summary: str, start: str, created: str) -> Dict[str, Any]:
        return {"summary": summary, "start": {"dateTime": start}, "created": created}

    def test_no_shift_is_office(self) -> None:
        events = [self.ev("Gym", "2026-09-26T06:45:00-07:00", "2026-09-01T00:00:00Z")]
        assert day_type_for(events, self.TODAY) == "office"

    def test_scheduled_bcldb_shift_is_shift(self) -> None:
        events = [
            self.ev("BCLDB Shift", "2026-09-26T05:30:00-07:00", "2026-09-19T00:00:00Z")
        ]
        assert day_type_for(events, self.TODAY) == "shift"

    def test_called_in_shift_is_minimum(self) -> None:
        events = [
            self.ev("BCLDB Shift", "2026-09-26T05:30:00-07:00", "2026-09-25T20:00:00Z")
        ]
        assert day_type_for(events, self.TODAY) == "minimum"

    def test_other_days_and_other_titles_ignored(self) -> None:
        events = [
            self.ev("BCLDB Shift", "2026-09-27T05:30:00-07:00", "2026-09-01T00:00:00Z"),
            self.ev(
                "Wake Up + Leave for Shift",
                "2026-09-26T04:30:00-07:00",
                "2026-09-01T00:00:00Z",
            ),
            dict(
                self.ev(
                    "BCLDB Shift", "2026-09-26T05:30:00-07:00", "2026-09-01T00:00:00Z"
                ),
                status="cancelled",
            ),
        ]
        assert day_type_for(events, self.TODAY) == "office"

    def test_cli_reads_calendar_json(self, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
        path = tmp_path / "events.json"
        path.write_text(
            json.dumps(
                {
                    "events": [
                        self.ev(
                            "BCLDB Shift",
                            "2026-09-26T05:30:00-07:00",
                            "2026-09-10T00:00:00Z",
                        )
                    ]
                }
            )
        )
        assert main(["--as-of", "2026-09-26", "daytype", "--events", str(path)]) == 0
        assert capsys.readouterr().out.strip() == "shift"
