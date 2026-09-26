"""
Karan's operating system, as data.

Stages, the 7 daily Smart Lists, cadences, day types, Action Plan A timing
and the Call Desk texts for each Facebook ad all live here, so the rest of the
toolkit follows the same playbook as Follow Up Boss and the Call Desk page.
Change the business rules here, not in the engine.
"""

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

AGENT = os.getenv("AGENT_NAME", "Karan")
TEAM_LINE = os.getenv("TEAM_LINE", "with Nimar Gill's team at Sutton")


@dataclass(frozen=True)
class SmartList:
    number: int
    name: str
    target: str
    daily_cap: Optional[int]  # None = everyone who is due
    channel: str  # "Call" or "Text"


SMART_LISTS: Dict[int, SmartList] = {
    1: SmartList(
        1, "New – Call Now", "Call twice a day until you reach them", None, "Call"
    ),
    2: SmartList(2, "Hot", "Everyone, every 2–3 days", None, "Call"),
    3: SmartList(3, "Clients", "Everyone, every 2–3 days", None, "Call"),
    4: SmartList(4, "Unreached", "10 a day", 10, "Call"),
    5: SmartList(5, "Prospects", "10 a day, oldest contact first", 10, "Call"),
    6: SmartList(6, "Nurture", "10 texts a day", 10, "Text"),
    7: SmartList(7, "Sphere & Past Clients", "10 a day, monthly", 10, "Call"),
}

# stage (lower case) -> (smart list, days between touches after a conversation)
STAGES: Dict[str, Tuple[int, int]] = {
    "lead": (1, 1),
    "attempted contact": (1, 1),
    "hot prospect": (2, 2),
    "appointment set": (3, 2),
    "active client": (3, 3),
    "active listing": (3, 3),
    "under contract": (3, 3),
    "pending": (3, 3),
    "spoke with customer": (5, 14),
    "prospect": (5, 14),
    "nurture": (6, 45),
    "sphere": (7, 30),
    "past client": (7, 30),
}
EXCLUDED_STAGES = {"trash", "closed", "sale closed", "archived"}
NEW_LEAD_DAYS = 7  # Lead / Attempted Contact older than this moves to Unreached
UNREACHED_GAP_DAYS = 3  # Unreached list: last attempt more than 3 days ago
STOP_TAGS = ("Do Not Contact", "DNC", "Bad Number")
AGENT_TAGS = ("Has-Agent",)


@dataclass(frozen=True)
class DayType:
    name: str
    dials: int
    texts: int
    conversations: int
    note: str


DAY_TYPES: Dict[str, DayType] = {
    "office": DayType(
        "Office day",
        40,
        20,
        4,
        "Lists 1→4 at 10:00, Lists 5–6 at 1:00, List 7 at 2:00, Lists 1+4 again at 4:30.",
    ),
    "shift": DayType(
        "Shift day",
        15,
        30,
        2,
        "Texts only during the shift (Lists 6 and 7). Call block 3:00–4:30: Lists 1→4.",
    ),
    "minimum": DayType(
        "Called in (minimum day)",
        15,
        0,
        1,
        "New leads get text 1 within 15 min. 15 dials after the shift. A task on every conversation. That's a win.",
    ),
}

# Action Plan A: day since the lead came in -> step
PLAN_A: List[Tuple[int, str, str]] = [
    (0, "1", "Call, then text 1 if no answer. Call again after 5 p.m."),
    (1, "2", "Call, then text 2"),
    (2, "email", "Email 3 hand-picked listings"),
    (4, "3", "Call, then text 3"),
    (7, "4", "Text 4 (new listing)"),
    (10, "call", "Call"),
    (14, "5", "Text 5 (close the loop), then move stage"),
]


def plan_a_step(days_in: int) -> Tuple[int, str, str]:
    """The Plan A step that applies ``days_in`` days after the lead came in."""
    step = PLAN_A[0]
    for item in PLAN_A:
        if days_in >= item[0]:
            step = item
    return step


@dataclass(frozen=True)
class Campaign:
    key: str
    name: str
    texts: Dict[str, str]
    voicemail: str
    qualifiers: List[str]


_intro = f"it's {AGENT} {TEAM_LINE}"

