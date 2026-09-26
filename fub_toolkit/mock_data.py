"""
Fictional Follow Up Boss data for the prototype.

All names, phone numbers (555 range) and emails (example.com) are made up.
Timestamps are generated relative to ``as_of`` so the demo always looks like
"this morning" and every recommendation path is exercised.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


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
        source: str,
        created: str,
        phone: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        rec = {
            "id": pid,
            "firstName": first,
            "lastName": last,
            "name": f"{first} {last}",
            "stage": stage,
            "source": source,
            "created": created,
            "phones": [{"value": phone, "type": "mobile", "isPrimary": 1}],
            "emails": [
                {
                    "value": f"{first.lower()}.{last.lower().replace(chr(39), '')}@example.com",
                    "isPrimary": 1,
                }
            ],
            "tags": extra.pop("tags", []),
        }
        rec.update(extra)
        return rec

    people: List[Dict[str, Any]] = [
        person(
            101,
            "Priya",
            "Sandhu",
            "Hot Prospect",
            "Facebook - Langley Townhomes",
            ago(21),
            "604-555-0101",
            background="Q: When are you looking to buy? A: 0-3 months\nQ: Are you pre-approved? A: Yes",
            tags=["Facebook", "Listings Sent"],
        ),
        person(
            102,
            "Jason",
            "Tran",
            "Lead",
            "Facebook - Surrey Condos Under $600k",
            ago(hours=0.7),
            "778-555-0102",
            background="Q: When are you looking to buy? A: 0-3 months\nQ: Are you pre-approved? A: No",
        ),
        person(
            103,
            "Maria",
            "Gonzalez",
            "Lead",
            "Facebook - Abbotsford Detached Homes",
            ago(hours=26),
            "604-555-0103",
            background="Q: When are you looking to buy? A: 3-6 months",
        ),
        person(
            104,
            "Daniel",
            "Kim",
            "Lead",
            "Facebook - First-Time Buyer Guide",
            ago(3),
            "778-555-0104",
        ),
        person(
            105,
            "Aman",
            "Gill",
            "Active Client",
            "Facebook - Fraser Valley Acreages",
            ago(40),
            "604-555-0105",
            tags=["Listings Sent"],
        ),
        person(
            106,
            "Sarah",
            "Thompson",
            "Lead",
            "Facebook - Chilliwack New Listings",
            ago(12),
            "604-555-0106",
        ),
        person(
            107,
            "Kevin",
            "O'Brien",
            "Lead",
            "Facebook - Coquitlam Condos",
            ago(15),
            "778-555-0107",
        ),
        person(
            108,
            "Harpreet",
            "Dhillon",
            "Hot Prospect",
            "Facebook - Surrey Homes with Suites",
            ago(9),
            "604-555-0108",
        ),
        person(
            109,
            "Emily",
            "Chen",
            "Active Client",
            "Facebook - Langley Townhomes",
            ago(30),
            "778-555-0109",
            tags=["Listing Alert"],
        ),
        person(
            110,
            "Mike",
            "Patel",
            "Active Client",
            "Facebook - Abbotsford Detached Homes",
            ago(45),
            "604-555-0110",
            tags=["Listings Sent"],
        ),
        person(
            111,
            "Lisa",
            "Wong",
            "Nurture",
            "Facebook - Home Value Report",
            ago(120),
            "778-555-0111",
        ),
        person(
            112,
            "Tom",
            "Anderson",
            "Lead",
            "Facebook - Maple Ridge Townhomes",
            ago(20),
            "604-555-0112",
        ),
        person(
            113,
            "Rachel",
            "Martin",
            "Lead",
            "Facebook - White Rock Condos",
            ago(10),
            "778-555-0113",
        ),
        person(114, "Chris", "Lee", "Pending", "Referral", ago(90), "604-555-0114"),
        person(
            115, "Grace", "Nguyen", "Past Client", "Referral", ago(700), "778-555-0115"
        ),
        person(
            116,
            "Brandon",
            "Singh",
            "Active Client",
            "Facebook - Langley Townhomes",
            ago(18),
            "604-555-0116",
            tags=["Listing Alert"],
        ),
        person(
            117,
            "Nina",
            "Kaur",
            "Nurture",
            "Facebook - Mission Rancher Homes",
            ago(60),
            "778-555-0117",
        ),
    ]

    notes: List[Dict[str, Any]] = [
        {
            "id": 1,
            "personId": 101,
            "created": ago(5),
            "subject": "Qualification call",
            "body": "Spoke with Priya. Renting in Willoughby, lease ends in 2 months. Wants a 3 bed townhouse in Langley/Willoughby, "
            "budget up to $950k, pre-approved with RBC. Husband also on title and wants a double garage. Sent 4 listings after the call.",
        },
        {
            "id": 2,
            "personId": 105,
            "created": ago(8),
            "subject": "Acreage search",
            "body": "Met with Aman and his wife. Looking for 2-5 acres in Maple Ridge or Mission, detached with a shop, up to $2.2M, "
            "cash from sale of their Burnaby home — need to sell our Burnaby house first. Timeline 3-6 months.",
        },
        {
            "id": 3,
            "personId": 106,
            "created": ago(6),
            "subject": "Intro call",
            "body": "Talked to Sarah briefly — interested in Chilliwack, has two kids, asked to call back later this week to go over details.",
        },
        {
            "id": 4,
            "personId": 107,
            "created": ago(4),
            "subject": "Call notes",
            "body": "Spoke with Kevin. First-time buyer, renting in Burnaby. Wants a 2 bed condo in Coquitlam near SkyTrain, "
            "budget $650k-$750k, 3-6 months. Not pre-approved yet, hasn't talked to a broker.",
        },
        {
            "id": 5,
            "personId": 108,
            "created": ago(2),
            "subject": "Qualification call",
            "body": "Had a great call with Harpreet. Needs a detached home with a legal suite (mortgage helper) in Surrey — Fleetwood or Cloverdale. "
            "5 bed, up to $1.6M, pre-approved. Living with parents, wants to move in 2-3 months.",
        },
        {
            "id": 6,
            "personId": 109,
            "created": ago(10),
            "subject": "Buyer consult",
            "body": "Met with Emily. 3 bed townhouse in Langley (Willoughby or Walnut Grove), up to $900k, pre-approved, 1-3 months. "
            "Set up listing alert and sent 5 listings.",
        },
        {
            "id": 7,
            "personId": 110,
            "created": ago(3),
            "subject": "Showing recap",
            "body": "Showed Mike 3 homes in Abbotsford. Liked the rancher on Marshall Rd but wants a bigger yard. "
            "Detached, 4 bed, up to $1.3M, pre-approved, selling nothing (renting). Timeline 2-4 months.",
        },
        {
            "id": 8,
            "personId": 111,
            "created": ago(60),
            "subject": "Nurture",
            "body": "Spoke with Lisa. Just browsing for now, maybe next year. Owns a condo in New Westminster, curious about moving to a townhouse in Burnaby.",
        },
        {
            "id": 9,
            "personId": 113,
            "created": ago(3),
            "subject": "Call",
            "body": "Rachel said she's working with another realtor already and is just on a lot of ad lists.",
        },
        {
            "id": 10,
            "personId": 115,
            "created": ago(100),
            "subject": "Anniversary",
            "body": "Called Grace for her 2-year home anniversary. Happy in the South Surrey house.",
        },
        {
            "id": 11,
            "personId": 116,
            "created": ago(2),
            "subject": "Check-in",
            "body": "Spoke with Brandon. Still looking for a 3 bed townhouse in Langley, up to $875k, pre-approved, 3-6 months. Liked two from the alert.",
        },
        {
            "id": 12,
            "personId": 117,
            "created": ago(5),
            "subject": "Nurture call",
            "body": "Talked to Nina. Wants a rancher in Mission in about 12 months after her retirement. Budget around $900k. Not in a rush.",
        },
        {
            "id": 13,
            "personId": 112,
            "created": ago(19),
            "subject": "Attempt",
            "body": "Left voicemail. Didn't speak to him.",
        },
    ]

    calls: List[Dict[str, Any]] = [
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
            "personId": 104,
            "created": ago(3),
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
            "created": ago(6),
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
            "created": ago(60),
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
            "created": ago(100),
            "isIncoming": 0,
            "outcome": "Interested",
            "duration": 600,
        },
        {
            "id": 215,
            "personId": 116,
            "created": ago(2),
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
    ] + [
        {
            "id": 220 + i,
            "personId": 112,
            "created": ago(19 - i * 2.5),
            "isIncoming": 0,
            "outcome": "No Answer",
            "duration": 0,
        }
        for i in range(4)
    ]

    texts: List[Dict[str, Any]] = [
        {
            "id": 301,
            "personId": 101,
            "created": ago(5),
            "isIncoming": 0,
            "message": "Great chatting Priya! Here are 4 townhomes in Willoughby that fit — let me know which ones stand out.",
        },
        {
            "id": 302,
            "personId": 101,
            "created": ago(hours=18),
            "isIncoming": 1,
            "message": "Hi Karan, is the end unit on 208 St still available? Could we see it this weekend?",
        },
        {
            "id": 303,
            "personId": 104,
            "created": ago(3),
            "isIncoming": 0,
            "message": "Hi Daniel, it's Karan — thanks for grabbing the first-time buyer guide. Any questions I can help with?",
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
            "personId": 111,
            "created": ago(25),
            "isIncoming": 0,
            "message": "Hi Lisa, quick New West market update attached — let me know if you'd like a value estimate on your condo.",
        },
        {
            "id": 307,
            "personId": 106,
            "created": ago(6),
            "isIncoming": 1,
            "message": "Maybe something under 700k? Will know more after we talk to the bank",
        },
    ] + [
        {
            "id": 320 + i,
            "personId": 112,
            "created": ago(18 - i * 2.5),
            "isIncoming": 0,
            "message": "Hi Tom, it's Karan following up on the Maple Ridge townhomes. When's a good time for a quick call?",
        }
        for i in range(3)
    ]

    tasks: List[Dict[str, Any]] = [
        {
            "id": 401,
            "personId": 101,
            "name": "Send Priya strata docs for 208 St unit",
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
            "name": "Send Kevin mortgage broker contacts",
            "type": "Follow Up",
            "dueDate": due(-3),
            "isCompleted": 0,
        },
        {
            "id": 404,
            "personId": 110,
            "name": "Follow up after Abbotsford showings",
            "type": "Call",
            "dueDate": due(0),
            "isCompleted": 0,
        },
        {
            "id": 405,
            "personId": 109,
            "name": "Check new Willoughby listings for Emily",
            "type": "Follow Up",
            "dueDate": due(-1),
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
            "name": "Order open house signs for Sunday",
            "type": "Follow Up",
            "dueDate": due(-1),
            "isCompleted": 0,
        },
        {
            "id": 409,
            "personId": 114,
            "name": "Confirm subject removal with lender",
            "type": "Follow Up",
            "dueDate": due(-1),
            "isCompleted": 0,
        },
    ]

    appointments: List[Dict[str, Any]] = [
        {
            "id": 501,
            "title": "Showing - Maple Ridge acreages",
            "start": ahead(hours=27),
            "end": ahead(hours=30),
            "location": "256 St, Maple Ridge",
            "invitees": [{"personId": 105, "name": "Aman Gill"}],
        },
        {
            "id": 502,
            "title": "Showing - 3 homes in Abbotsford",
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
                "street": "7890 202 St #14",
                "city": "Langley",
                "price": 879000,
            },
        },
        {
            "id": 602,
            "personId": 109,
            "type": "Saved Property",
            "created": ago(1),
            "property": {
                "street": "7890 202 St #14",
                "city": "Langley",
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
