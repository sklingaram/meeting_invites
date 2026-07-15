"""Ingestion Engine for the Event Sync Service.

Handles reading, parsing, validating, deduplicating, and normalizing
meeting records from CRM and Calendar source files.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from app.models import (
    DedupEntry,
    IngestionResult,
    NormalizedRecord,
    ProcessingSummary,
    ValidationWarning,
)

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Raised on file-level failures during ingestion."""

    pass


class IngestionEngine:
    """Engine for ingesting and normalizing meeting records from source files."""

    CRM_REQUIRED_FIELDS = ("crm_id", "subject", "meeting_date", "meeting_time", "relationship_owner")

    CRM_DATE_FORMATS = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
    )

    def ingest_crm(self, file_path: str) -> IngestionResult:
        """Parse CRM source file into normalized records.

        Deduplication: keeps LAST occurrence of duplicate IDs.
        Raises IngestionError on file-level failures.
        """
        raw_records = self._load_json_file(file_path, "crm")

        warnings: list[ValidationWarning] = []
        all_records: list[NormalizedRecord] = []

        for raw in raw_records:
            record, record_warnings = self._validate_crm_record(raw)
            all_records.append(record)
            warnings.extend(record_warnings)

        dedup_log: list[DedupEntry] = []
        deduped_records = self._deduplicate_crm(all_records, dedup_log)

        incomplete_count = sum(1 for r in deduped_records if not r.is_valid)
        summary = ProcessingSummary(
            source="crm",
            total_parsed=len(raw_records),
            incomplete_count=incomplete_count,
            duplicates_removed=len(dedup_log),
        )

        return IngestionResult(
            records=deduped_records,
            warnings=warnings,
            dedup_log=dedup_log,
            summary=summary,
        )

    def _load_json_file(self, file_path: str, source: str) -> list[dict]:
        """Load and validate JSON file structure.

        Raises IngestionError if file is missing, unreadable,
        not valid JSON, or not a list of objects.
        """
        path = Path(file_path)

        if not path.exists():
            raise IngestionError(
                f"{source.upper()} source file not found: {file_path}"
            )

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, PermissionError) as e:
            raise IngestionError(
                f"{source.upper()} source file unreadable: {file_path} ({e})"
            )

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise IngestionError(
                f"{source.upper()} source file contains invalid JSON: {file_path} ({e})"
            )

        if not isinstance(data, list):
            raise IngestionError(
                f"{source.upper()} source file has wrong structure: "
                f"expected a JSON array, got {type(data).__name__}"
            )

        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise IngestionError(
                    f"{source.upper()} source file has wrong structure: "
                    f"expected array of objects, item at index {i} is {type(item).__name__}"
                )

        return data

    def _validate_crm_record(
        self, raw: dict
    ) -> tuple[NormalizedRecord, list[ValidationWarning]]:
        """Validate and normalize a single CRM record."""
        warnings: list[ValidationWarning] = []
        is_valid = True

        source_id = raw.get("crm_id")
        if not source_id:
            source_id = "UNKNOWN"
            is_valid = False
            warnings.append(
                ValidationWarning(
                    source="crm",
                    record_id="UNKNOWN",
                    field="crm_id",
                    reason="Missing required field: crm_id",
                )
            )

        record_id = source_id

        # subject -> title
        title = raw.get("subject")
        if not title:
            is_valid = False
            warnings.append(
                ValidationWarning(
                    source="crm",
                    record_id=record_id,
                    field="subject",
                    reason="Missing required field: subject",
                )
            )
            title = ""

        # meeting_date
        meeting_date_str = raw.get("meeting_date")
        meeting_date = None
        if not meeting_date_str:
            is_valid = False
            warnings.append(
                ValidationWarning(
                    source="crm",
                    record_id=record_id,
                    field="meeting_date",
                    reason="Missing required field: meeting_date",
                )
            )
        else:
            meeting_date = self._parse_date(meeting_date_str)
            if meeting_date is None:
                is_valid = False
                warnings.append(
                    ValidationWarning(
                        source="crm",
                        record_id=record_id,
                        field="meeting_date",
                        reason=f"Malformed field: meeting_date value '{meeting_date_str}' "
                        f"is not a recognized date format",
                    )
                )

        # meeting_time
        meeting_time_str = raw.get("meeting_time")
        meeting_time = None
        if not meeting_time_str:
            is_valid = False
            warnings.append(
                ValidationWarning(
                    source="crm",
                    record_id=record_id,
                    field="meeting_time",
                    reason="Missing required field: meeting_time",
                )
            )
        else:
            meeting_time = self._parse_time(meeting_time_str)
            if meeting_time is None:
                is_valid = False
                warnings.append(
                    ValidationWarning(
                        source="crm",
                        record_id=record_id,
                        field="meeting_time",
                        reason=f"Malformed field: meeting_time value '{meeting_time_str}' "
                        f"is not a recognized time format",
                    )
                )

        # Combine date + time into start_time
        start_time = None
        if meeting_date is not None and meeting_time is not None:
            start_time = datetime.combine(meeting_date, meeting_time)
        elif meeting_date is not None:
            start_time = datetime.combine(meeting_date, datetime.min.time())

        # relationship_owner -> organizer
        organizer = raw.get("relationship_owner")
        if not organizer:
            is_valid = False
            warnings.append(
                ValidationWarning(
                    source="crm",
                    record_id=record_id,
                    field="relationship_owner",
                    reason="Missing required field: relationship_owner",
                )
            )

        # Construct attendees from relationship_owner + client_name
        attendees: list[str] = []
        if organizer:
            attendees.append(organizer)
        client_name = raw.get("client_name")
        if client_name:
            attendees.append(client_name)

        # Duration not explicit in CRM, default to 60
        duration_minutes = 60

        # Optional fields
        location = raw.get("location")
        description = raw.get("notes")

        record = NormalizedRecord(
            source_id=record_id,
            source="crm",
            title=title,
            start_time=start_time,
            end_time=None,
            duration_minutes=duration_minutes,
            organizer=organizer,
            attendees=attendees,
            location=location,
            description=description,
            raw_data=raw,
            is_valid=is_valid,
            validation_warnings=[w.reason for w in warnings],
        )

        return record, warnings

    def _deduplicate_crm(
        self, records: list[NormalizedRecord], dedup_log: list[DedupEntry]
    ) -> list[NormalizedRecord]:
        """Deduplicate CRM records, keeping the LAST occurrence of each ID."""
        seen: dict[str, int] = {}

        for i, record in enumerate(records):
            if record.source_id in seen:
                prev_idx = seen[record.source_id]
                dedup_log.append(
                    DedupEntry(
                        source="crm",
                        discarded_id=records[prev_idx].source_id,
                        kept_id=record.source_id,
                        reason="CRM deduplication: keeping last occurrence",
                    )
                )
                logger.info(
                    "CRM dedup: discarding earlier occurrence of %s (index %d), "
                    "keeping later occurrence (index %d)",
                    record.source_id,
                    prev_idx,
                    i,
                )
            seen[record.source_id] = i

        kept_indices = set(seen.values())
        return [records[i] for i in range(len(records)) if i in kept_indices]

    # Required fields for Calendar validation
    CALENDAR_REQUIRED_FIELDS = ("event_id", "title", "start_time", "end_time", "organizer")

    def ingest_calendar(self, file_path: str) -> IngestionResult:
        """Parse Calendar source file into normalized records.

        Deduplication: keeps FIRST occurrence of duplicate IDs.
        Raises IngestionError on file-level failures.
        """
        raw_records = self._load_json_file(file_path, "calendar")

        records: list[NormalizedRecord] = []
        warnings: list[ValidationWarning] = []
        dedup_log: list[DedupEntry] = []

        # Parse and validate all records
        parsed_records: list[NormalizedRecord] = []
        for raw in raw_records:
            record, record_warnings = self._validate_calendar_record(raw)
            parsed_records.append(record)
            warnings.extend(record_warnings)

        # Deduplicate: keep FIRST occurrence
        seen_ids: dict[str, int] = {}
        for idx, record in enumerate(parsed_records):
            source_id = record.source_id
            if source_id in seen_ids:
                # Discard this duplicate, keep the first
                first_idx = seen_ids[source_id]
                dedup_log.append(
                    DedupEntry(
                        source="calendar",
                        discarded_id=source_id,
                        kept_id=source_id,
                        reason=f"Calendar deduplication: keeping first occurrence (index {first_idx}), discarding index {idx}",
                    )
                )
                logger.info(
                    "Calendar dedup: discarding duplicate event_id '%s' at index %d "
                    "(keeping index %d)",
                    source_id,
                    idx,
                    first_idx,
                )
            else:
                seen_ids[source_id] = idx
                records.append(record)

        # Count incomplete records
        incomplete_count = sum(1 for r in records if not r.is_valid)

        summary = ProcessingSummary(
            source="calendar",
            total_parsed=len(parsed_records),
            incomplete_count=incomplete_count,
            duplicates_removed=len(dedup_log),
        )

        return IngestionResult(
            records=records,
            warnings=warnings,
            dedup_log=dedup_log,
            summary=summary,
        )

    def _validate_calendar_record(
        self, raw: dict
    ) -> tuple[NormalizedRecord, list[ValidationWarning]]:
        """Validate and normalize a single Calendar record.

        Returns a NormalizedRecord and any validation warnings.
        Records with missing/malformed required fields are marked as incomplete.
        """
        warnings: list[ValidationWarning] = []
        is_valid = True

        # Extract source_id
        source_id = raw.get("event_id")
        if not source_id:
            source_id = "UNKNOWN"
            warnings.append(
                ValidationWarning(
                    source="calendar",
                    record_id="UNKNOWN",
                    field="event_id",
                    reason="Missing required field: event_id",
                )
            )
            is_valid = False
        else:
            source_id = str(source_id)

        record_id = source_id

        # Extract and validate title
        title = raw.get("title")
        if not title:
            warnings.append(
                ValidationWarning(
                    source="calendar",
                    record_id=record_id,
                    field="title",
                    reason="Missing required field: title",
                )
            )
            is_valid = False
            title = title or ""
        else:
            title = str(title)

        # Extract and validate organizer
        organizer = raw.get("organizer")
        if not organizer:
            warnings.append(
                ValidationWarning(
                    source="calendar",
                    record_id=record_id,
                    field="organizer",
                    reason="Missing required field: organizer",
                )
            )
            is_valid = False
        else:
            organizer = str(organizer)

        # Extract and validate start_time
        start_time = self._parse_datetime(raw.get("start_time"))
        if start_time is None:
            raw_start = raw.get("start_time")
            if raw_start is None or raw_start == "":
                reason = "Missing required field: start_time"
            else:
                reason = f"Malformed field: start_time value '{raw_start}' is not a valid timestamp"
            warnings.append(
                ValidationWarning(
                    source="calendar",
                    record_id=record_id,
                    field="start_time",
                    reason=reason,
                )
            )
            is_valid = False

        # Extract and validate end_time
        end_time = self._parse_datetime(raw.get("end_time"))
        if end_time is None:
            raw_end = raw.get("end_time")
            if raw_end is None or raw_end == "":
                reason = "Missing required field: end_time"
            else:
                reason = f"Malformed field: end_time value '{raw_end}' is not a valid timestamp"
            warnings.append(
                ValidationWarning(
                    source="calendar",
                    record_id=record_id,
                    field="end_time",
                    reason=reason,
                )
            )
            is_valid = False

        # Compute duration from start_time and end_time
        duration_minutes = None
        if start_time and end_time:
            delta = end_time - start_time
            duration_minutes = int(delta.total_seconds() / 60)

        # Extract optional fields
        attendees = raw.get("attendees", [])
        if not isinstance(attendees, list):
            attendees = []
        # Ensure all attendees are strings
        attendees = [str(a) for a in attendees if a]

        location = raw.get("location")
        if location is not None:
            location = str(location) if location else None

        description = raw.get("description")
        if description is not None:
            description = str(description) if description else None

        record = NormalizedRecord(
            source_id=source_id,
            source="calendar",
            title=title,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            organizer=organizer,
            attendees=attendees,
            location=location,
            description=description,
            raw_data=raw,
            is_valid=is_valid,
            validation_warnings=[w.reason for w in warnings],
        )

        return record, warnings

    def _parse_datetime(self, value) -> datetime | None:
        """Parse a datetime string in ISO format.

        Handles both with and without 'Z' timezone suffix.
        Returns None if the value is None, empty, or unparseable.
        """
        if value is None or value == "":
            return None

        if not isinstance(value, str):
            return None

        # Strip trailing 'Z' (UTC indicator) for consistent parsing
        cleaned = value.rstrip("Z")

        try:
            return datetime.fromisoformat(cleaned)
        except (ValueError, TypeError):
            return None

    def _parse_date(self, date_str: str):
        """Try multiple date formats and return date object or None."""
        if not isinstance(date_str, str):
            return None

        date_str = date_str.strip()
        for fmt in self.CRM_DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_time(self, time_str: str):
        """Parse time string and return time object or None."""
        if not isinstance(time_str, str):
            return None

        time_str = time_str.strip()
        time_formats = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p")
        for fmt in time_formats:
            try:
                return datetime.strptime(time_str, fmt).time()
            except ValueError:
                continue
        return None
