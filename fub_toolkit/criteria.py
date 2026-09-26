"""
Buyer-criteria extraction.

Reads the free text that accumulates on a lead (Facebook lead-form answers in
``background``, custom fields, agent notes, call notes and the lead's own
texts) and pulls out structured buyer criteria. Sources are processed oldest
to newest so newer information overrides older information.

This is deliberately rule-based and transparent: every extracted value keeps
the snippet it came from so you can check it before relying on it.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .models import Lead

# Longest names first so "North Vancouver" wins over "Vancouver".
AREAS: Dict[str, str] = {
    "north vancouver": "North Vancouver",
    "north van": "North Vancouver",
    "west vancouver": "West Vancouver",
    "west van": "West Vancouver",
    "east vancouver": "East Vancouver",
    "east van": "East Vancouver",
    "vancouver": "Vancouver",
    "port coquitlam": "Port Coquitlam",
    "poco": "Port Coquitlam",
    "port moody": "Port Moody",
    "burke mountain": "Coquitlam (Burke Mountain)",
    "coquitlam": "Coquitlam",
    "tri-cities": "Tri-Cities",
    "tri cities": "Tri-Cities",
    "new westminster": "New Westminster",
    "new west": "New Westminster",
    "burnaby": "Burnaby",
    "richmond": "Richmond",
    "north delta": "North Delta",
    "tsawwassen": "Tsawwassen",
    "ladner": "Ladner",
    "delta": "Delta",
    "south surrey": "South Surrey",
    "white rock": "White Rock",
    "cloverdale": "Cloverdale",
    "fleetwood": "Fleetwood",
    "newton": "Newton",
    "panorama": "Panorama",
    "sullivan": "Sullivan",
    "guildford": "Guildford",
    "surrey": "Surrey",
    "fort langley": "Fort Langley",
    "walnut grove": "Walnut Grove",
    "willoughby": "Willoughby",
    "murrayville": "Murrayville",
    "brookswood": "Brookswood",
    "aldergrove": "Aldergrove",
    "langley": "Langley",
    "abbotsford": "Abbotsford",
    "abby": "Abbotsford",
    "mission": "Mission",
    "promontory": "Promontory",
    "sardis": "Sardis",
    "chilliwack": "Chilliwack",
    "maple ridge": "Maple Ridge",
    "pitt meadows": "Pitt Meadows",
    "agassiz": "Agassiz",
    "harrison": "Harrison",
    "hope": "Hope",
}

PROPERTY_TYPES: List[Tuple[str, str]] = [
    (r"half[- ]duplex|duplex", "Duplex / Half duplex"),
    (r"town ?houses?|town ?homes?|\bth\b", "Townhouse"),
    (r"condos?|apartments?|\bapt\b", "Condo / Apartment"),
    (r"acreages?|\bacres?\b|hobby farm|\bfarm\b", "Acreage"),
    (r"rancher|detached|single[- ]family|\bsfh\b|\bhouse\b", "Detached"),
    (r"triplex|fourplex|4-plex|multi[- ]family|multiplex", "Multi-family"),
    (r"\bindustrial\b|warehouse", "Industrial"),
    (r"\bcommercial\b|retail unit|office space", "Commercial"),
    (r"\bvacant land\b|building lot|\blot\b(?! of)", "Land / Lot"),
]

MUST_HAVES: List[Tuple[str, str]] = [
    (
        r"mortgage helper|basement suite|legal suite|\bsuite\b",
        "Suite / mortgage helper",
    ),
    (r"double garage", "Double garage"),
    (r"\bgarage\b", "Garage"),
    (r"\bshop\b|workshop", "Shop"),
    (r"rv parking|room for (?:an )?rv|\brv\b", "RV parking"),
    (r"\byard\b|backyard|fenced", "Yard"),
    (r"\bview\b", "View"),
    (r"catchment|close to (?:a )?school|near (?:a )?school", "School catchment"),
    (r"skytrain|transit", "Near transit"),
    (r"no strata|freehold", "No strata"),
    (r"rentals? allowed|can rent (?:it )?out", "Rentals allowed"),
    (r"\bpets?\b|\bdogs?\b|\bcats?\b", "Pet friendly"),
    (r"\brancher\b|one level|single level", "One level (rancher)"),
]

FLAG_PATTERNS: List[Tuple[str, str]] = [
    (
        r"working with (?:another|an?other|a) (?:agent|realtor)|have (?:an|a) (?:agent|realtor)|already have (?:an|a) (?:agent|realtor)",
        "Working with another agent",
    ),
    (r"already bought|we bought|found a place|purchased already", "Already bought"),
    (
        r"stop (?:texting|calling|messaging)|remove me|unsubscribe|do not contact|don'?t contact",
        "Do not contact",
    ),
    (r"not interested", "Not interested"),
    (r"wrong number|bad number", "Bad number"),
    (r"just (?:browsing|looking)|curious", "Just browsing"),
]

MOTIVATIONS: List[Tuple[str, str]] = [
    (r"baby|growing family|more space|need(?:s)? more room", "Needs more space"),
    (r"downsiz", "Downsizing"),
    (
        r"lease (?:is )?(?:up|ends|ending)|landlord (?:is )?selling|rent (?:is )?(?:too high|going up)",
        "Rental situation changing",
    ),
    (
        r"closer to (?:work|family|school)|new job|relocat|moving (?:here|from)",
        "Relocation / closer to work or family",
    ),
    (r"invest|rental income|cash ?flow", "Investment"),
    (r"divorce|separat", "Life change"),
    (r"retir", "Retirement"),
]

QUESTIONS: Dict[str, str] = {
    "areas": "Which areas are you focused on — and are you open to anywhere nearby?",
    "property_types": "What type of home are you after — detached, townhouse or condo?",
    "budget": "What price range are you comfortable with?",
    "timeline": "When would you ideally like to be moved in?",
    "financing": "Have you been pre-approved yet, or would an intro to a mortgage broker help?",
    "situation": "Are you renting right now, or would you need to sell first?",
    "bedrooms": "How many bedrooms do you need?",
    "motivation": "What's prompting the move?",
}


LABELS: Dict[str, str] = {
    "areas": "area",
    "property_types": "property type",
    "budget": "budget",
    "timeline": "timeline",
    "financing": "financing",
    "situation": "current housing",
    "bedrooms": "bedrooms",
    "motivation": "motivation",
}


@dataclass
class BuyerCriteria:
    areas: List[str] = field(default_factory=list)
    property_types: List[str] = field(default_factory=list)
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    timeline_months: Optional[int] = None
    timeline_label: str = ""
    pre_approved: Optional[bool] = None
    cash_buyer: bool = False
    situation: List[str] = field(default_factory=list)
    current_areas: List[str] = field(default_factory=list)
    must_haves: List[str] = field(default_factory=list)
    motivation: List[str] = field(default_factory=list)
    decision_makers: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    evidence: Dict[str, str] = field(default_factory=dict)

    @property
    def budget_label(self) -> str:
        if self.min_price and self.max_price:
            return f"{fmt_price(self.min_price)}–{fmt_price(self.max_price)}"
        if self.max_price:
            return f"up to {fmt_price(self.max_price)}"
        if self.min_price:
            return f"from {fmt_price(self.min_price)}"
        return ""

    @property
    def financing_label(self) -> str:
        if self.cash_buyer:
            return "cash"
        if self.pre_approved is True:
            return "pre-approved"
        if self.pre_approved is False:
            return "NOT pre-approved"
        return ""

    def missing(self) -> List[str]:
        """Key qualification items still unknown, in the order to ask them."""
        gaps = []
        if not self.areas:
            gaps.append("areas")
        if not self.property_types:
            gaps.append("property_types")
        if not self.max_price:
            gaps.append("budget")
        if self.timeline_months is None:
            gaps.append("timeline")
        if self.pre_approved is None and not self.cash_buyer:
            gaps.append("financing")
        if not self.situation:
            gaps.append("situation")
        if self.bedrooms is None and not any(
            t in self.property_types for t in ("Land / Lot", "Commercial", "Industrial")
        ):
            gaps.append("bedrooms")
        if not self.motivation:
            gaps.append("motivation")
        return gaps

    def missing_labels(self) -> List[str]:
        return [LABELS[m] for m in self.missing()]

    def missing_questions(self, limit: int = 3) -> List[str]:
        return [QUESTIONS[m] for m in self.missing()[:limit]]

    @property
    def is_qualified(self) -> bool:
        """Enough to send targeted listings: area, type, budget and timeline known."""
        return not {"areas", "property_types", "budget", "timeline"} & set(
            self.missing()
        )

    def one_line(self) -> str:
        parts = []
        if self.property_types:
            parts.append("/".join(self.property_types))
        if self.areas:
            parts.append(", ".join(self.areas))
        if self.bedrooms:
            parts.append(f"{self.bedrooms}+ bed")
        if self.budget_label:
            parts.append(self.budget_label)
        if self.timeline_label:
            parts.append(self.timeline_label)
        if self.financing_label:
            parts.append(self.financing_label)
        if self.must_haves:
            parts.append("must: " + ", ".join(self.must_haves))
        return " · ".join(parts) if parts else "No criteria captured yet"


def fmt_price(value: int) -> str:
    if value >= 1_000_000:
        text = f"{value / 1_000_000:.2f}".rstrip("0").rstrip(".")
        return f"${text}M"
    return f"${round(value / 1000):,}k"


_MONEY = r"\$?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s*(k|m|mil|million|thousand)\b)?"


def _to_dollars(
    number: str, unit: Optional[str], unit_hint: Optional[str] = None
) -> Optional[int]:
    unit = (unit or unit_hint or "").lower()
    value = float(number.replace(",", ""))
    if unit in {"m", "mil", "million"}:
        value *= 1_000_000
    elif unit in {"k", "thousand"}:
        value *= 1_000
    elif value < 10_000:
        return None  # bare small numbers are not prices ("3 bed", "2 kids")
    value = int(round(value))
    return value if 100_000 <= value <= 30_000_000 else None


def parse_budget(text: str) -> Tuple[Optional[int], Optional[int]]:
    t = text.lower()
    rng = re.search(rf"(?:between\s+)?{_MONEY}\s*(?:-|–|to|and)\s*{_MONEY}", t)
    if rng:
        hi_unit = rng.group(4)
        lo = _to_dollars(rng.group(1), rng.group(2), hi_unit)
        hi = _to_dollars(rng.group(3), hi_unit, rng.group(2))
        if lo and hi and lo < hi:
            return lo, hi
    cap = re.search(
        rf"(?:under|up to|max(?:imum)?|below|no more than|budget(?: is| of)?|around|approved (?:for|up to)|about|less than)\s*:?\s*{_MONEY}",
        t,
    )
    if cap:
        val = _to_dollars(cap.group(1), cap.group(2))
        if val:
            return None, val
    loose = re.search(
        r"\$\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s*(k|m|mil|million)\b)?", t
    ) or re.search(r"\b(\d+(?:\.\d+)?)\s*(k|m|mil|million)\b", t)
    if loose:
        val = _to_dollars(loose.group(1), loose.group(2))
        if val:
            return None, val
    return None, None


_SEASON_MONTH = {"spring": 4, "summer": 7, "fall": 10, "autumn": 10, "winter": 1}


def parse_timeline(text: str, as_of: datetime) -> Tuple[Optional[int], str]:
    t = text.lower()
    if re.search(r"\basap\b|right away|immediately|as soon as possible", t):
        return 1, "ASAP"
    m = re.search(r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*months?", t)
    if m:
        return int(m.group(2)), f"{m.group(1)}–{m.group(2)} months"
    m = re.search(r"(\d+)\s*\+\s*months?|more than (\d+) months", t)
    if m:
        n = int(m.group(1) or m.group(2))
        return n, f"{n}+ months"
    m = re.search(r"(?:in|within|next)\s+(\d+)\s*months?", t) or re.search(
        r"(\d+)\s*months?", t
    )
    if m:
        n = int(m.group(1))
        return n, f"~{n} months"
    if re.search(r"next month|within (?:a|the) month|this month", t):
        return 1, "within a month"
    if re.search(r"within (?:a|the next) year|next year|12 months", t):
        return 12, "within a year"
    m = re.search(r"(?:this|next|by|in the)\s+(spring|summer|fall|autumn|winter)", t)
    if m:
        target = _SEASON_MONTH[m.group(1)]
        months = (target - as_of.month) % 12 or 12
        return months, m.group(1).capitalize()
    if re.search(r"just (?:browsing|looking)|no rush|not in a rush|down the road", t):
        return 12, "long-term / browsing"
    return None, ""


_FORM_QA = re.compile(r"q:\s*(?P<q>.*?)\s*a:\s*(?P<a>[^\n]*)", re.I)


def normalize_form(text: str) -> str:
    """Rewrite lead-form 'Q: ... A: ...' pairs as 'topic: answer'.

    Facebook lead forms arrive in FUB as question/answer text. The question
    itself ("Are you pre-approved?") must not be read as the answer.
    """

    def repl(m: "re.Match[str]") -> str:
        q, a = m.group("q").lower(), m.group("a").strip()
        if re.search(r"pre-?\s?approv|mortgage|financ", q):
            return f"pre-approved: {a}"
        if re.search(r"when|timeline|timeframe|how soon", q):
            return f"timeline: {a}"
        if re.search(r"budget|price", q):
            return f"budget: {a}"
        if re.search(r"bed", q):
            return f"bedrooms: {a}"
        return a

    return _FORM_QA.sub(repl, text)


def parse_financing(text: str) -> Tuple[Optional[bool], bool]:
    t = text.lower()
    answer = re.search(
        r"pre-approved:\s*(yes|no|not yet|working on it|in progress)\b", t
    )
    if answer:
        return answer.group(1) == "yes", False
    cash = bool(re.search(r"\bcash (?:buyer|purchase)|paying cash|all cash", t))
    if re.search(
        r"not (?:yet )?pre-?\s?approved|no pre-?\s?approval|need(?:s)? to get pre-?\s?approved|haven'?t (?:been )?pre-?\s?approved|haven'?t talked to (?:a|the) (?:lender|broker|bank)|pre-?\s?approved\??\s*:?\s*no",
        t,
    ):
        return False, cash
    if re.search(
        r"pre-?\s?approv(?:ed|al (?:done|in place))|approved (?:for|up to)|pre-?\s?approved\??\s*:?\s*yes",
        t,
    ):
        return True, cash
    return None, cash


_NEGATION = re.compile(
    r"\b(?:not|no|isn'?t|aren'?t|never|without)\b[\w\s']{0,12}$|n'?t\s+$"
)


def _collect(
    patterns: List[Tuple[str, str]], text: str, negatable: bool = False
) -> List[str]:
    """Labels whose pattern appears in ``text``.

    With ``negatable`` a match preceded by a negation ("not working with another
    agent", "said no to ...") is ignored.
    """
    t = text.lower()
    found: List[str] = []
    for pattern, label in patterns:
        for match in re.finditer(pattern, t):
            before = t[max(0, match.start() - 20) : match.start()]
            if negatable and _NEGATION.search(before):
                continue
            if label not in found:
                found.append(label)
            break
    return found


_AREA_RE = re.compile(
    r"\b("
    + "|".join(re.escape(k) for k in sorted(AREAS, key=len, reverse=True))
    + r")\b"
)
_CURRENT_HOME = re.compile(
    r"(?:renting|rent|living|live|lives|owns?|currently|moving from|sale of|sell|selling)\b(?:(?!want|looking|buy|search)[^.;])*$"
)


def _areas(text: str) -> Tuple[List[str], List[str]]:
    """Return (areas they want, areas they live in now), in order of mention."""
    t = text.lower()
    wanted: List[str] = []
    current: List[str] = []
    for m in _AREA_RE.finditer(t):
        label = AREAS[m.group(1)]
        before = t[max(0, m.start() - 35) : m.start()]
        target = current if _CURRENT_HOME.search(before) else wanted
        if label not in target:
            target.append(label)
    return wanted, [c for c in current if c not in wanted]


def _types(text: str) -> List[str]:
    t = text.lower()
    found: List[str] = []
    for pattern, label in PROPERTY_TYPES:
        if re.search(pattern, t):
            if label not in found:
                found.append(label)
            t = re.sub(pattern, " ", t)
    return found


def _snippet(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _sources(lead: Lead) -> List[Tuple[datetime, str, str]]:
    """All free text on a lead as (timestamp, label, text), oldest first."""
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    created = lead.created or epoch
    items: List[Tuple[datetime, str, str]] = []
    if lead.background:
        items.append((created, "lead form", lead.background))
    for key, value in lead.custom.items():
        label = re.sub(r"(?<!^)(?=[A-Z])", " ", key[len("custom") :]).strip()
        items.append((created, "lead form", f"{label}: {value}"))
    for note in lead.notes:
        items.append((note.created or created, "note", f"{note.subject}. {note.body}"))
    for ix in lead.interactions:
        if not ix.text:
            continue
        if ix.channel == "call":
            items.append((ix.created or created, "call note", ix.text))
        elif ix.incoming:
            items.append((ix.created or created, "their text", ix.text))
    items.sort(key=lambda x: x[0])
    return items


def extract_criteria(lead: Lead, as_of: datetime) -> BuyerCriteria:
    """Extract buyer criteria from everything recorded on ``lead``."""
    c = BuyerCriteria()

    def cite(key: str, when: datetime, label: str, text: str) -> None:
        c.evidence[key] = (
            f"{label} {when.astimezone(as_of.tzinfo).strftime('%b %d')}: \"{_snippet(text)}\""
        )

    for when, label, text in _sources(lead):
        text = normalize_form(text)
        lower = text.lower()
        areas, current = _areas(text)
        if areas:
            c.areas = areas
            cite("areas", when, label, text)
        for area in current:
            if area not in c.current_areas:
                c.current_areas.append(area)
        types = _types(text)
        if types:
            c.property_types = types
            cite("property_types", when, label, text)
        lo, hi = parse_budget(text)
        if hi:
            c.min_price, c.max_price = lo, hi
            cite("budget", when, label, text)
        beds = re.search(
            r"(\d)\s*\+?\s*(?:bed(?:room)?s?|bdrm?s?|br)\b", lower
        ) or re.search(r"bed(?:room)?s?\??\s*:\s*(\d)", lower)
        if beds:
            c.bedrooms = int(beds.group(1))
        baths = re.search(r"(\d(?:\.5)?)\s*\+?\s*(?:bath(?:room)?s?|ba)\b", lower)
        if baths:
            c.bathrooms = float(baths.group(1))
        months, tl_label = parse_timeline(text, as_of)
        if months is not None:
            c.timeline_months, c.timeline_label = months, tl_label
            cite("timeline", when, label, text)
        approved, cash = parse_financing(text)
        if approved is not None:
            c.pre_approved = approved
            cite("financing", when, label, text)
        if cash:
            c.cash_buyer = True
        for item in _collect(MUST_HAVES, text):
            if item not in c.must_haves:
                c.must_haves.append(item)
        for item in _collect(MOTIVATIONS, text):
            if item not in c.motivation:
                c.motivation.append(item)
        for item in _collect(FLAG_PATTERNS, text, negatable=True):
            if item not in c.flags:
                c.flags.append(item)
        if (
            re.search(r"\brent(?:ing)?\b|\blease\b|landlord", lower)
            and "Renting" not in c.situation
        ):
            c.situation.append("Renting")
        if (
            re.search(
                r"need(?:s)? to sell|sell (?:our|my|their) (?:place|home|house|condo|townhouse)|selling (?:our|my) |have (?:a|our) place to sell",
                lower,
            )
            and "Needs to sell first" not in c.situation
        ):
            c.situation.append("Needs to sell first")
        if (
            re.search(r"first[- ]time (?:home ?)?buyer|\bfthb\b|first home", lower)
            and "First-time buyer" not in c.situation
        ):
            c.situation.append("First-time buyer")
        if (
            re.search(r"living with (?:parents|family)|with (?:my|our) parents", lower)
            and "Living with family" not in c.situation
        ):
            c.situation.append("Living with family")
        people_text = re.sub(
            r"living with (?:my |our |his |her |their )?parents", " ", lower
        )
        for who in re.findall(
            r"\b(wife|husband|partner|spouse|parents|fianc[eé]e?|co-?signer)\b",
            people_text,
        ):
            who = who.capitalize()
            if who not in c.decision_makers:
                c.decision_makers.append(who)

    if "Double garage" in c.must_haves and "Garage" in c.must_haves:
        c.must_haves.remove("Garage")
    if c.timeline_months is None and "Just browsing" in c.flags:
        c.timeline_months, c.timeline_label = 12, "long-term / browsing"
    return c
