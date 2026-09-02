"""Compare uploaded Excel values with extracted LinkedIn profile fields.

Extraction SUCCESS/FAILED is independent of verification VERIFIED/MISMATCH.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.services.excel_service import _normalize_header

VERIFY_NOT_VERIFIED = "NOT_VERIFIED"
VERIFY_VERIFIED = "VERIFIED"
VERIFY_MISMATCH = "MISMATCH"
VERIFY_REVIEW = "REVIEW"
VERIFY_RESOLVED = "RESOLVED"
VERIFY_ALREADY_EXISTS = "ALREADY_EXISTS"
VERIFY_NEEDS_REVIEW = "NEEDS_REVIEW"  # alias used in UI filters; stored as REVIEW/MISMATCH

_COMPANY_SUFFIXES = (
    "incorporated",
    "corporation",
    "company",
    "limited",
    "llc",
    "ltd",
    "inc",
    "corp",
    "gmbh",
    "plc",
    "co",
    "lp",
    "llp",
    "pty",
    "pvt",
    "private",
)

_LOCATION_NOISE = {
    "usa",
    "us",
    "unitedstates",
    "unitedstatesofamerica",
    "uk",
    "unitedkingdom",
    "india",
    "canada",
    "australia",
    "germany",
    "france",
    "area",
    "metro",
    "greater",
    "region",
    "county",
    # Full US state / territory names (abbrs handled via _US_STATE_ABBR).
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "wisconsin",
    "wyoming",
}

# Multi-word country / region phrases removed before tokenizing (city normalize).
_LOCATION_PHRASES = (
    "united states of america",
    "united states",
    "united kingdom",
    "new hampshire",
    "new jersey",
    "new mexico",
    "north carolina",
    "north dakota",
    "rhode island",
    "south carolina",
    "south dakota",
    "west virginia",
    "district of columbia",
)

# Canonical country codes for company-location country-wise matching.
_COUNTRY_CANON = {
    "unitedstates": "us",
    "unitedstatesofamerica": "us",
    "usa": "us",
    "us": "us",
    "america": "us",
    "unitedkingdom": "uk",
    "uk": "uk",
    "greatbritain": "uk",
    "britain": "uk",
    "england": "uk",
    "scotland": "uk",
    "wales": "uk",
    "india": "in",
    "bharat": "in",
    "canada": "ca",
    "australia": "au",
    "germany": "de",
    "france": "fr",
    "singapore": "sg",
    "uae": "ae",
    "unitedarabemirates": "ae",
    "netherlands": "nl",
    "ireland": "ie",
    "brazil": "br",
    "mexico": "mx",
    "japan": "jp",
    "china": "cn",
    "southkorea": "kr",
    "korea": "kr",
    "spain": "es",
    "italy": "it",
    "sweden": "se",
    "switzerland": "ch",
    "poland": "pl",
    "philippines": "ph",
    "indonesia": "id",
    "malaysia": "my",
    "thailand": "th",
    "vietnam": "vn",
    "southafrica": "za",
    "newzealand": "nz",
    "israel": "il",
    "pakistan": "pk",
    "bangladesh": "bd",
    "nigeria": "ng",
    "kenya": "ke",
    "argentina": "ar",
    "chile": "cl",
    "colombia": "co",
    "peru": "pe",
    "portugal": "pt",
    "belgium": "be",
    "austria": "at",
    "denmark": "dk",
    "norway": "no",
    "finland": "fi",
    "hongkong": "hk",
    "taiwan": "tw",
}

_COUNTRY_PHRASES = tuple(
    sorted(
        (
            "united states of america",
            "united states",
            "united kingdom",
            "united arab emirates",
            "south korea",
            "south africa",
            "new zealand",
            "hong kong",
            "great britain",
            *{c for c in _COUNTRY_CANON if len(c) > 3 and c not in {"usa", "uae"}},
        ),
        key=len,
        reverse=True,
    )
)

_US_STATE_ABBR = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il",
    "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt",
    "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri",
    "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}

_US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "ohio", "oklahoma", "oregon",
    "pennsylvania", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "wisconsin", "wyoming",
}

# Honorifics and post-nominals that carry no identity signal.
_NAME_PREFIXES = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir", "madam"}
_NAME_SUFFIXES = {
    "jr", "sr", "ii", "iii", "iv", "phd", "md", "mba", "cpa", "esq", "cfa",
    "pmp", "msc", "bsc", "ma", "ba", "do", "dds", "rn", "jd", "cma", "cfp",
}

# Filler words that differ freely between a spreadsheet title and a LinkedIn headline.
_TITLE_STOPWORDS = {"and", "of", "the", "at", "for", "in", "to", "a", "an", "amp"}

# Abbreviations expanded so "VP" and "Vice President" compare as one token stream.
_TITLE_SYNONYMS = {
    "vp": "vicepresident",
    "svp": "seniorvicepresident",
    "evp": "executivevicepresident",
    "avp": "assistantvicepresident",
    "ceo": "chiefexecutiveofficer",
    "cfo": "chieffinancialofficer",
    "coo": "chiefoperatingofficer",
    "cto": "chieftechnologyofficer",
    "cio": "chiefinformationofficer",
    "cmo": "chiefmarketingofficer",
    "chro": "chiefhumanresourcesofficer",
    "sr": "senior",
    "snr": "senior",
    "jr": "junior",
    "mgr": "manager",
    "mgmt": "management",
    "dir": "director",
    "asst": "assistant",
    "assoc": "associate",
    "exec": "executive",
    "pres": "president",
    "eng": "engineer",
    "engg": "engineering",
    "dev": "developer",
    "ops": "operations",
    "admin": "administrator",
    "hr": "humanresources",
    "it": "informationtechnology",
}

_COMPANY_STOPWORDS = {"and", "the", "of", "amp"}

NAME_ALIASES = {"name", "fullname", "full_name", "originalname", "contactname"}
DESIGNATION_ALIASES = {
    "designation",
    "jobtitle",
    "title",
    "position",
    "role",
    "job",
}
EMAIL_ALIASES = {
    "email",
    "emailaddress",
    "email_address",
    "workemail",
    "work_email",
    "contactemail",
    "contact_email",
    "e_mail",
}
COMPANY_ALIASES = {
    "company",
    "organization",
    "organisation",
    "employer",
    "companyname",
    "org",
}
# Explicit person-location column names (not City/State/Country parts).
PERSON_LOCATION_ALIASES = {
    "location",
    "personlocation",
    "personcity",
    "geo",
    "locality",
    "region",
}
PERSON_CITY_ALIASES = {"city"}
PERSON_STATE_ALIASES = {"state", "province"}
PERSON_COUNTRY_ALIASES = {"country"}

COMPANY_CITY_ALIASES = {"companycity"}
COMPANY_STATE_ALIASES = {"companystate"}
COMPANY_COUNTRY_ALIASES = {"companycountry"}
COMPANY_ADDRESS_ALIASES = {"companyaddress", "address"}

# Back-compat alias set used by older call sites / docs.
LOCATION_ALIASES = PERSON_LOCATION_ALIASES | PERSON_CITY_ALIASES | {"geo", "address", "locality", "region"}


@dataclass
class VerificationResult:
    status: str
    score: int
    compared: int
    matched: int
    reason: str
    name_match: bool | None
    designation_match: bool | None
    company_match: bool | None
    location_match: bool | None
    company_location_match: bool | None
    original_name: str | None
    original_designation: str | None
    original_company: str | None
    original_location: str | None
    original_company_location: str | None


def _strip_punct(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = _strip_punct(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def values_equivalent(left: Any, right: Any) -> bool:
    """True when two raw cells say the same thing.

    Ignores case, punctuation, accents and word order, so "Macon, Mississippi,
    United States" on both sides can never be reported as a difference.
    """
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return sorted(a.split()) == sorted(b.split())


def normalize_company(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    tokens = [t for t in text.split() if t not in _COMPANY_STOPWORDS]
    while tokens and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def normalize_designation(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    tokens = [
        _TITLE_SYNONYMS.get(token, token)
        for token in text.split()
        if token not in _TITLE_STOPWORDS
    ]
    return " ".join(tokens)


def normalize_location(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    # Strip multi-word country/state phrases before token split ("United States" → gone).
    for phrase in _LOCATION_PHRASES:
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = [t for t in re.split(r"[\s,]+", text) if t]
    kept: list[str] = []
    for token in tokens:
        compact = re.sub(r"[^a-z0-9]", "", token)
        if not compact or compact.isdigit():
            continue
        if compact in _LOCATION_NOISE or compact in _US_STATE_ABBR:
            continue
        kept.append(compact)
    if kept:
        return " ".join(kept)
    # Fallback when the whole value was noise (e.g. country-only cell).
    return re.sub(r"[^a-z0-9]", "", normalize_text(value))


def normalize_name(value: Any) -> str:
    """Drop honorifics, post-nominals and middle initials before comparing."""
    text = normalize_text(value)
    if not text:
        return ""
    tokens = [t for t in text.split() if t not in _NAME_PREFIXES]
    while tokens and tokens[-1] in _NAME_SUFFIXES:
        tokens.pop()
    core = [t for t in tokens if len(t) > 1]
    return " ".join(core or tokens)


def _pick_from_row(source: dict[str, Any] | None, aliases: set[str]) -> str | None:
    if not isinstance(source, dict):
        return None
    for key, value in source.items():
        if _normalize_header(str(key)) in aliases:
            text = str(value).strip() if value is not None else ""
            if text and text.lower() not in {"none", "nan", "null", "n/a", "-"}:
                return text
    return None


def _compose_location_parts(*parts: str | None) -> str | None:
    cleaned = [str(p).strip() for p in parts if p and str(p).strip()]
    if not cleaned:
        return None
    # Drop duplicates while preserving order (City + Address both saying Columbus).
    seen: set[str] = set()
    unique: list[str] = []
    for part in cleaned:
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
    return ", ".join(unique)


def _person_location_from_row(source_row: dict[str, Any] | None) -> str | None:
    explicit = _pick_from_row(source_row, PERSON_LOCATION_ALIASES)
    if explicit:
        return explicit
    return _compose_location_parts(
        _pick_from_row(source_row, PERSON_CITY_ALIASES),
        _pick_from_row(source_row, PERSON_STATE_ALIASES),
        _pick_from_row(source_row, PERSON_COUNTRY_ALIASES),
    )


def _company_location_from_row(source_row: dict[str, Any] | None) -> str | None:
    composed = _compose_location_parts(
        _pick_from_row(source_row, COMPANY_CITY_ALIASES),
        _pick_from_row(source_row, COMPANY_STATE_ALIASES),
        _pick_from_row(source_row, COMPANY_COUNTRY_ALIASES),
    )
    if composed:
        return composed
    return _pick_from_row(source_row, COMPANY_ADDRESS_ALIASES)


def original_fields(source_row: dict[str, Any] | None) -> dict[str, str | None]:
    fields = {
        "name": _pick_from_row(source_row, NAME_ALIASES),
        "email": _pick_from_row(source_row, EMAIL_ALIASES),
        "designation": _pick_from_row(source_row, DESIGNATION_ALIASES),
        "company": _pick_from_row(source_row, COMPANY_ALIASES),
        "location": _person_location_from_row(source_row),
        "company_location": _company_location_from_row(source_row),
    }
    if not fields["name"] and isinstance(source_row, dict):
        first = _pick_from_row(source_row, {"firstname", "first", "givenname"})
        last = _pick_from_row(source_row, {"lastname", "last", "surname", "familyname"})
        combined = " ".join(p for p in (first, last) if p).strip()
        fields["name"] = combined or None
    return fields


def _compare_generic(original: str | None, extracted: str | None, normalizer) -> bool | None:
    if not original or not str(original).strip():
        return None
    if values_equivalent(original, extracted):
        return True
    left = normalizer(original)
    right = normalizer(extracted)
    if not left:
        return None
    if not right:
        return False
    return left == right


def _compare_name(original: str | None, extracted: str | None) -> bool | None:
    if not original or not str(original).strip():
        return None
    if values_equivalent(original, extracted):
        return True
    left = normalize_name(original)
    right = normalize_name(extracted)
    if not left:
        return None
    if not right:
        return False
    if left == right:
        return True
    left_tokens = left.split()
    right_tokens = right.split()
    if sorted(left_tokens) == sorted(right_tokens):
        return True
    # Same first and last name, extra middle names on one side only.
    if len(left_tokens) > 1 and len(right_tokens) > 1:
        if left_tokens[0] == right_tokens[0] and left_tokens[-1] == right_tokens[-1]:
            return True
    return False


def _compare_designation(original: str | None, extracted: str | None) -> bool | None:
    if not original or not str(original).strip():
        return None
    if values_equivalent(original, extracted):
        return True
    left = normalize_designation(original)
    right = normalize_designation(extracted)
    if not left:
        return None
    if not right:
        return False
    if left == right:
        return True
    # "VP Sales" expands to the same stream as "Vice President Sales".
    if left.replace(" ", "") == right.replace(" ", ""):
        return True
    return sorted(left.split()) == sorted(right.split())


def locations_compatible(left: str | None, right: str | None) -> bool | None:
    """True when locations share a meaningful city/place token after noise strip."""
    if not left or not str(left).strip() or not right or not str(right).strip():
        return None
    a = normalize_location(left)
    b = normalize_location(right)
    if not a or not b:
        return None
    if a == b:
        return True
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if a_tokens & b_tokens:
        return True
    # Contained phrase (e.g. "columbus mississippi" in longer address normalize).
    compact_a = a.replace(" ", "")
    compact_b = b.replace(" ", "")
    if len(compact_a) >= 4 and (compact_a in compact_b or compact_b in compact_a):
        return True
    return False


def normalize_country(value: Any) -> str:
    """Map a country label to a short canonical code (us, uk, in, …)."""
    if value is None:
        return ""
    text = normalize_text(value)
    if not text:
        return ""
    compact = re.sub(r"[^a-z0-9]", "", text)
    if compact in _COUNTRY_CANON:
        return _COUNTRY_CANON[compact]
    for phrase in _COUNTRY_PHRASES:
        phrase_compact = re.sub(r"[^a-z0-9]", "", phrase)
        if phrase in text or (phrase_compact and phrase_compact in compact):
            return _COUNTRY_CANON.get(phrase_compact, phrase_compact)
    return compact


def country_from_location_text(value: Any) -> str:
    """Infer country code from a free-form location (LinkedIn geo / address)."""
    if value is None:
        return ""
    text = normalize_text(value)
    if not text:
        return ""
    compact_all = re.sub(r"[^a-z0-9]", "", text)

    for phrase in _COUNTRY_PHRASES:
        phrase_compact = re.sub(r"[^a-z0-9]", "", phrase)
        if phrase in text or (phrase_compact and phrase_compact in compact_all):
            return _COUNTRY_CANON.get(phrase_compact, phrase_compact)

    tokens = [re.sub(r"[^a-z0-9]", "", t) for t in re.split(r"[\s,]+", text) if t]
    tokens = [t for t in tokens if t]

    # US city/state profiles often omit country — detect state before short ISO codes
    # so "IN" / "CA" are Indiana / California, not India / Canada.
    for token in tokens:
        if token in _US_STATE_ABBR or token in _US_STATE_NAMES:
            return "us"
    for phrase in (
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "rhode island",
        "south carolina",
        "south dakota",
        "west virginia",
        "district of columbia",
    ):
        if phrase in text:
            return "us"

    for token in tokens:
        if token in _COUNTRY_CANON:
            return _COUNTRY_CANON[token]
    return ""


def _person_country_from_row(
    source_row: dict[str, Any] | None, person_location: str | None
) -> str:
    explicit = _pick_from_row(source_row, PERSON_COUNTRY_ALIASES)
    if explicit:
        code = normalize_country(explicit)
        if code:
            return code
    return country_from_location_text(person_location)


def _compare_location_country(
    uploaded: str | None,
    extracted: str | None,
    *,
    uploaded_country: str | None = None,
) -> bool | None:
    """Person/company location vs LinkedIn: country-wise."""
    if not uploaded or not str(uploaded).strip():
        return None
    if values_equivalent(uploaded, extracted):
        return True
    left = normalize_country(uploaded_country) if uploaded_country else ""
    if not left:
        left = country_from_location_text(uploaded)
    right = country_from_location_text(extracted)
    if left and right:
        return left == right
    # Country unknown on a side ("Greater Boston Area"): a shared city still
    # confirms a match, anything else stays inconclusive rather than a conflict.
    if locations_compatible(uploaded, extracted) is True:
        return True
    return False if left else None


def _compare_location(original: str | None, extracted: str | None) -> bool | None:
    """Person location vs LinkedIn: country-wise only."""
    return _compare_location_country(original, extracted)


def _company_country_from_row(
    source_row: dict[str, Any] | None, company_location: str | None
) -> str:
    explicit = _pick_from_row(source_row, COMPANY_COUNTRY_ALIASES)
    if explicit:
        code = normalize_country(explicit)
        if code:
            return code
    return country_from_location_text(company_location)


def _compare_company_location_country(
    source_row: dict[str, Any] | None,
    company_location: str | None,
    extracted_location: str | None,
) -> bool | None:
    """Company location vs LinkedIn: country-wise."""
    if not company_location or not str(company_location).strip():
        return None
    if values_equivalent(company_location, extracted_location):
        return True
    left = _company_country_from_row(source_row, company_location)
    right = country_from_location_text(extracted_location)
    if left and right:
        return left == right
    if locations_compatible(company_location, extracted_location) is True:
        return True
    return False if left else None


def _company_address_consistency(source_row: dict[str, Any] | None) -> bool | None:
    """Cross-check Company Country vs country inferred from Company Address."""
    country = _pick_from_row(source_row, COMPANY_COUNTRY_ALIASES)
    address = _pick_from_row(source_row, COMPANY_ADDRESS_ALIASES)
    if not country or not address:
        return None
    left = normalize_country(country)
    right = country_from_location_text(address)
    if not left or not right:
        return None
    return left == right


def _compare_company(original: str | None, extracted: str | None) -> bool | None:
    if not original or not str(original).strip():
        return None
    if values_equivalent(original, extracted):
        return True
    left = normalize_company(original)
    right = normalize_company(extracted)
    if not left:
        return None
    if not right:
        return False
    if left == right:
        return True
    # Conservative containment after suffix strip only (Microsoft vs Microsoft Corporation).
    if len(left) >= 4 and (left in right or right in left):
        shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
        if longer.startswith(shorter + " ") or longer.endswith(" " + shorter):
            return True
    return False


COMPARE_FIELDS = ("name", "designation", "company", "location", "company_location")

# LinkedIn only exposes a person-level geo, so company location compares against it.
EXTRACTED_FIELD_SOURCE = {
    "name": "name",
    "designation": "designation",
    "company": "company",
    "location": "location",
    "company_location": "location",
}


def compare_field(
    field: str,
    uploaded: str | None,
    extracted: str | None,
    *,
    source_row: dict[str, Any] | None = None,
) -> bool | None:
    """Live uploaded-vs-extracted check for one field.

    Returns True (agree), False (real difference) or None (nothing to compare).
    This is the single source of truth for both scoring and the review UI, so a
    field can never be shown as conflicting while the score counts it as matched.
    """
    if field == "name":
        return _compare_name(uploaded, extracted)
    if field == "designation":
        return _compare_designation(uploaded, extracted)
    if field == "company":
        return _compare_company(uploaded, extracted)
    if field == "location":
        return _compare_location_country(
            uploaded,
            extracted,
            uploaded_country=_pick_from_row(source_row, PERSON_COUNTRY_ALIASES),
        )
    if field == "company_location":
        return _compare_company_location_country(source_row, uploaded, extracted)
    raise ValueError(f"Unknown field: {field}")


def evaluate_matches(
    source_row: dict[str, Any] | None, extracted: dict[str, Any] | None
) -> dict[str, bool | None]:
    """Recompute every field match from the current values."""
    originals = original_fields(source_row)
    extracted = extracted or {}
    return {
        field: compare_field(
            field,
            originals.get(field),
            extracted.get(EXTRACTED_FIELD_SOURCE[field]),
            source_row=source_row,
        )
        for field in COMPARE_FIELDS
    }


def compare_uploaded_vs_extracted(
    source_row: dict[str, Any] | None,
    *,
    extracted_name: str | None,
    extracted_designation: str | None,
    extracted_company: str | None,
    extracted_location: str | None,
    match_threshold: int = 100,
    review_threshold: int = 100,
) -> VerificationResult:
    originals = original_fields(source_row)
    name_match = _compare_name(originals["name"], extracted_name)
    designation_match = _compare_designation(originals["designation"], extracted_designation)
    company_match = _compare_company(originals["company"], extracted_company)
    # Person + company location: country-wise uploaded vs extracted only.
    location_match = _compare_location_country(
        originals["location"],
        extracted_location,
        uploaded_country=_pick_from_row(source_row, PERSON_COUNTRY_ALIASES),
    )
    company_location_match = _compare_company_location_country(
        source_row, originals["company_location"], extracted_location
    )

    excel_location_notes: list[str] = []

    # Excel-internal: Company Country vs Company Address country.
    address_ok = _company_address_consistency(source_row)
    if address_ok is False:
        company_location_match = False
        excel_location_notes.append("company_country_vs_address")

    # Excel-internal: person vs company country (city differences are allowed).
    person_country = _person_country_from_row(source_row, originals["location"])
    company_country = _company_country_from_row(
        source_row, originals["company_location"]
    )
    if person_country and company_country and person_country != company_country:
        excel_location_notes.append("person_vs_company_country")
        if company_location_match is True:
            company_location_match = False

    flags = [
        name_match,
        designation_match,
        company_match,
        location_match,
        company_location_match,
    ]
    compared = sum(1 for f in flags if f is not None)
    matched = sum(1 for f in flags if f is True)
    if compared == 0:
        return VerificationResult(
            status=VERIFY_NOT_VERIFIED,
            score=0,
            compared=0,
            matched=0,
            reason="No original Name/Designation/Company/Location values to compare",
            name_match=name_match,
            designation_match=designation_match,
            company_match=company_match,
            location_match=location_match,
            company_location_match=company_location_match,
            original_name=originals["name"],
            original_designation=originals["designation"],
            original_company=originals["company"],
            original_location=originals["location"],
            original_company_location=originals["company_location"],
        )

    score = int(round((matched / compared) * 100))
    mismatches = []
    if name_match is False:
        mismatches.append("name")
    if designation_match is False:
        mismatches.append("designation")
    if company_match is False:
        mismatches.append("company")
    if location_match is False:
        mismatches.append("location")
    if company_location_match is False:
        mismatches.append("company_location")

    if not mismatches and score >= match_threshold:
        status = VERIFY_VERIFIED
        reason = f"{matched}/{compared} fields matched"
    elif not mismatches:
        status = VERIFY_REVIEW
        reason = f"{matched}/{compared} fields matched"
    elif score >= review_threshold:
        status = VERIFY_REVIEW
        reason = "Partial match: " + ", ".join(mismatches)
    else:
        status = VERIFY_MISMATCH
        reason = "Mismatch: " + ", ".join(mismatches)

    if excel_location_notes:
        reason = f"{reason}; Excel location check: {', '.join(excel_location_notes)}"

    return VerificationResult(
        status=status,
        score=score,
        compared=compared,
        matched=matched,
        reason=reason,
        name_match=name_match,
        designation_match=designation_match,
        company_match=company_match,
        location_match=location_match,
        company_location_match=company_location_match,
        original_name=originals["name"],
        original_designation=originals["designation"],
        original_company=originals["company"],
        original_location=originals["location"],
        original_company_location=originals["company_location"],
    )


def apply_verification(item: Any, *, match_threshold: int, review_threshold: int) -> VerificationResult:
    """Write verification fields onto a bulk job item. Does not change extraction status."""
    if getattr(item, "status", None) != "SUCCESS":
        item.verification_status = VERIFY_NOT_VERIFIED
        item.verification_score = 0
        item.name_match = None
        item.designation_match = None
        item.company_match = None
        item.location_match = None
        if hasattr(item, "company_location_match"):
            item.company_location_match = None
        item.verification_reason = "Extraction did not succeed"
        return VerificationResult(
            status=VERIFY_NOT_VERIFIED,
            score=0,
            compared=0,
            matched=0,
            reason=item.verification_reason,
            name_match=None,
            designation_match=None,
            company_match=None,
            location_match=None,
            company_location_match=None,
            original_name=None,
            original_designation=None,
            original_company=None,
            original_location=None,
            original_company_location=None,
        )

    result = compare_uploaded_vs_extracted(
        getattr(item, "source_row_json", None),
        extracted_name=getattr(item, "name", None),
        extracted_designation=getattr(item, "designation", None),
        extracted_company=getattr(item, "company", None),
        extracted_location=getattr(item, "location", None),
        match_threshold=match_threshold,
        review_threshold=review_threshold,
    )
    item.verification_status = result.status
    item.verification_score = result.score
    item.name_match = result.name_match
    item.designation_match = result.designation_match
    item.company_match = result.company_match
    item.location_match = result.location_match
    if hasattr(item, "company_location_match"):
        item.company_location_match = result.company_location_match
    item.verification_reason = result.reason
    return result
