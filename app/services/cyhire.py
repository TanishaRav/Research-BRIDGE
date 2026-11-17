"""CyHire / 12twenty forward service stub (R11.1).

When a match session has ended (closed) and a project still has unmatched /
unfilled openings, a manager can forward that opening to CyHire (a 12twenty
career-services platform) so it can be advertised as a job posting. This stub
builds the 12twenty-shaped JSON payload and records it via an
``integration_events`` row. No live network call is made (INTEGRATIONS_ONLY).

Stdlib only; takes an open sqlite3 connection so it shares the request
transaction.
"""

import json

from app import db


def build_payload(conn, project, openings):
    """Return a 12twenty-shaped dict for a project's unfilled openings.

    The shape mirrors 12twenty's job-posting create API: a jobPosting object
    with employer, title, description, positions, compensation, and eligibility
    fields. Values are drawn from the project row.
    """
    mentors = db.project_mentors(conn, project["id"])
    pi = next((m for m in mentors if m["is_pi"]), None)
    session = db.get_session(conn, project["session_id"])

    if project["comp_type"] == "credit":
        compensation = {
            "type": "academicCredit",
            "credit": project["credit_option"] or None,
        }
    else:
        compensation = {
            "type": "hourly",
            "hourlyRate": project["hourly_rate"],
            "currency": "USD",
        }

    return {
        "jobPosting": {
            "externalId": "spark-project-%d" % project["id"],
            "title": project["title"],
            "description": project["description"] or "",
            "employer": {
                "name": "State University Research",
                "contactName": pi["display_name"] if pi else None,
                "contactEmail": pi["email"] if pi else None,
            },
            "jobType": "ResearchAssistantship",
            "positionsAvailable": openings,
            "compensation": compensation,
            "eligibility": {
                "citizenshipRequired": not bool(project["noncitizen_eligible"]),
            },
            "source": {
                "system": "SPARK",
                "sessionId": project["session_id"],
                "sessionName": session["name"] if session else None,
            },
        }
    }


def forward(conn, project, openings=None):
    """Build and record a CyHire forward for a project. Returns (event_id, payload).

    `openings` is the number of unfilled slots; when omitted it is computed as
    capacity minus active matches. Recording does not commit; the caller owns
    the transaction.
    """
    if openings is None:
        cap = project["capacity"] or project["positions"] or 0
        openings = cap - db.project_filled_count(conn, project["session_id"], project["id"])
    payload = build_payload(conn, project, openings)
    event_id = db.record_integration_event(
        conn, target="cyhire", payload_json=json.dumps(payload),
        session_id=project["session_id"], project_id=project["id"],
        status="recorded",
    )
    return event_id, payload
