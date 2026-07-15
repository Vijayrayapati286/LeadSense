"""Best-effort country/state -> IANA timezone lookup, used to populate
Recipient.timezone at Excel-import time so campaigns can optionally send at
each recipient's local business hours instead of a single fixed time.

Deliberately approximate: for small/single-zone countries one zone is "close
enough" for a 9am-6pm business-hours check. A handful of large countries
that span multiple zones are keyed by (country, state) instead.
"""

# Country -> IANA timezone, for countries with one practical zone.
COUNTRY_TIMEZONES = {
    "india": "Asia/Kolkata",
    "united states": "America/New_York",
    "usa": "America/New_York",
    "united kingdom": "Europe/London",
    "uk": "Europe/London",
    "canada": "America/Toronto",
    "australia": "Australia/Sydney",
    "germany": "Europe/Berlin",
    "france": "Europe/Paris",
    "spain": "Europe/Madrid",
    "italy": "Europe/Rome",
    "netherlands": "Europe/Amsterdam",
    "singapore": "Asia/Singapore",
    "japan": "Asia/Tokyo",
    "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "united arab emirates": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "brazil": "America/Sao_Paulo",
    "mexico": "America/Mexico_City",
    "south africa": "Africa/Johannesburg",
    "new zealand": "Pacific/Auckland",
    "ireland": "Europe/Dublin",
    "sweden": "Europe/Stockholm",
    "switzerland": "Europe/Zurich",
    "philippines": "Asia/Manila",
    "indonesia": "Asia/Jakarta",
    "malaysia": "Asia/Kuala_Lumpur",
    "south korea": "Asia/Seoul",
    "israel": "Asia/Jerusalem",
}

# (country, state) -> IANA timezone, for countries spanning multiple zones.
# State is matched case-insensitively; only the most common/populous zone per
# state is used.
STATE_TIMEZONES = {
    ("united states", "california"): "America/Los_Angeles",
    ("united states", "washington"): "America/Los_Angeles",
    ("united states", "oregon"): "America/Los_Angeles",
    ("united states", "nevada"): "America/Los_Angeles",
    ("united states", "arizona"): "America/Phoenix",
    ("united states", "colorado"): "America/Denver",
    ("united states", "utah"): "America/Denver",
    ("united states", "texas"): "America/Chicago",
    ("united states", "illinois"): "America/Chicago",
    ("united states", "chicago"): "America/Chicago",
    ("usa", "california"): "America/Los_Angeles",
    ("usa", "texas"): "America/Chicago",
    ("australia", "western australia"): "Australia/Perth",
    ("australia", "queensland"): "Australia/Brisbane",
    ("australia", "south australia"): "Australia/Adelaide",
    ("australia", "victoria"): "Australia/Melbourne",
    ("australia", "new south wales"): "Australia/Sydney",
    ("canada", "british columbia"): "America/Vancouver",
    ("canada", "alberta"): "America/Edmonton",
    ("canada", "ontario"): "America/Toronto",
    ("canada", "quebec"): "America/Toronto",
}


def lookup_timezone(country: str | None, state: str | None = None) -> str | None:
    """Best-effort IANA timezone for a recipient's country/state. Returns
    None if the country isn't recognized (the recipient just won't be
    eligible for timezone-aware scheduling)."""
    if not country:
        return None
    country_key = country.strip().lower()
    if state:
        state_key = state.strip().lower()
        tz = STATE_TIMEZONES.get((country_key, state_key))
        if tz:
            return tz
    return COUNTRY_TIMEZONES.get(country_key)
