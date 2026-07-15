"""REST API Blueprint for the Event Sync Service.

Exposes reconciled meeting data as JSON via GET endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify

from app.models import Conflict, FieldValue, UnifiedMeeting

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Module-level store for unified meetings; initialized by app factory
_meetings: list[UnifiedMeeting] = []


def init_api(meetings: list[UnifiedMeeting]) -> None:
    """Initialize the API module with reconciled meetings.

    Called during app factory setup after ingestion and reconciliation.
    """
    global _meetings
    _meetings = meetings


def _serialize_field_value(field_value: FieldValue) -> dict[str, Any]:
    """Serialize a FieldValue to a JSON-compatible dict with provenance metadata."""
    value = field_value.value

    # Convert datetime objects to ISO format strings
    if isinstance(value, datetime):
        value = value.isoformat()

    alternative = field_value.alternative
    if isinstance(alternative, datetime):
        alternative = alternative.isoformat()

    return {
        "value": value,
        "source": field_value.source,
        "alternative": alternative,
        "alternative_source": field_value.alternative_source,
        "is_conflict": field_value.is_conflict,
    }


def _serialize_conflict(conflict: Conflict) -> dict[str, Any]:
    """Serialize a Conflict to a JSON-compatible dict."""
    primary_value = conflict.primary_value
    alternative_value = conflict.alternative_value

    # Convert datetime objects to ISO format strings
    if isinstance(primary_value, datetime):
        primary_value = primary_value.isoformat()
    if isinstance(alternative_value, datetime):
        alternative_value = alternative_value.isoformat()

    return {
        "field_name": conflict.field_name,
        "primary_value": primary_value,
        "primary_source": conflict.primary_source,
        "alternative_value": alternative_value,
        "alternative_source": conflict.alternative_source,
        "resolution_reason": conflict.resolution_reason,
    }


def _serialize_meeting(meeting: UnifiedMeeting) -> dict[str, Any]:
    """Serialize a UnifiedMeeting to a JSON-compatible dict.

    Includes full provenance metadata for every field and conflict details.
    """
    return {
        "id": meeting.id,
        "title": _serialize_field_value(meeting.title),
        "start_time": _serialize_field_value(meeting.start_time),
        "end_time": _serialize_field_value(meeting.end_time),
        "organizer": _serialize_field_value(meeting.organizer),
        "attendees": _serialize_field_value(meeting.attendees),
        "location": _serialize_field_value(meeting.location),
        "description": _serialize_field_value(meeting.description),
        "source_records": meeting.source_records,
        "sources": meeting.sources,
        "match_confidence": meeting.match_confidence,
        "conflicts": [_serialize_conflict(c) for c in meeting.conflicts],
    }


@api_bp.route("/meetings", methods=["GET"])
def get_meetings():
    """Return all unified meetings as JSON.

    Returns HTTP 200 with {"meetings": [...]} containing full provenance.
    """
    serialized = [_serialize_meeting(m) for m in _meetings]
    return jsonify({"meetings": serialized}), 200


@api_bp.route("/meetings/<meeting_id>", methods=["GET"])
def get_meeting(meeting_id: str):
    """Return a single unified meeting by UUID.

    Returns HTTP 200 with the meeting dict, or HTTP 404 if not found.
    """
    for meeting in _meetings:
        if meeting.id == meeting_id:
            return jsonify(_serialize_meeting(meeting)), 200

    return jsonify({"error": "Meeting not found"}), 404
