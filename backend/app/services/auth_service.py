"""Microsoft SSO authentication service with dev-mode fallback."""

import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import msal
from jose import jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.services.core_users import is_allowed_login

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory auth state store (use Redis in production)
_auth_states: dict[str, datetime] = {}
_dev_sessions: dict[str, dict] = {}


class AuthService:
    def __init__(self):
        self.settings = settings

    def _get_msal_app(self) -> msal.ConfidentialClientApplication | None:
        if not self.settings.is_azure_configured:
            return None
        return msal.ConfidentialClientApplication(
            client_id=self.settings.azure_client_id,
            client_credential=self.settings.azure_client_secret,
            authority=self.settings.azure_authority,
        )

    def get_login_url(self) -> dict:
        """Generate Microsoft login URL or dev-mode login info."""
        if not self.settings.is_azure_configured:
            return {
                "login_url": None,
                "dev_mode": True,
                "message": "Azure AD not configured. Use dev login endpoint.",
            }

        state = secrets.token_urlsafe(32)
        _auth_states[state] = datetime.now(timezone.utc) + timedelta(minutes=10)

        msal_app = self._get_msal_app()
        auth_url = msal_app.get_authorization_request_url(
            scopes=self.settings.azure_scopes,
            redirect_uri=self.settings.azure_redirect_uri,
            state=state,
        )
        return {"login_url": auth_url, "dev_mode": False, "state": state}

    def handle_callback(self, code: str, state: str, db: Session) -> dict:
        """Exchange auth code for token and create/update user."""
        if state not in _auth_states:
            raise ValueError("Invalid or expired auth state")

        del _auth_states[state]
        msal_app = self._get_msal_app()
        if not msal_app:
            raise ValueError("Azure AD not configured")

        result = msal_app.acquire_token_by_authorization_code(
            code=code,
            scopes=self.settings.azure_scopes,
            redirect_uri=self.settings.azure_redirect_uri,
        )

        if "error" in result:
            raise ValueError(result.get("error_description", "Authentication failed"))

        # Fetch user profile from Microsoft Graph
        import httpx

        headers = {"Authorization": f"Bearer {result['access_token']}"}
        with httpx.Client() as client:
            profile = client.get("https://graph.microsoft.com/v1.0/me", headers=headers).json()

        user = self._upsert_user(db, profile)
        token = self._create_jwt(user)
        return {"access_token": token, "user": user}

    def dev_login(self, db: Session, email: str | None = None, name: str | None = None) -> dict:
        """Development login when Azure AD is not configured.

        `name` is only included in the profile when actually supplied — an
        existing (already-provisioned) user's real name must never be
        clobbered by a generic default just because whoever's logging in
        only typed their email.
        """
        email = email or "demo@company.com"
        profile = {
            "id": f"dev-{email}",
            "mail": email,
            "userPrincipalName": email,
            "department": "Sales",
        }
        if name:
            profile["displayName"] = name
        user = self._upsert_user(db, profile)
        token = self._create_jwt(user)
        return {"access_token": token, "user": user}

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    def password_login(self, db: Session, email: str, password: str) -> dict:
        """Email+password login for named team members provisioned with a
        set password (see seed_service.provision_core_users), independent of
        both Azure AD and the unauthenticated dev-login fallback."""
        user = db.query(User).filter(User.email == email).first()
        if not user or not user.password_hash or not self.verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")
        token = self._create_jwt(user)
        return {"access_token": token, "user": user}

    def _upsert_user(self, db: Session, profile: dict) -> User:
        email = profile.get("mail") or profile.get("userPrincipalName", "")
        oid = profile.get("id", "")

        # Single choke point for both Azure AD (handle_callback) and
        # dev_login — only the hardcoded core team can authenticate through
        # either path until real Azure AD group-based access replaces this.
        if not is_allowed_login(email):
            raise ValueError(f"{email or '(no email)'} is not authorized to access this application")

        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                name=profile.get("displayName", "Unknown"),
                email=email,
                department=profile.get("department", "Sales"),
                azure_oid=oid,
            )
            db.add(user)
        else:
            user.name = profile.get("displayName", user.name)
            user.department = profile.get("department", user.department)
            user.azure_oid = oid

        db.commit()
        db.refresh(user)
        return user

    def _create_jwt(self, user: User) -> str:
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        }
        return jwt.encode(payload, self.settings.secret_key, algorithm="HS256")

    def verify_token(self, token: str) -> dict | None:
        try:
            return jwt.decode(token, self.settings.secret_key, algorithms=["HS256"])
        except Exception:
            return None

    def get_current_user(self, db: Session, token: str) -> User | None:
        payload = self.verify_token(token)
        if not payload:
            return None
        return db.query(User).filter(User.id == int(payload["sub"])).first()
