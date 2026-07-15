# Implementation Plan: Event Sync Service

## Overview

Build a Python/Flask application that ingests meeting records from CRM and Calendar JSON sources, reconciles them using fuzzy matching heuristics, and serves unified meetings via a REST API and Jinja2 web frontend. Implementation follows an incremental approach: data models → ingestion → reconciliation → API → frontend → wiring.

## Tasks

- [x] 1. Set up project structure and data models
  - [x] 1.1 Create project directory structure and dependency manifest
    - Create `app/`, `data/`, `templates/`, `tests/` directories
    - Create `requirements.txt` with Flask, Jinja2, pytest, hypothesis
    - Create `__init__.py` files for package structure
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 1.2 Implement core data models
    - Create `app/models.py` with dataclasses: `NormalizedRecord`, `UnifiedMeeting`, `FieldValue`, `Conflict`, `ValidationWarning`, `DedupEntry`, `ProcessingSummary`, `IngestionResult`
    - Implement field definitions as specified in design document
    - _Requirements: 1.1, 2.1, 4.1, 4.3_

- [x] 2. Implement Ingestion Engine
  - [x] 2.1 Implement CRM ingestion with validation and deduplication
    - Create `app/ingestion.py` with `IngestionEngine` class
    - Implement `ingest_crm()`: parse `data/crm_events.json`, validate required fields (title, date/time, duration, organizer, attendees, source ID), normalize records
    - Actual CRM schema (from `data/crm_events.json`): `crm_id`, `subject`, `client_name`, `client_company`, `relationship_owner`, `meeting_date`, `meeting_time`, `meeting_type`, `location`, `notes`, `status`, `created_at`
    - Implement CRM deduplication: keep last occurrence of duplicate IDs (keyed on `crm_id`), log discarded entries
    - Handle file-level errors (missing file, invalid JSON, wrong structure) by raising `IngestionError`
    - Mark records with missing/malformed fields as incomplete with validation warnings
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 2.2 Implement Calendar ingestion with validation and deduplication
    - Implement `ingest_calendar()`: parse `data/calendar_events.json`, validate required fields (title, start/end time, organizer, source ID), normalize records
    - Actual Calendar schema (from `data/calendar_events.json`): `event_id`, `title`, `organizer`, `attendees` (array of emails), `start_time`, `end_time`, `location`, `description`, `is_recurring`, `status`, `created_at`
    - Implement Calendar deduplication: keep first occurrence of duplicate IDs (keyed on `event_id`), log discarded entries
    - Produce processing summary (total parsed, incomplete count, duplicates removed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 2.3 Write property tests for ingestion (Properties 1-5)
    - **Property 1: Normalization Preserves Source Data**
    - **Property 2: Validation Identifies All Field Issues**
    - **Property 3: CRM Deduplication Keeps Last Occurrence**
    - **Property 4: Calendar Deduplication Keeps First Occurrence**
    - **Property 5: Processing Summary Accuracy**
    - Create `tests/test_ingestion_properties.py` using Hypothesis strategies to generate realistic meeting records
    - **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4**

  - [ ]* 2.4 Write unit tests for ingestion error handling
    - Create `tests/test_ingestion_unit.py`
    - Test file-level errors: missing file, unreadable file, invalid JSON, wrong structure
    - Test record-level validation: missing fields, wrong types, unparseable dates
    - Test deduplication logging
    - _Requirements: 1.2, 1.4, 2.2_

- [x] 3. Checkpoint - Verify ingestion
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Reconciliation Engine
  - [x] 4.1 Implement match confidence scoring
    - Create `app/reconciliation.py` with `ReconciliationEngine` class
    - Implement `_date_proximity_score()`: linear interpolation, 1.0 at 0 min apart, 0.0 at ≥30 min apart
    - Implement `_attendee_overlap_score()`: Jaccard similarity of attendee sets (case-insensitive)
    - Implement `_subject_similarity_score()`: `SequenceMatcher` ratio from difflib
    - Implement `compute_match_confidence()`: weighted sum (0.4×date + 0.3×attendee + 0.3×subject)
    - _Requirements: 3.1, 3.4_

  - [x] 4.2 Implement record merging and conflict resolution
    - Implement `_merge_records()`: create UnifiedMeeting from two matched records
    - Implement `_resolve_conflict()`: CRM priority for title/organizer/attendees/description, Calendar priority for start_time/end_time/location
    - Handle null-field cases: non-null value wins without generating a conflict
    - Generate UUID for each UnifiedMeeting
    - _Requirements: 3.2, 3.5, 4.1, 4.2, 4.3, 4.4_

  - [x] 4.3 Implement full reconciliation pipeline
    - Implement `reconcile()`: compute pairwise scores, merge pairs above 0.75 threshold, include unmatched as single-source entries
    - Ensure no duplicate merges (each record appears in exactly one UnifiedMeeting)
    - Ensure output uniqueness: no two meetings share both date within 30 min and ≥50% attendee overlap
    - _Requirements: 3.2, 3.3, 3.6_

  - [ ]* 4.4 Write property tests for reconciliation (Properties 6-10)
    - **Property 6: Match Confidence Bounds**
    - **Property 7: Record Completeness After Reconciliation**
    - **Property 8: Output Uniqueness Constraint**
    - **Property 9: Conflict Resolution With Source Priority**
    - **Property 10: Null Fields Do Not Generate Conflicts**
    - Create `tests/test_reconciliation_properties.py` using Hypothesis strategies
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.6, 4.1, 4.2, 4.3, 4.4**

- [x] 5. Checkpoint - Verify reconciliation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement REST API
  - [x] 6.1 Implement API endpoints
    - Create `app/api.py` as a Flask Blueprint
    - Implement `GET /api/meetings`: return all UnifiedMeetings as JSON with provenance metadata and conflict info, HTTP 200
    - Implement `GET /api/meetings/<id>`: return single meeting by UUID, HTTP 200 or 404
    - Ensure Content-Type `application/json` on all responses
    - Implement JSON serialization for UnifiedMeeting including FieldValue provenance and Conflict details
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 6.2 Write property test for API serialization (Property 11)
    - **Property 11: API Serialization Completeness**
    - Create `tests/test_api_properties.py` using Hypothesis
    - **Validates: Requirements 5.2, 5.3**

  - [ ]* 6.3 Write unit tests for API endpoints
    - Create `tests/test_api_unit.py`
    - Test GET /api/meetings returns 200 with valid JSON
    - Test GET /api/meetings/<id> returns 404 for unknown ID
    - Test Content-Type headers
    - _Requirements: 5.1, 5.4, 5.5_

- [x] 7. Implement Frontend
  - [x] 7.1 Create Jinja2 templates and frontend blueprint
    - Create `app/frontend.py` as a Flask Blueprint serving at root URL `/`
    - Create `templates/meetings.html`: display meeting list with title, date/time, source indicators
    - Show source provenance labels (CRM, Calendar, or both) per meeting
    - Visually distinguish conflicting fields with both primary and alternative values and source labels
    - Display empty state message when no meetings exist
    - Sort meetings by date/time descending (most recent first)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 7.2 Write property test for display sort order (Property 12)
    - **Property 12: Meeting Display Sort Order**
    - Create `tests/test_frontend_properties.py` using Hypothesis
    - **Validates: Requirements 6.6**

  - [ ]* 7.3 Write unit tests for frontend rendering
    - Create `tests/test_frontend_unit.py`
    - Test meeting list renders with sample data
    - Test empty state message displays
    - Test conflict indicators appear for conflicting fields
    - _Requirements: 6.1, 6.3, 6.5_

- [x] 8. Wire application together and implement startup
  - [x] 8.1 Create application entry point
    - Create `app/app.py` with `create_app()` factory function
    - Implement startup sequence: ingest CRM from `data/crm_events.json` → ingest Calendar from `data/calendar_events.json` → reconcile → initialize Flask app with unified meetings
    - Register API and Frontend blueprints
    - Ensure data is reconciled before server accepts requests (eager ingestion)
    - Handle fatal startup errors: log error, exit with non-zero code
    - _Requirements: 7.1, 7.2, 7.4_

  - [x] 8.2 Create sample data files
    - Created `data/crm_events.json` with 20 CRM records (CRM-1001 through CRM-1020)
    - Created `data/calendar_events.json` with 22 Calendar records (CAL-A1 through CAL-A22)
    - Includes records that match across sources (e.g., portfolio reviews, investor updates) and some unique to each source (e.g., internal meetings, client reception)
    - _Requirements: 1.1, 2.1_

  - [x] 8.3 Create README documentation
    - Create `README.md` with prerequisites, installation, and startup command
    - Document reconciliation approach: fields compared, confidence formula, threshold, rationale
    - Document conflict resolution strategy: source priority per field, rationale
    - Include time breakdown placeholder and AI collaboration section
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 8.4 Write integration tests
    - Create `tests/test_integration.py`
    - Test full startup → ingestion → reconciliation → API response flow
    - Verify data available on first API request after startup
    - _Requirements: 7.1, 7.2_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (12 properties total)
- Unit tests validate specific examples and edge cases
- Python 3.9+ with Flask, pytest, and Hypothesis are the required dependencies
- All meeting data is stored in-memory; no database needed

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4"] },
    { "id": 4, "tasks": ["4.1"] },
    { "id": 5, "tasks": ["4.2", "4.3"] },
    { "id": 6, "tasks": ["4.4"] },
    { "id": 7, "tasks": ["6.1", "7.1"] },
    { "id": 8, "tasks": ["6.2", "6.3", "7.2", "7.3"] },
    { "id": 9, "tasks": ["8.1", "8.3"] },
    { "id": 10, "tasks": ["8.4"] }
  ]
}
```
