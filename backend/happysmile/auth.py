"""Staff login, sessions and role-based access (architecture §13; edge case EC-Q-12).

Roles:
  front_desk  sees and acts on leads of their own clinics only
  manager     all clinics; can view the audit log
  admin       manager rights plus experiment configuration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response

from . import events
from .config import get_settings
from .db import tx
from .security import DUMMY_HASH, hash_ip, new_session_token, token_hash, verify_password

COOKIE = "hs_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "hs-console"
MAX_FAILED_LOGINS = 5


@dataclass
class Staff:
    id: str
    username: str
    display_name: str
    role: str
    clinic_ids: list[str] = field(default_factory=list)

    @property
    def all_clinics(self) -> bool:
        return self.role in ("manager", "admin")

    def can_see(self, clinic_id: str) -> bool:
        return self.all_clinics or clinic_id in self.clinic_ids

    def scope(self, requested: str | None, conn) -> list[str]:
        """Clinic ids this request covers: the requested clinic (if allowed) or everything visible."""
        visible = ([r["id"] for r in conn.execute("SELECT id FROM clinic WHERE is_pilot ORDER BY id")]
                   if self.all_clinics else list(self.clinic_ids))
        if requested and requested != "all":
            if requested not in visible and not (self.all_clinics and requested):
                raise HTTPException(403, "You don't have access to this clinic.")
            return [requested]
        return visible


def login(username: str, password: str, ip: str | None, response: Response) -> Staff:
    s = get_settings()
    with tx() as conn:
        failures = conn.execute(
            "SELECT count(*) AS n FROM login_attempt WHERE username = %s AND NOT ok AND at > now() - interval '15 minutes'",
            (username,)).fetchone()["n"]
        if failures >= MAX_FAILED_LOGINS:
            raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
        row = conn.execute("SELECT * FROM staff WHERE username = %s AND active", (username,)).fetchone()
        ok = verify_password(password, row["password_hash"] if row else DUMMY_HASH) and row is not None
        conn.execute("INSERT INTO login_attempt (username, ok) VALUES (%s, %s)", (username, ok))
        if not ok:
            events.audit(conn, row["id"] if row else None, "login_failed", detail={"username": username}, ip_hash=hash_ip(ip))
    if not ok:
        raise HTTPException(401, "Wrong username or password.")
    token, h = new_session_token()
    with tx() as conn:
        conn.execute("INSERT INTO staff_session (token_hash, staff_id, expires_at) VALUES (%s, %s, %s)",
                     (h, row["id"], datetime.now(timezone.utc) + timedelta(hours=s.session_hours)))
        events.audit(conn, row["id"], "login", ip_hash=hash_ip(ip))
    response.set_cookie(COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="lax",
                        max_age=s.session_hours * 3600, path="/")
    return _load_staff(row["id"])


def logout(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        with tx() as conn:
            conn.execute("UPDATE staff_session SET revoked_at = now() WHERE token_hash = %s", (token_hash(token),))
    response.delete_cookie(COOKIE, path="/")


def _load_staff(staff_id) -> Staff:
    with tx() as conn:
        row = conn.execute("SELECT id, username, display_name, role FROM staff WHERE id = %s", (staff_id,)).fetchone()
        clinics = [r["clinic_id"] for r in conn.execute(
            "SELECT clinic_id FROM staff_clinic WHERE staff_id = %s ORDER BY clinic_id", (staff_id,))]
    return Staff(id=str(row["id"]), username=row["username"], display_name=row["display_name"],
                 role=row["role"], clinic_ids=clinics)


def current_staff(request: Request) -> Staff:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Please sign in.")
    with tx() as conn:
        row = conn.execute(
            "SELECT s.staff_id FROM staff_session s JOIN staff st ON st.id = s.staff_id "
            "WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now() AND st.active",
            (token_hash(token),)).fetchone()
    if not row:
        raise HTTPException(401, "Your session has ended. Please sign in again.")
    return _load_staff(row["staff_id"])


def require_csrf(request: Request) -> None:
    """State-changing console calls must carry a custom header. Browsers won't add it
    cross-site without a CORS preflight, which this API never allows."""
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(403, "Missing request header.")


def staff_writer(request: Request, staff: Staff = Depends(current_staff)) -> Staff:
    require_csrf(request)
    return staff


def require_role(*roles: str):
    def dep(staff: Staff = Depends(current_staff)) -> Staff:
        if staff.role not in roles:
            raise HTTPException(403, "You don't have permission to do this.")
        return staff
    return dep
