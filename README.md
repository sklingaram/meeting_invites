# Event Sync Service

A Python/Flask application that ingests meeting records from CRM and Calendar sources, reconciles them using fuzzy matching heuristics, and serves a unified meeting list through a REST API and web frontend.

The service solves the problem of seeing the same meeting duplicated across systems by automatically detecting when two records from different sources refer to the same real-world meeting and merging them into a single unified view with full provenance tracking.

## Prerequisites

- Python 3.9+
- pip (Python package manager)

## Installation

```bash
pip install -r requirements.txt
```

## Running the Service

Start the service with a single command:

```bash
python -m app.app
```

Or alternatively:

```bash
python app/app.py
```

The service will:
1. Ingest CRM records from `data/crm_events.json`
2. Ingest Calendar records from `data/calendar_events.json`
3. Reconcile records across sources
4. Start the Flask server

The web frontend is available at `http://localhost:5000/` and the API at `http://localhost:5000/api/meetings`.

## Architecture

```
app/
├── app.py              # Application entry point and startup orchestration
├── ingestion.py        # Ingestion Engine — parses, validates, deduplicates source data
├── reconciliation.py   # Reconciliation Engine — matches and merges records across sources
├── api.py              # REST API blueprint — JSON endpoints for meeting data
├── frontend.py         # Frontend blueprint — Jinja2 HTML rendering
└── models.py           # Data models (NormalizedRecord, UnifiedMeeting, FieldValue, etc.)

data/
├── crm_events.json     # CRM source data
└── calendar_events.json # Calendar source data

templates/
└── meetings.html       # Jinja2 template for the meeting list page

tests/
├── test_ingestion_properties.py
├── test_reconciliation_properties.py
├── test_api_properties.py
├── test_frontend_properties.py
├── test_ingestion_unit.py
├── test_api_unit.py
├── test_frontend_unit.py
└── test_integration.py
```

**Data flow:** Source files → Ingestion Engine → Normalized Records → Reconciliation Engine → Unified Meetings → REST API / Frontend

All data is held in-memory after startup. No database is required.

## Reconciliation Approach

### Fields Compared

The Reconciliation Engine compares records across sources using three signals:

| Signal | What it measures | Weight |
|--------|-----------------|--------|
| Date/time proximity | How close the meeting start times are | 0.4 |
| Attendee overlap | Jaccard similarity of attendee sets (case-insensitive) | 0.3 |
| Subject similarity | SequenceMatcher ratio of meeting titles | 0.3 |

### Confidence Formula

```
confidence = (0.4 × date_score) + (0.3 × attendee_score) + (0.3 × subject_score)
```

Where:
- **date_score**: Linear interpolation from 1.0 (identical times) to 0.0 (≥30 minutes apart)
- **attendee_score**: `|A ∩ B| / |A ∪ B|` — Jaccard similarity of attendee sets
- **subject_score**: `SequenceMatcher(title_a, title_b).ratio()` — Python difflib string similarity

### Threshold

Pairs scoring **≥ 0.75** are merged into a single Unified Meeting. Pairs below this threshold remain as separate single-source entries.

### Rationale

The weighted approach balances three complementary signals:

- **Temporal proximity (40%)** is the strongest signal because the same real-world meeting should appear at nearly the same time in both systems. It gets the highest weight because time is the most reliable shared identifier.
- **Attendee overlap (30%)** provides a social signal — the same meeting will have the same people invited. Using Jaccard similarity handles partial overlaps where one system may have a subset of attendees.
- **Subject similarity (30%)** adds a semantic signal. Meeting titles often vary slightly between systems (e.g., "Q4 Portfolio Review" vs "Portfolio Review - Q4") so fuzzy string matching captures these variations.

The 0.75 threshold was chosen to be conservative enough to avoid false merges while still catching meetings with minor discrepancies across sources. A pair needs strong signals on at least two of the three dimensions to qualify for merging.

## Conflict Resolution Strategy

When two matched records contain different values for the same field, the system applies deterministic source-priority conflict resolution.

### Source Priority by Field

| Field | Priority Source | Rationale |
|-------|---------------|-----------|
| title | CRM | CRM titles reflect client-facing naming conventions |
| organizer | CRM | CRM tracks the relationship owner accurately |
| attendees | CRM | CRM has the authoritative client contact list |
| description | CRM | CRM notes capture client context and meeting purpose |
| start_time | Calendar | Calendar is the system of record for scheduling |
| end_time | Calendar | Calendar is the system of record for scheduling |
| location | Calendar | Calendar manages room/location bookings |

### Rationale

The strategy assigns priority based on each system's domain of authority:

- **CRM priority for client-related fields**: The CRM system is purpose-built for tracking client relationships. It maintains authoritative records of who the client contacts are, how meetings are named in a client context, and what the meeting objectives are.
- **Calendar priority for scheduling fields**: The Calendar system is the operational scheduling tool. It reflects the actual booked times, handles rescheduling, and manages physical/virtual meeting locations.

### Null Handling

When one source provides a value and the other provides null or empty for the same field, the non-null value is used as the primary value **without** generating a conflict. This avoids noise from fields that one system simply doesn't track.

## API Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/api/meetings` | All unified meetings with provenance and conflict info | 200 JSON |
| GET | `/api/meetings/<id>` | Single meeting by UUID | 200 JSON or 404 |
| GET | `/` | Web frontend — meeting list page | 200 HTML |

### Example: GET /api/meetings

Returns an array of unified meeting objects, each including:
- Field values with source provenance (`source` label per field)
- Conflict details with both primary and alternative values
- Match confidence score (for merged records)
- Source record IDs that contributed to the meeting

## Testing

Run the full test suite:

```bash
pytest tests/ -v
```

The test suite includes:
- **Property-based tests** (Hypothesis) — verify universal correctness properties across randomized inputs
- **Unit tests** — verify specific examples and edge cases
- **Integration tests** — verify the full startup-to-response flow

## Time Breakdown

| Phase | Hours |
|-------|-------|
| Ingestion Engine | _TBD_ |
| Reconciliation Engine | _TBD_ |
| REST API | _TBD_ |
| Frontend | _TBD_ |
| Testing | _TBD_ |
| Documentation | _TBD_ |
| **Total** | _TBD_ |

## AI Collaboration

This project was built with AI assistance using **Kiro**, an AI-powered development environment. Kiro contributed to:

- **Requirements analysis** — structuring acceptance criteria and identifying edge cases
- **Design decisions** — evaluating reconciliation heuristics, conflict resolution strategies, and architecture tradeoffs
- **Implementation** — generating code for ingestion, reconciliation, API, frontend, and test suites
- **Property-based testing** — defining correctness properties and generating Hypothesis-based test strategies
- **Documentation** — producing this README and inline code documentation

The spec-driven workflow (requirements → design → tasks → implementation) was facilitated through Kiro's structured development process, ensuring traceability from requirements to code.