CAMPAIGNS: Dict[str, Campaign] = {
    "homes": Campaign(
        "homes",
        "Cloverdale Homes under $1.5M",
        {
            "1": f"Hi {{name}}, {_intro}. You should've got the Cloverdale homes list by email. I'm reaching out to see what you're actually looking for so I can send better matches. When's a good time for a quick call?",
            "2": "Quick question {name}: for Cloverdale, are you looking at detached, townhomes, or open to both?",
            "3": "Were you set on Cloverdale, or open to Clayton and Langley too? A few new ones just came up under $1.5M.",
            "4": "A {listing} just came up in {area} at {price}. Want me to send the details?",
            "5": "Hi {name}, should I keep sending Cloverdale options your way, or close your file for now? Either is totally fine.",
            "N": f"Hi {{name}}, {AGENT} here. Cloverdale had a few interesting sales this month. Are you still keeping an eye on the market, or has anything changed on your end?",
            "B": "Perfect {name}, you're booked for {day} at {time}. I'll send the addresses the day before. Anything specific you want me to look out for?",
        },
        f"Hi {{name}}, {_intro}, about the Cloverdale homes list you requested. I'd like to hear what you're looking for so I can send better matches. I'll send you a quick text too.",
        [
            "Browsing or actively searching?",
            "Cloverdale only, or open to Clayton, Langley, Surrey?",
            "Detached or townhouse? Bedrooms? Suite needed?",
            "What's got you looking, and how soon would you move?",
            "Own now / need to sell first? Talked to a lender?",
        ],
    ),
    "acreage": Campaign(
        "acreage",
        "Langley Acreages under $2.5M",
        {
            "1": f"Hi {{name}}, {_intro}. You should've got the Langley acreage list by email. I'm reaching out to see what you have in mind so I can send better matches. When's a good time for a quick call?",
            "2": "Quick question {name}: are you looking to live on the acreage, farm it, or more as an investment?",
            "3": "Roughly how much land are you after: 1–2 acres, around 5, or 10+? A few new ones just came up under $2.5M.",
            "4": "A {listing} just came up in {area} at {price}. Want me to send the details?",
            "5": "Hi {name}, should I keep sending Langley acreages your way, or close your file for now? Either is totally fine.",
            "N": f"Hi {{name}}, {AGENT} here. A few Langley acreages sold this month that were interesting for the price. Are you still keeping an eye out, or has anything changed on your end?",
            "B": "Perfect {name}, you're booked for {day} at {time}. I'll send the addresses and a route the day before. Anything you want me to check on the properties ahead of time?",
        },
        f"Hi {{name}}, {_intro}, about the Langley acreage list you requested. I'd like to hear what you have in mind so I can send better matches. I'll send you a quick text too.",
        [
            "Browsing or actively searching?",
            "How will you use the land: live, farm, business, investment?",
            "How many acres? Flat and usable?",
            "House needs? Shop, barn, truck parking? OK with ALR?",
            "How soon? Own now / sell first? Talked to a lender?",
        ],
    ),
    "general": Campaign(
        "general",
        "General enquiry",
        {
            "1": f"Hi {{name}}, {_intro}. Saw you were looking at {{topic}}. Just tried calling. Is now good for a quick chat, or later today?",
            "2": f"Hi {{name}}, {AGENT} again. Are you mainly looking to buy, sell, or just keeping an eye on the market for now?",
            "3": "Quick one {name}: a few new {area} listings came up this week around your range. Want me to send them over?",
            "4": "Quick one {name}: a few new {area} listings came up this week around your range. Want me to send them over?",
            "5": "Hi {name}, don't want to keep bugging you. Should I close your file, or keep sending the odd listing and market update?",
            "N": "Hi {name}, hope all's well. Has anything changed on your end with the move, or still looking at {timeline}?",
            "B": "Perfect, you're booked for {day} at {time}. I'll send the addresses the day before. Anything specific you want me to look out for?",
        },
        f"Hi {{name}}, {_intro}. I'd like to hear what you're looking for so I can help. I'll send you a quick text too.",
        [
            "Area and type of home?",
            "What's got you thinking about moving?",
            "Ideal timing?",
            "Renting or own now? Need to sell first?",
            "Talked to a lender? Anyone else involved in the decision?",
        ],
    ),
}

SELLER_SCRIPT = [
    "You'd requested a value on your home. Online estimates can be way off here, so I pulled a range from actual recent sales nearby. Thinking of selling at some point, or mainly curious?",
    "Book: a 15-minute walkthrough gets you a number you can plan around. Tuesday evening or Saturday?",
    "Not ready: email the CMA range, tag Seller-Potential + timeline, task in 90 days.",
]


def campaign_for(tags: List[str], source: str) -> Campaign:
    """Pick the Call Desk tab from the ad tag Facebook adds, or the source."""
    text = " ".join(tags + [source]).lower()
    if "acreage" in text:
        return CAMPAIGNS["acreage"]
    if re.search(r"1\.5m|cloverdale|langley homes|homes", text):
        return CAMPAIGNS["homes"]
    return CAMPAIGNS["general"]


def fill(template: str, **values: str) -> str:
    """Fill ``{placeholders}`` that we know; leave the rest for Karan to complete."""

    def repl(m: "re.Match[str]") -> str:
        value = values.get(m.group(1))
        return value if value else m.group(0)

    filled = re.sub(r"\{(\w+)\}", repl, template)
    return filled.replace("a.m..", "a.m.").replace("p.m..", "p.m.")
