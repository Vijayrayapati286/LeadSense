"""Named team members for password seed / local dev-login only.

Microsoft SSO does not use this list — any user who authenticates with
Azure AD (the configured Entra tenant) can sign in. CORE_USERS is still
used to provision email+password accounts (CORE_USER_PASSWORDS) and to
gate the unauthenticated /auth/dev-login fallback.

Passwords are NOT stored here — this file is committed to a shared repo, so
passwords live only in the CORE_USER_PASSWORDS env var (see
seed_service.provision_core_users and backend/.env.example) and are never
in source control.
"""

CORE_USERS = [("Veerendra Chowhan", "veerendra.chowhan@feuji.com"), ("Srikanth Reddy", "srikanth.k@feuji.com"), ("Preeti Gupta", "preeti.gupta@feuji.com"), ("Ramya Pinnika", "ramya.pinnika@feuji.com"), ("Ramya Swathi", "ramya.pasupuleti@feuji.com"), ("Roshan Shenisetty", "roshan.shenishetty@feuji.com"), ("Sreenivas Reddy", "sreenivas.jetningu@feuji.com"), ("Vijay Rayapati", "vijay.rayapati@feuji.com"), ("Demo User", "demo@feuji.com"), ("Jennifer Wilson", "jennifer.wilson@feuji.com"), ("Shashank Shukla", "shashank.shukla@feuji.com")]

ALLOWED_LOGIN_EMAILS = {email.lower() for _, email in CORE_USERS}


def is_allowed_login(email: str | None) -> bool:
    return bool(email) and email.lower() in ALLOWED_LOGIN_EMAILS
