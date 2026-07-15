"""Reconciliation Engine for the Event Sync Service.

Matches records across CRM and Calendar sources using fuzzy matching
heuristics and merges them into unified meeting records.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from app.models import Conflict, FieldValue, NormalizedRecord, UnifiedMeeting


class ReconciliationEngine:
    """Matches and merges records from CRM and Calendar sources.

    Uses a multi-signal approach combining temporal proximity,
    attendee overlap, and subject similarity to determine whether
    two records represent the same real-world meeting.
    """

    CONFIDENCE_THRESHOLD: float = 0.75
    DATE_PROXIMITY_WINDOW: timedelta = timedelta(minutes=30)
    ATTENDEE_OVERLAP_MIN: float = 0.50
    SUBJECT_SIMILARITY_MIN: float = 0.70

    def compute_match_confidence(
        self, record_a: NormalizedRecord, record_b: NormalizedRecord
    ) -> float:
        """Compute match confidence score between two records.

        Returns a value in the range [0.0, 1.0] representing how likely
        the two records refer to the same real-world meeting.

        The score is a weighted combination:
          confidence = (0.4 × date_score) + (0.3 × attendee_score) + (0.3 × subject_score)
        """
        date_score = self._date_proximity_score(record_a.start_time, record_b.start_time)
        attendee_score = self._attendee_overlap_score(
            set(record_a.attendees), set(record_b.attendees)
        )
        subject_score = self._subject_similarity_score(record_a.title, record_b.title)

        confidence = (0.4 * date_score) + (0.3 * attendee_score) + (0.3 * subject_score)
        return confidence

    def _date_proximity_score(
        self, dt_a: datetime | None, dt_b: datetime | None
    ) -> float:
        """Score based on temporal distance between two datetimes.

        Returns 1.0 if times are identical, linearly decreasing to 0.0
        at 30 minutes or more apart. Returns 0.0 if either time is None.
        """
        if dt_a is None or dt_b is None:
            return 0.0

        diff_seconds = abs((dt_a - dt_b).total_seconds())
        window_seconds = self.DATE_PROXIMITY_WINDOW.total_seconds()

        if diff_seconds >= window_seconds:
            return 0.0

        # Linear interpolation: 1.0 at 0, 0.0 at window_seconds
        return 1.0 - (diff_seconds / window_seconds)

    def _attendee_overlap_score(
        self, attendees_a: set[str], attendees_b: set[str]
    ) -> float:
        """Score based on Jaccard similarity of attendee sets.

        Performs case-insensitive comparison. Returns 0.0 if both sets
        are empty (avoids division by zero).
        """
        # Normalize to lowercase for case-insensitive comparison
        normalized_a = {a.lower() for a in attendees_a}
        normalized_b = {b.lower() for b in attendees_b}

        union = normalized_a | normalized_b
        if not union:
            return 0.0

        intersection = normalized_a & normalized_b
        return len(intersection) / len(union)

    def _subject_similarity_score(self, subject_a: str, subject_b: str) -> float:
        """Score based on string similarity using SequenceMatcher.

        Returns the ratio from difflib.SequenceMatcher. Returns 0.0
        if either subject is empty.
        """
        if not subject_a or not subject_b:
            return 0.0

        return SequenceMatcher(None, subject_a, subject_b).ratio()

    def reconcile(
        self,
        crm_records: list[NormalizedRecord],
        calendar_records: list[NormalizedRecord],
    ) -> list[UnifiedMeeting]:
        """Reconcile records from both sources into unified meetings.

        Algorithm (greedy matching):
        1. Compute match confidence for ALL pairs (crm_record, cal_record)
        2. Sort pairs by confidence descending
        3. Greedily select pairs where confidence >= 0.75, marking each record as used
        4. Merge selected pairs into UnifiedMeeting records
        5. Create single-source entries for unmatched records

        Each input record appears in exactly one UnifiedMeeting.
        """
        # Step 1: Compute pairwise match confidence scores
        scored_pairs: list[tuple[float, int, int]] = []
        for i, crm_rec in enumerate(crm_records):
            for j, cal_rec in enumerate(calendar_records):
                confidence = self.compute_match_confidence(crm_rec, cal_rec)
                scored_pairs.append((confidence, i, j))

        # Step 2: Sort by confidence descending
        scored_pairs.sort(key=lambda x: x[0], reverse=True)

        # Step 3: Greedy matching — select pairs above threshold
        used_crm: set[int] = set()
        used_cal: set[int] = set()
        matched_pairs: list[tuple[int, int, float]] = []

        for confidence, crm_idx, cal_idx in scored_pairs:
            if confidence < self.CONFIDENCE_THRESHOLD:
                break  # No more pairs above threshold (list is sorted descending)
            if crm_idx in used_crm or cal_idx in used_cal:
                continue  # Record already matched
            used_crm.add(crm_idx)
            used_cal.add(cal_idx)
            matched_pairs.append((crm_idx, cal_idx, confidence))

        # Step 4: Merge matched pairs
        unified_meetings: list[UnifiedMeeting] = []
        for crm_idx, cal_idx, confidence in matched_pairs:
            merged = self._merge_records(
                crm_records[crm_idx], calendar_records[cal_idx], confidence
            )
            unified_meetings.append(merged)

        # Step 5: Create single-source entries for unmatched CRM records
        for i, crm_rec in enumerate(crm_records):
            if i not in used_crm:
                unified_meetings.append(self._create_single_source_meeting(crm_rec))

        # Step 6: Create single-source entries for unmatched Calendar records
        for j, cal_rec in enumerate(calendar_records):
            if j not in used_cal:
                unified_meetings.append(self._create_single_source_meeting(cal_rec))

        return unified_meetings

    def _create_single_source_meeting(self, record: NormalizedRecord) -> UnifiedMeeting:
        """Create a UnifiedMeeting from a single unmatched record.

        Each field is wrapped in a FieldValue with the record's source,
        no alternative value, and is_conflict=False.
        """
        return UnifiedMeeting(
            id=str(uuid.uuid4()),
            title=FieldValue(
                value=record.title, source=record.source, is_conflict=False
            ),
            start_time=FieldValue(
                value=record.start_time, source=record.source, is_conflict=False
            ),
            end_time=FieldValue(
                value=record.end_time, source=record.source, is_conflict=False
            ),
            organizer=FieldValue(
                value=record.organizer, source=record.source, is_conflict=False
            ),
            attendees=FieldValue(
                value=record.attendees, source=record.source, is_conflict=False
            ),
            location=FieldValue(
                value=record.location, source=record.source, is_conflict=False
            ),
            description=FieldValue(
                value=record.description, source=record.source, is_conflict=False
            ),
            source_records=[record.source_id],
            sources=[record.source],
            match_confidence=None,
            conflicts=[],
        )

    @staticmethod
    def _is_empty(value: Any) -> bool:
        """Check if a value is considered empty/null."""
        if value is None:
            return True
        if isinstance(value, (str, list)) and len(value) == 0:
            return True
        return False

    # Field-to-priority-source mapping for conflict resolution
    FIELD_PRIORITY: dict[str, str] = {
        "title": "crm",
        "organizer": "crm",
        "attendees": "crm",
        "description": "crm",
        "start_time": "calendar",
        "end_time": "calendar",
        "location": "calendar",
    }

    def _resolve_conflict(
        self, field_name: str, crm_value: Any, cal_value: Any
    ) -> tuple[FieldValue, Conflict | None]:
        """Apply deterministic source-priority conflict resolution for a field.

        Rules:
        1. Both non-null and different → conflict, primary from priority source.
        2. Both non-null and same → no conflict, use value with priority source label.
        3. One null and other non-null → no conflict, use non-null value (Req 4.4).
        4. Both null → no conflict, value is None.

        Returns a tuple of (FieldValue, Conflict or None).
        """
        priority_source = self.FIELD_PRIORITY[field_name]
        other_source = "calendar" if priority_source == "crm" else "crm"

        # Determine which value belongs to which source
        priority_value = crm_value if priority_source == "crm" else cal_value
        other_value = cal_value if priority_source == "crm" else crm_value

        priority_empty = self._is_empty(priority_value)
        other_empty = self._is_empty(other_value)

        # Case 4: Both null/empty
        if priority_empty and other_empty:
            return (
                FieldValue(value=None, source=priority_source, is_conflict=False),
                None,
            )

        # Case 3: One null, other non-null → NOT a conflict (Req 4.4)
        if priority_empty and not other_empty:
            return (
                FieldValue(value=other_value, source=other_source, is_conflict=False),
                None,
            )
        if not priority_empty and other_empty:
            return (
                FieldValue(value=priority_value, source=priority_source, is_conflict=False),
                None,
            )

        # Both are non-null/non-empty — check if they are the same
        if priority_value == other_value:
            # Case 2: Same values → no conflict
            return (
                FieldValue(value=priority_value, source=priority_source, is_conflict=False),
                None,
            )

        # Case 1: Different non-null values → conflict
        resolution_reason = (
            f"{priority_source} takes priority for {field_name}"
        )
        field_value = FieldValue(
            value=priority_value,
            source=priority_source,
            alternative=other_value,
            alternative_source=other_source,
            is_conflict=True,
        )
        conflict = Conflict(
            field_name=field_name,
            primary_value=priority_value,
            primary_source=priority_source,
            alternative_value=other_value,
            alternative_source=other_source,
            resolution_reason=resolution_reason,
        )
        return (field_value, conflict)

    def _merge_records(
        self,
        crm_record: NormalizedRecord,
        cal_record: NormalizedRecord,
        confidence: float,
    ) -> UnifiedMeeting:
        """Merge two matched records into a UnifiedMeeting.

        Applies field-level conflict resolution using source priority rules:
        - CRM priority: title, organizer, attendees, description
        - Calendar priority: start_time, end_time, location

        Generates a UUID for the meeting and collects all conflicts.
        """
        meeting_id = str(uuid.uuid4())

        # Resolve each field
        title_fv, title_conflict = self._resolve_conflict(
            "title", crm_record.title, cal_record.title
        )
        start_time_fv, start_time_conflict = self._resolve_conflict(
            "start_time", crm_record.start_time, cal_record.start_time
        )
        end_time_fv, end_time_conflict = self._resolve_conflict(
            "end_time", crm_record.end_time, cal_record.end_time
        )
        organizer_fv, organizer_conflict = self._resolve_conflict(
            "organizer", crm_record.organizer, cal_record.organizer
        )
        attendees_fv, attendees_conflict = self._resolve_conflict(
            "attendees", crm_record.attendees, cal_record.attendees
        )
        location_fv, location_conflict = self._resolve_conflict(
            "location", crm_record.location, cal_record.location
        )
        description_fv, description_conflict = self._resolve_conflict(
            "description", crm_record.description, cal_record.description
        )

        # Collect non-None conflicts
        conflicts = [
            c
            for c in [
                title_conflict,
                start_time_conflict,
                end_time_conflict,
                organizer_conflict,
                attendees_conflict,
                location_conflict,
                description_conflict,
            ]
            if c is not None
        ]

        return UnifiedMeeting(
            id=meeting_id,
            title=title_fv,
            start_time=start_time_fv,
            end_time=end_time_fv,
            organizer=organizer_fv,
            attendees=attendees_fv,
            location=location_fv,
            description=description_fv,
            source_records=[crm_record.source_id, cal_record.source_id],
            sources=["crm", "calendar"],
            match_confidence=confidence,
            conflicts=conflicts,
        )
