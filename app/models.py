"""Core data models for the Event Sync Service.

Defines dataclasses for normalized records, unified meetings,
field provenance tracking, conflict resolution, and processing logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NormalizedRecord:
    """Internal representation of a meeting record after ingestion.

    Common structure for both CRM and Calendar sources.
    """

    source_id: str
    """Original record identifier from source."""

    source: str
    """Source system: 'crm' or 'calendar'."""

    title: str
    """Meeting title/subject."""

    start_time: datetime | None = None
    """Meeting start time (UTC)."""

    end_time: datetime | None = None
    """Meeting end time (UTC)."""

    duration_minutes: int | None = None
    """Duration in minutes."""

    organizer: str | None = None
    """Meeting organizer name/email."""

    attendees: list[str] = field(default_factory=list)
    """List of attendee names/emails."""

    location: str | None = None
    """Meeting location."""

    description: str | None = None
    """Meeting description/notes."""

    raw_data: dict = field(default_factory=dict)
    """Original source record for reference."""

    is_valid: bool = True
    """Whether all required fields passed validation."""

    validation_warnings: list[str] = field(default_factory=list)
    """Descriptions of validation issues."""


@dataclass
class FieldValue:
    """Tracks provenance for a single field in a unified meeting.

    Records which source provided the value and whether a conflict exists.
    """

    value: Any
    """The primary (resolved) value."""

    source: str
    """Source that provided the primary value."""

    alternative: Any | None = None
    """The non-primary value (if conflict exists)."""

    alternative_source: str | None = None
    """Source of the alternative value."""

    is_conflict: bool = False
    """Whether this field has conflicting values across sources."""


@dataclass
class Conflict:
    """Detailed record of a field-level conflict between sources."""

    field_name: str
    """Name of the conflicting field."""

    primary_value: Any
    """The selected primary value."""

    primary_source: str
    """Source that provided the primary value."""

    alternative_value: Any
    """The non-selected value."""

    alternative_source: str
    """Source that provided the alternative."""

    resolution_reason: str
    """Why this resolution was chosen."""


@dataclass
class UnifiedMeeting:
    """Reconciled output record combining data from one or both sources.

    Each field is wrapped in a FieldValue to track provenance.
    """

    id: str
    """Generated unique identifier (UUID)."""

    title: FieldValue
    """Meeting title with provenance."""

    start_time: FieldValue
    """Start time with provenance."""

    end_time: FieldValue
    """End time with provenance."""

    organizer: FieldValue
    """Organizer with provenance."""

    attendees: FieldValue
    """Attendee list with provenance."""

    location: FieldValue
    """Location with provenance."""

    description: FieldValue
    """Description with provenance."""

    source_records: list[str] = field(default_factory=list)
    """Source record IDs that contributed."""

    sources: list[str] = field(default_factory=list)
    """Source systems: ['crm'], ['calendar'], or ['crm', 'calendar']."""

    match_confidence: float | None = None
    """None for single-source, 0.0-1.0 for merged records."""

    conflicts: list[Conflict] = field(default_factory=list)
    """Fields where sources disagree."""


@dataclass
class ValidationWarning:
    """Warning generated during record validation."""

    source: str
    """Source system that produced the warning."""

    record_id: str
    """ID of the record with the issue."""

    field: str
    """Name of the problematic field."""

    reason: str
    """Description of the validation issue."""


@dataclass
class DedupEntry:
    """Log entry for a deduplication action."""

    source: str
    """Source system where dedup occurred."""

    discarded_id: str
    """ID of the record that was discarded."""

    kept_id: str
    """ID of the record that was kept."""

    reason: str
    """Reason for keeping one over the other."""


@dataclass
class ProcessingSummary:
    """Summary statistics for a single source ingestion run."""

    source: str
    """Source system being summarized."""

    total_parsed: int
    """Total number of records parsed from source."""

    incomplete_count: int
    """Number of records marked as incomplete (validation failures)."""

    duplicates_removed: int
    """Number of records discarded during deduplication."""


@dataclass
class IngestionResult:
    """Complete result of ingesting a single source file."""

    records: list[NormalizedRecord]
    """Normalized records after validation and deduplication."""

    warnings: list[ValidationWarning]
    """All validation warnings generated during processing."""

    dedup_log: list[DedupEntry]
    """Log of all deduplication actions taken."""

    summary: ProcessingSummary
    """Processing statistics for this ingestion run."""
