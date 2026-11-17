"""Notification service stub (R3.9, R5.5).

Records an in-app notification row for a user. The full multi-channel delivery
(email/ICS/digests) arrives in FEAT-005; for now notify() just persists a
notifications row so favorite-invite and preference-alert flows have somewhere
to land. Stdlib only.
"""

from app import db


def notify(conn, user_id, kind, subject="", body=""):
    """Persist an in-app notification. Returns the new row id."""
    return db.insert(
        conn, "notifications",
        user_id=user_id, kind=kind, subject=subject, body=body, is_read=0,
    )
