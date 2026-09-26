"""
Fictional Follow Up Boss data shaped like Karan's real account.

Same stages, ad tags and kinds of leads (Cloverdale homes ad, Langley acreage
ad, land/industrial investors, a long unreached pile), but every name, phone
number (555 range), email (example.com) and address is made up. Timestamps are
generated relative to ``as_of`` so the demo always looks like "this morning".
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

HOMES_TAG = "1.5M Langley Homes-copy-copy"
ACREAGE_TAG = "2.5M Langley Acreages-copy"


def build_mock_bundle(as_of: datetime) -> Dict[str, List[Dict[str, Any]]]:
    def ago(days: float = 0, hours: float = 0) -> str:
        t = (as_of - timedelta(days=days, hours=hours)).astimezone(timezone.utc)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    def ahead(days: float = 0, hours: float = 0) -> str:
        return ago(-days, -hours)

    def due(days_from_today: int) -> str:
        return (as_of.date() + timedelta(days=days_from_today)).isoformat()

    def person(
        pid: int,
        first: str,
        last: str,
        stage: str,
        created: str,
        phone: str,
        tags: List[str],
        **extra: Any,
    ) -> Dict[str, Any]:
        rec = {
            "id": pid,
            "firstName": first,
            "lastName": last,
            "name": f"{first} {last}",
            "stage": stage,
            "source": extra.pop("source", "Facebook"),
            "created": created,
            "phones": [{"value": phone, "type": "mobile", "isPrimary": 1}],
            "emails": [
                {
                    "value": f"{first.lower()}.{last.lower().replace(chr(39), '')}@example.com",
                    "isPrimary": 1,
                }
            ],
            "tags": tags,
        }
        rec.update(extra)
        return rec

    people: List[Dict[str, Any]] = [
        person(
            101,
            "Priya",
            "Sandhu",
            "Hot Prospect",
            ago(21),
            "604-555-0101",
            [HOMES_TAG, "0-3mo", "Listing Alert"],
        ),
        person(
            102,
            "Jason",
            "Tran",
            "Lead",
            ago(hours=0.7),
            "778-555-0102",
            [HOMES_TAG],
            background="Q: When are you looking to buy? A: 0-3 months\nQ: Are you pre-approved? A: No",
        ),
        person(
            103,
            "Maria",
            "Gonzalez",
            "Attempted Contact",
            ago(2, 1),
            "604-555-0103",
            [ACREAGE_TAG],
        ),
        person(
            104,
            "Daniel",
            "Kim",
            "Attempted Contact",
            ago(4, 1),
            "778-555-0104",
            [HOMES_TAG],
        ),
        person(
            105,
            "Aman",
            "Gill",
            "Appointment Set",
            ago(40),
            "604-555-0105",
            [ACREAGE_TAG, "Listing Alert"],
        ),
        person(
            106,
            "Sarah",
            "Thompson",
            "Spoke with Customer",
            ago(30),
            "604-555-0106",
            [HOMES_TAG],
        ),
        person(
            107,
            "Kevin",
            "O'Brien",
            "Hot Prospect",
            ago(15),
            "778-555-0107",
            [HOMES_TAG, "0-3mo"],
        ),
        person(
            108,
            "Harpreet",
            "Dhillon",
            "Hot Prospect",
            ago(9),
            "604-555-0108",
            [ACREAGE_TAG, "0-3mo"],
        ),
        person(
            109,
            "Emily",
            "Chen",
            "Active Client",
            ago(30),
            "778-555-0109",
            [HOMES_TAG, "Listing Alert"],
        ),
        person(
            110,
            "Mike",
            "Patel",
            "Active Client",
            ago(45),
            "604-555-0110",
            [ACREAGE_TAG, "Listings Sent"],
        ),
        person(111, "Lisa", "Wong", "Nurture", ago(120), "778-555-0111", [HOMES_TAG]),
        person(
            112,
            "Tom",
            "Anderson",
            "Attempted Contact",
            ago(30),
            "604-555-0112",
            [HOMES_TAG],
        ),
        person(
            113,
            "Rachel",
            "Martin",
            "Attempted Contact",
            ago(10),
            "778-555-0113",
            [HOMES_TAG],
        ),
        person(
            114,
            "Chris",
            "Lee",
            "Under Contract",
            ago(90),
            "604-555-0114",
            [],
            source="Referral",
        ),
        person(
            115,
            "Grace",
            "Nguyen",
            "Past Client",
            ago(700),
            "778-555-0115",
            [],
            source="Referral",
        ),
        person(
            116,
            "Brandon",
            "Singh",
            "Spoke with Customer",
            ago(18),
            "604-555-0116",
            [HOMES_TAG, "Listing Alert"],
        ),
        person(117, "Nina", "Kaur", "Nurture", ago(60), "778-555-0117", [ACREAGE_TAG]),
        person(
            118,
            "Raj",
            "Bains",
            "Hot Prospect",
            ago(25),
            "604-555-0118",
            ["Investor-Commercial", "Nimar-Handoff"],
            source="Nimar handoff",
        ),
        person(
            119,
            "Alyn",
            "Brooks",
            "Attempted Contact",
            ago(20),
            "778-555-0119",
            [HOMES_TAG, "Do Not Contact"],
        ),
        person(
            120,
            "Pam",
            "Grewal",
            "Active Listing",
            ago(60),
            "604-555-0120",
            ["Seller-Potential"],
            source="Referral",
        ),
        person(
            121, "Jas", "Toor", "Sphere", ago(400), "778-555-0121", [], source="Sphere"
        ),
    ]
    # The unreached pile: Aug–Sep ad leads that were never called, plus a few
    # tried once long ago. More than the 10-a-day cap on purpose.
    for n in range(12):
        tried = n % 4 == 3
        people.append(
            person(
                130 + n,
                f"Unreached{n + 1}",
                "Lead",
                "Attempted Contact" if tried else "Lead",
                ago(12 + n * 4),
                f"604-555-02{n:02d}",
                [ACREAGE_TAG if n % 2 else HOMES_TAG],
            )
        )

    notes: List[Dict[str, Any]] = [
        {
            "id": 1,
            "personId": 101,
            "created": ago(5),
            "subject": "Call",
            "body": "Spoke with Priya. Renting in Newton, lease ends in 2 months. Wants a 4 bed detached with a basement suite in Cloverdale or Clayton, "
            "up to $1.45M, pre-approved. Husband also deciding. Sent 4 listings after the call.",
        },
        {
            "id": 2,
            "personId": 105,
            "created": ago(8),
            "subject": "Acreage search",
            "body": "Met with Aman and his wife. Want 2-5 acres in South Langley or Glen Valley to live on, detached home with a shop, up to $2.4M. "
            "Need to sell our Burnaby house first. Timeline 3-6 months. Pre-approved.",
        },
        {
            "id": 3,
            "personId": 106,
            "created": ago(16),
            "subject": "Intro call",
            "body": "Talked to Sarah briefly — interested in Cloverdale, has two kids, asked to call back to go over details.",
        },
        {
            "id": 4,
            "personId": 107,
            "created": ago(4),
            "subject": "Call notes",
            "body": "Spoke with Kevin. First-time buyer, renting in Burnaby. Wants a 3 bed townhouse in Clayton, "
            "budget $850k-$950k, 0-3 months. Not pre-approved yet, hasn't talked to a broker.",
        },
        {
            "id": 5,
            "personId": 108,
            "created": ago(2),
            "subject": "Acreage call",
            "body": "Had a great call with Harpreet. Wants 5-10 acres in South Langley to build 2 houses for the family. "
            "Up to $2.4M, pre-approved, 1-3 months. Asked about subdivision — told him we'd confirm with the Township/ALC.",
        },
        {
            "id": 6,
            "personId": 109,
            "created": ago(10),
            "subject": "Buyer consult",
            "body": "Met with Emily. 3 bed townhouse in Clayton or Cloverdale, up to $900k, pre-approved, 1-3 months. Set up listing alert and sent 5 listings.",
        },
        {
            "id": 7,
            "personId": 110,
            "created": ago(3),
            "subject": "Showing recap",
            "body": "Showed Mike 3 acreages in Aldergrove. Liked the 5 acre on 272 St but wants a bigger shop for his trucks. "
            "Up to $2.2M, pre-approved, renting. Timeline 2-4 months.",
        },
        {
            "id": 8,
            "personId": 111,
            "created": ago(50),
            "subject": "Nurture",
            "body": "Spoke with Lisa. Just browsing for now, maybe next year. Owns a condo in New Westminster, curious about a townhouse in Cloverdale.",
        },
        {
            "id": 9,
            "personId": 113,
            "created": ago(3),
            "subject": "Call",
            "body": "Rachel said she's working with another realtor already.",
        },
        {
            "id": 10,
            "personId": 115,
            "created": ago(40),
            "subject": "Check-in",
            "body": "Called Grace. Happy in the South Surrey house.",
        },
        {
            "id": 11,
            "personId": 116,
            "created": ago(3),
            "subject": "Check-in",
            "body": "Spoke with Brandon. 3 bed townhouse in Cloverdale, up to $875k, pre-approved, 6-9 months. Liked two from the alert.",
        },
        {
            "id": 12,
            "personId": 117,
            "created": ago(5),
            "subject": "Nurture call",
            "body": "Talked to Nina. Wants 2 acres in Aldergrove in about 12 months after retirement. Budget around $1.8M. Not in a rush.",
        },
        {
            "id": 13,
            "personId": 118,
            "created": ago(9),
            "subject": "Nimar handoff",
            "body": "Spoke with Raj. Wants 20-40 acres of income-producing industrial land, truck yard near Deltaport. "
            "Budget $5M-$7M, $3M down. Timeline 3-6 months.",
        },
        {
            "id": 14,
            "personId": 120,
            "created": ago(4),
            "subject": "Listing",
            "body": "Pam's listing went live. 2 showings so far.",
        },
        {
            "id": 15,
            "personId": 121,
            "created": ago(35),
            "subject": "Coffee",
            "body": "Coffee with Jas. Doing well, might know someone looking in Langley.",
        },
        {
            "id": 16,
            "personId": 114,
            "created": ago(4),
            "subject": "Deal",
            "body": "Subject removal due next week. Waiting on strata docs.",
        },
    ]

    calls: List[Dict[str, Any]] = (
        [
            {
                "id": 201,
                "personId": 101,
                "created": ago(5),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 840,
            },
            {
                "id": 202,
                "personId": 101,
                "created": ago(2),
                "isIncoming": 0,
                "outcome": "No Answer",
                "duration": 0,
            },
            {
                "id": 203,
                "personId": 103,
                "created": ago(2),
                "isIncoming": 0,
                "outcome": "No Answer",
                "duration": 0,
            },
            {
                "id": 204,
                "personId": 103,
                "created": ago(1),
                "isIncoming": 0,
                "outcome": "No Answer",
                "duration": 0,
            },
            {
                "id": 205,
                "personId": 105,
                "created": ago(8),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 1200,
            },
            {
                "id": 206,
                "personId": 106,
                "created": ago(16),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 180,
            },
            {
                "id": 207,
                "personId": 107,
                "created": ago(4),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 600,
            },
            {
                "id": 208,
                "personId": 108,
                "created": ago(2),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 900,
            },
            {
                "id": 209,
                "personId": 109,
                "created": ago(10),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 1500,
            },
            {
                "id": 210,
                "personId": 109,
                "created": ago(5),
                "isIncoming": 0,
                "outcome": "Left Message",
                "duration": 25,
            },
            {
                "id": 211,
                "personId": 110,
                "created": ago(3),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 300,
            },
            {
                "id": 212,
                "personId": 111,
                "created": ago(50),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 420,
            },
            {
                "id": 213,
                "personId": 113,
                "created": ago(3),
                "isIncoming": 0,
                "outcome": "Not Interested",
                "duration": 90,
            },
            {
                "id": 214,
                "personId": 115,
                "created": ago(40),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 600,
            },
            {
                "id": 215,
                "personId": 116,
                "created": ago(3),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 480,
            },
            {
                "id": 216,
                "personId": 117,
                "created": ago(5),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 360,
            },
            {
                "id": 217,
                "personId": 118,
                "created": ago(9),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 1100,
            },
            {
                "id": 218,
                "personId": 114,
                "created": ago(4),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 240,
            },
            {
                "id": 219,
                "personId": 120,
                "created": ago(4),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 300,
            },
            {
                "id": 220,
                "personId": 104,
                "created": ago(4),
                "isIncoming": 0,
                "outcome": "No Answer",
                "duration": 0,
            },
            {
                "id": 221,
                "personId": 104,
                "created": ago(3),
                "isIncoming": 0,
                "outcome": "No Answer",
                "duration": 0,
            },
            {
                "id": 222,
                "personId": 121,
                "created": ago(35),
                "isIncoming": 0,
                "outcome": "Interested",
                "duration": 900,
            },
        ]
        + [
            {
                "id": 230 + i,
                "personId": 112,
                "created": ago(29 - i * 4),
                "isIncoming": 0,
                "outcome": "No Answer",
                "duration": 0,
            }
            for i in range(4)
        ]
        + [
            {
                "id": 260 + n,
                "personId": 130 + n,
                "created": ago(10 + n),
                "isIncoming": 0,
                "outcome": "No Answer",
                "duration": 0,
            }
            for n in range(12)
            if n % 4 == 3
        ]
    )

    texts: List[Dict[str, Any]] = [
        {
            "id": 301,
            "personId": 101,
            "created": ago(5),
            "isIncoming": 0,
            "message": "Great chatting Priya! Here are 4 homes in Clayton that fit — let me know which ones stand out.",
        },
        {
            "id": 302,
            "personId": 101,
            "created": ago(hours=18),
            "isIncoming": 1,
            "message": "Hi Karan, is the one on 188 St still available? Could we see it this weekend?",
        },
        {
            "id": 303,
            "personId": 104,
            "created": ago(4),
            "isIncoming": 0,
            "message": "Hi Daniel, it's Karan with Nimar Gill's team at Sutton...",
        },
        {
            "id": 304,
            "personId": 110,
            "created": ago(3),
            "isIncoming": 1,
            "message": "Thanks for today, we'll talk it over.",
        },
        {
            "id": 305,
            "personId": 110,
            "created": ago(3),
            "isIncoming": 0,
            "message": "Sounds good Mike, talk soon.",
        },
        {
            "id": 306,
            "personId": 106,
            "created": ago(16),
            "isIncoming": 1,
            "message": "Maybe something under 1.2M? Will know more after we talk to the bank",
        },
        {
            "id": 307,
            "personId": 103,
            "created": ago(2),
            "isIncoming": 0,
            "message": "Hi Maria, it's Karan with Nimar Gill's team at Sutton...",
        },
    ] + [
        {
            "id": 320 + i,
            "personId": 112,
            "created": ago(27 - i * 4),
            "isIncoming": 0,
            "message": "Hi Tom, Karan here following up on the Cloverdale homes list.",
        }
        for i in range(3)
    ]

    tasks: List[Dict[str, Any]] = [
        {
            "id": 401,
            "personId": 101,
            "name": "Send Priya the disclosure for the 188 St home",
            "type": "Email",
            "dueDate": due(-1),
            "isCompleted": 0,
        },
        {
            "id": 402,
            "personId": 106,
            "name": "Call Sarah back re budget and timing",
            "type": "Call",
            "dueDate": due(-2),
            "isCompleted": 0,
        },
        {
            "id": 403,
            "personId": 107,
            "name": "Send Kevin mortgage broker contact",
            "type": "Follow Up",
            "dueDate": due(-3),
            "isCompleted": 0,
        },
        {
            "id": 404,
            "personId": 110,
            "name": "Find acreages with a bigger shop for Mike",
            "type": "Call",
            "dueDate": due(0),
            "isCompleted": 0,
        },
        {
            "id": 405,
            "personId": 118,
            "name": "Send Raj the Delta truck yard details",
            "type": "Follow Up",
            "dueDate": due(-2),
            "isCompleted": 0,
        },
        {
            "id": 406,
            "personId": 116,
            "name": "Send Brandon comparable sales",
            "type": "Email",
            "dueDate": due(3),
            "isCompleted": 0,
        },
        {
            "id": 407,
            "personId": 115,
            "name": "Home anniversary card",
            "type": "Follow Up",
            "dueDate": due(-40),
            "isCompleted": 1,
        },
        {
            "id": 408,
            "personId": None,
            "name": "Print open house sign-in QR code",
            "type": "Follow Up",
            "dueDate": due(-1),
            "isCompleted": 0,
        },
        {
            "id": 409,
            "personId": 114,
            "name": "Confirm strata docs received",
            "type": "Follow Up",
            "dueDate": due(-1),
            "isCompleted": 0,
        },
    ]

    appointments: List[Dict[str, Any]] = [
        {
            "id": 501,
            "title": "Showing - South Langley acreages",
            "start": ahead(hours=27),
            "end": ahead(hours=30),
            "location": "248 St, Langley",
            "invitees": [{"personId": 105, "name": "Aman Gill"}],
        },
        {
            "id": 502,
            "title": "Showing - 3 acreages in Aldergrove",
            "start": ago(3, 2),
            "end": ago(3),
            "invitees": [{"personId": 110, "name": "Mike Patel"}],
        },
    ]

    events: List[Dict[str, Any]] = [
        {
            "id": 601,
            "personId": 109,
            "type": "Viewed Property",
            "created": ago(1, 3),
            "property": {
                "street": "7890 188 St #14",
                "city": "Surrey",
                "price": 879000,
            },
        },
        {
            "id": 602,
            "personId": 109,
            "type": "Saved Property",
            "created": ago(1),
            "property": {
                "street": "7890 188 St #14",
                "city": "Surrey",
                "price": 879000,
            },
        },
        {
            "id": 603,
            "personId": 102,
            "type": "Registration",
            "created": ago(hours=0.7),
            "source": "Facebook",
        },
    ]

    return {
        "people": people,
        "tasks": tasks,
        "notes": notes,
        "calls": calls,
        "textMessages": texts,
        "appointments": appointments,
        "events": events,
    }
