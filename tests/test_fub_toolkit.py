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

from fub_toolkit.cli import main
from fub_toolkit.criteria import (
    extract_criteria,
    fmt_price,
    normalize_form,
    parse_budget,
    parse_financing,
    parse_timeline,
)
from fub_toolkit.engine import build_insight, rank
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


# --------------------------------------------------------------- engine


class TestEngine:
    def test_unanswered_reply_ranks_first(self, report) -> None:  # type: ignore[no-untyped-def]
        assert report.call_list[0].lead.name == "Priya Sandhu"
        assert report.call_list[0].action.code == "reply_now"

    def test_new_leads_are_speed_to_lead(self, report) -> None:  # type: ignore[no-untyped-def]
        for name in ("Jason Tran", "Maria Gonzalez"):
            i = by_name(report, name)
            assert i.action.code == "speed_to_lead" and i.on_call_list
        names = [i.lead.name for i in report.call_list]
        assert names.index("Jason Tran") < names.index(
            "Maria Gonzalez"
        )  # newer + shorter timeline first

    def test_recommendation_paths(self, report) -> None:  # type: ignore[no-untyped-def]
        expected = {
            "Daniel Kim": "attempt_contact",
            "Aman Gill": "confirm_appointment",
            "Sarah Thompson": "qualify",
            "Kevin O'Brien": "broker_intro",
            "Harpreet Dhillon": "send_listings",
            "Emily Chen": "book_showing",
            "Mike Patel": "showing_follow_up",
            "Lisa Wong": "nurture_value",
            "Tom Anderson": "move_to_nurture",
            "Grace Nguyen": "referral_touch",
            "Rachel Martin": "update_crm",
            "Chris Lee": "update_crm",
        }
        actual = {name: by_name(report, name).action.code for name in expected}
        assert actual == expected

    def test_exclusions(self, report) -> None:  # type: ignore[no-untyped-def]
        assert "another agent" in by_name(report, "Rachel Martin").excluded_reason
        assert "Under contract" in by_name(report, "Chris Lee").excluded_reason
        listed = {i.lead.name for i in report.call_list + report.value_list}
        assert not {"Rachel Martin", "Chris Lee"} & listed
        assert all(i.score == 0 for i in report.cleanup)

    def test_not_due_leads_stay_off_todays_lists(self, report) -> None:  # type: ignore[no-untyped-def]
        nina = by_name(report, "Nina Kaur")
        assert not nina.due and nina in report.not_due

    def test_temperatures(self, report) -> None:  # type: ignore[no-untyped-def]
        assert by_name(report, "Priya Sandhu").temperature == "Hot"
        assert by_name(report, "Lisa Wong").temperature == "Nurture"
        assert by_name(report, "Tom Anderson").temperature == "Nurture"
        assert by_name(report, "Grace Nguyen").temperature == "Sphere"

    def test_every_score_has_reasons(self, report) -> None:  # type: ignore[no-untyped-def]
        for i in report.call_list:
            assert i.score > 0 and i.reasons

    def test_every_active_lead_has_next_step_and_date(self, report) -> None:  # type: ignore[no-untyped-def]
        for i in report.insights:
            if not i.excluded_reason:
                assert i.action.label and i.action.follow_up is not None

    def test_rank_is_sorted_by_score(self, report) -> None:  # type: ignore[no-untyped-def]
        scores = [i.score for i in report.insights]
        assert scores == sorted(scores, reverse=True)

    def test_uncontacted_new_lead_beats_routine_follow_up(self) -> None:
        new = make_lead(id=1, created=(AS_OF - timedelta(hours=2)).isoformat())
        old = make_lead(id=2)
        old.interactions.append(
            Interaction(
                "call",
                2,
                False,
                AS_OF - timedelta(days=9),
                outcome="Interested",
                duration=300,
            )
        )
        ranked = rank([build_insight(old, AS_OF), build_insight(new, AS_OF)])
        assert ranked[0].lead.id == 1

    def test_do_not_contact_tag_excludes(self) -> None:
        i = build_insight(make_lead(tags=["DNC"]), AS_OF)
        assert i.excluded_reason and not i.on_call_list

    def test_drafts_use_agent_name_and_no_placeholders(self, report) -> None:  # type: ignore[no-untyped-def]
        for i in report.call_list + report.value_list:
            assert "{" not in i.action.text_draft
        assert "Karan" in by_name(report, "Jason Tran").action.text_draft
        custom = build_report(build_mock_bundle(AS_OF), AS_OF, agent="Alex")
        assert "Alex" in by_name(custom, "Jason Tran").action.text_draft


# --------------------------------------------------------------- reports


class TestReports:
    def test_overdue_tasks(self, report) -> None:  # type: ignore[no-untyped-def]
        names = [o.task.name for o in report.overdue]
        assert names[0] == "Send Kevin mortgage broker contacts"  # most overdue first
        assert (
            "Order open house signs for Sunday" in names
        )  # task with no contact still shown
        assert "Home anniversary card" not in names  # completed
        assert "Send Brandon comparable sales" not in names  # due in future
        assert [o.days_overdue for o in report.overdue] == sorted(
            (o.days_overdue for o in report.overdue), reverse=True
        )

    def test_notes_summary(self, report) -> None:  # type: ignore[no-untyped-def]
        lines = by_name(report, "Priya Sandhu").activity.summary_lines
        assert lines[0].startswith("Sep 25 · Text in")
        assert len(lines) <= 4

    def test_markdown_sections(self, report) -> None:  # type: ignore[no-untyped-def]
        md = render_markdown(report)
        for heading in (
            "Daily Call Sheet",
            "1. Call list",
            "2. Texts & emails",
            "3. Overdue tasks",
            "4. Upcoming appointments",
            "5. Clean up",
        ):
            assert heading in md
        assert "Saturday, September 26, 2026" in md

    def test_csv_is_valid_and_ranked(self, report) -> None:  # type: ignore[no-untyped-def]
        rows = list(csv.DictReader(io.StringIO(render_csv(report))))
        assert len(rows) == len(report.call_list) + len(report.value_list)
        assert rows[0]["name"] == "Priya Sandhu" and rows[0]["rank"] == "1"
        assert all(r["next_follow_up"] for r in rows)

    def test_json_round_trip(self, report) -> None:  # type: ignore[no-untyped-def]
        data = json.loads(render_json(report))
        assert data["call_list"][0] == 101
        priya = next(x for x in data["leads"] if x["id"] == 101)
        assert priya["criteria"]["max_price"] == 950_000
        assert priya["next_action"]["code"] == "reply_now"

    def test_lead_card_shows_evidence(self, report) -> None:  # type: ignore[no-untyped-def]
        card = render_lead_card(by_name(report, "Kevin O'Brien"), AS_OF)
        assert "Where the criteria came from" in card and "Coquitlam" in card


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
        assert out.read_text().startswith("rank,name,phone")

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
