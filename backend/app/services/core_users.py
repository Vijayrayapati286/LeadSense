"""Single source of truth for who is allowed to use this application.

Named team members, gated at login (see auth_service.py) — no one outside
this list can authenticate, through any login path, until real Azure AD
group-based access replaces this hardcoded list. Edit this list to
add/remove access.

Passwords are NOT stored here — this file is committed to a shared repo, so
passwords live only in the CORE_USER_PASSWORDS env var (see
seed_service.provision_core_users and backend/.env.example) and are never
in source control.
"""

CORE_USERS = [
    ("Veerendra Chowhan", "veerendra.chowhan@feuji.com"),
    ("Srikanth Reddy", "srikanth.k@feuji.com"),
    ("Preeti Gupta", "preeti.gupta@feuji.com"),
    ("Ramya Pinnika", "ramya.pinnika@feuji.com"),
    ("Ramya Swathi", "ramya.pasupuleti@feuji.com"),
    ("Roshan Shenisetty", "roshan.shenishetty@feuji.com"),
    ("Srinivas Reddy", "sreenivas.jetningu@feuji.com"),
    ("Vijay Rayapati", "vijay.rayapati@feuji.com"),
    # Shared/generic credential — not a named person. Hand this one out
    # manually to anyone who needs access but isn't on the named list above.
    ("Demo User", "demo@feuji.com"),
]

ALLOWED_LOGIN_EMAILS = {email.lower() for _, email in CORE_USERS}


def is_allowed_login(email: str | None) -> bool:
    return bool(email) and email.lower() in ALLOWED_LOGIN_EMAILS
