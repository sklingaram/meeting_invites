"""Frontend blueprint for the Event Sync Service.

Serves the Jinja2-rendered HTML meeting list at the root URL.
"""

from flask import Blueprint, render_template

from app.models import UnifiedMeeting

frontend_bp = Blueprint(
    "frontend", __name__, template_folder="../templates"
)

_meetings: list[UnifiedMeeting] = []


def init_frontend(meetings: list[UnifiedMeeting]) -> None:
    """Initialize the frontend with reconciled meeting data."""
    global _meetings
    _meetings = meetings


@frontend_bp.route("/meetings")
def meeting_list():
    """Render the meeting list page sorted by date/time descending."""
    from datetime import datetime

    # Meetings with None start_time sort to the end (use min datetime as sentinel)
    _min_dt = datetime.min

    sorted_meetings = sorted(
        _meetings,
        key=lambda m: m.start_time.value if m.start_time.value is not None else _min_dt,
        reverse=True,
    )
    return render_template("meetings.html", meetings=sorted_meetings)
