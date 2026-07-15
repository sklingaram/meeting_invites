# Requirements Document

## Introduction

The Event Sync Service is an internal platform service that helps a sales team track client meetings by ingesting data from two upstream systems (a CRM API and a Calendar API), reconciling records that refer to the same real-world meeting, and serving a unified meeting list through a REST API and simple web frontend. The service must handle ambiguity in matching records across sources, resolve data conflicts, and present clear provenance information to users.

## Glossary

- **Event_Sync_Service**: The complete application comprising the Ingestion_Engine, Reconciliation_Engine, REST_API, and Frontend
- **Ingestion_Engine**: The component responsible for reading and normalizing raw meeting data from source files
- **Reconciliation_Engine**: The component responsible for matching and merging records from multiple sources into unified meeting records
- **REST_API**: The Flask-based HTTP interface that serves reconciled meeting data to clients
- **Frontend**: The web-based user interface that displays the unified meeting list
- **CRM_Source**: The upstream data file (`/data/crm_events.json`) containing meeting records with client info, meeting dates, and relationship owners
- **Calendar_Source**: The upstream data file (`/data/calendar_events.json`) containing calendar entries with attendees, times, locations, and recurrence info
- **Unified_Meeting**: A reconciled meeting record that combines data from one or both sources into a single logical meeting representation
- **Conflict**: A situation where two sources provide differing values for the same field of a matched meeting
- **Match_Confidence**: A score or classification indicating the certainty that two records from different sources refer to the same real-world meeting

## Requirements

### Requirement 1: Ingest CRM Source Data

**User Story:** As a sales team member, I want the service to ingest CRM meeting records, so that CRM data is available for reconciliation and display.

#### Acceptance Criteria

1. WHEN the Ingestion_Engine processes the CRM_Source file, THE Ingestion_Engine SHALL parse each record into a normalized internal meeting representation containing at minimum: meeting title, date/time, duration, organizer, attendees, and a source record identifier
2. IF a record in the CRM_Source is missing one or more required fields (meeting title, date/time, duration, organizer, attendees, or source record identifier) or contains fields that do not conform to their expected data type or format, THEN THE Ingestion_Engine SHALL mark the record as incomplete, include it in the output with a validation warning that identifies which fields are missing or malformed, and continue processing subsequent records
3. WHEN the Ingestion_Engine encounters two or more records within the CRM_Source that share the same source record identifier, THE Ingestion_Engine SHALL retain only the last-occurring instance, discard earlier duplicates, and record each deduplication action in a processing log including the discarded record's identifier
4. IF the CRM_Source file is missing, unreadable, or cannot be parsed, THEN THE Ingestion_Engine SHALL abort ingestion for that source, produce no partial output, and report an error indicating the file-level failure reason

### Requirement 2: Ingest Calendar Source Data

**User Story:** As a sales team member, I want the service to ingest Calendar meeting records, so that calendar data is available for reconciliation and display.

#### Acceptance Criteria

1. WHEN the Ingestion_Engine processes the Calendar_Source file, THE Ingestion_Engine SHALL parse each record into a normalized internal meeting representation containing at minimum: meeting title, start date/time, end date/time, organizer, attendee list, and source record identifier
2. IF a record in the Calendar_Source is missing one or more required fields (meeting title, start date/time, end date/time, organizer, or source record identifier) or contains fields that do not conform to their expected format (e.g., date/time not parseable as a valid timestamp), THEN THE Ingestion_Engine SHALL mark the record as incomplete, include it in the output with a validation warning that identifies each failing field and the reason for failure, and still make the record available for downstream processing
3. WHEN the Ingestion_Engine encounters two or more records within the Calendar_Source that share the same source record identifier, THE Ingestion_Engine SHALL retain only the first instance, discard subsequent duplicates, and record each deduplication action in a processing log including the discarded record's source record identifier
4. WHEN the Ingestion_Engine successfully completes processing of a Calendar_Source file, THE Ingestion_Engine SHALL produce a processing summary indicating the total number of records parsed, the number marked incomplete, and the number of duplicates removed

### Requirement 3: Reconcile Meetings Across Sources

**User Story:** As a sales team member, I want records from both sources that refer to the same real-world meeting to be merged, so that I see one unified entry per meeting rather than duplicates.

#### Acceptance Criteria

1. WHEN the Reconciliation_Engine processes normalized records from both sources, THE Reconciliation_Engine SHALL compare records using a combination of date proximity (start times within 30 minutes), attendee overlap (at least 50% of attendees in common), and subject similarity (at least 70% string similarity score) to identify matches
2. WHEN two records from different sources yield a Match_Confidence of 0.75 or higher on a scale of 0.0 to 1.0, THE Reconciliation_Engine SHALL merge them into a single Unified_Meeting record
3. WHEN a record from one source has no match in the other source with a Match_Confidence of 0.75 or higher, THE Reconciliation_Engine SHALL include the record as a Unified_Meeting with a single-source provenance indicator identifying which source contributed the record
4. THE Reconciliation_Engine SHALL assign a Match_Confidence value between 0.0 and 1.0 (inclusive) to each Unified_Meeting that was produced by merging two source records, where 0.0 indicates lowest confidence and 1.0 indicates an exact match across all compared fields
5. WHEN merging two source records into a Unified_Meeting and the records contain conflicting values for the same field, THE Reconciliation_Engine SHALL retain the value from the most recently updated record and preserve the other source's value as an alternate reference
6. WHEN the Reconciliation_Engine completes processing a batch of normalized records, THE Reconciliation_Engine SHALL produce no more than one Unified_Meeting per real-world meeting, ensuring no two Unified_Meeting records share both a date within 30 minutes and at least 50% attendee overlap

### Requirement 4: Handle Data Conflicts

**User Story:** As a sales team member, I want to see where the two sources disagree about a meeting's details, so that I can make informed decisions about which data to trust.

#### Acceptance Criteria

1. WHEN two matched records contain differing values for the same field (comparing fields: title, location, organizer, attendees, start time, end time, and description), THE Reconciliation_Engine SHALL preserve both values in the Unified_Meeting record and mark the field as a Conflict
2. THE Reconciliation_Engine SHALL select a primary value for each conflicting field using a deterministic conflict resolution strategy based on source priority (CRM_Source takes priority for client-related fields; Calendar_Source takes priority for time and location fields) and record which source provided the primary value
3. THE Unified_Meeting record SHALL retain the non-primary conflicting value as an alternative so that the user can see both options, stored alongside a label identifying the source that provided each value
4. IF one source provides a value for a field and the other source provides null or empty for that same field, THEN THE Reconciliation_Engine SHALL NOT treat this as a Conflict but SHALL use the non-null value as the primary value with a provenance indicator

### Requirement 5: Serve Reconciled Data via REST API

**User Story:** As a frontend application, I want to retrieve reconciled meeting data through a REST API, so that I can display it to the user.

#### Acceptance Criteria

1. THE REST_API SHALL expose a GET `/api/meetings` endpoint that returns the full list of Unified_Meeting records in JSON format with HTTP status 200
2. WHEN a client requests the meeting list, THE REST_API SHALL include provenance metadata for each field indicating which source (CRM_Source, Calendar_Source, or both) contributed the value
3. WHEN a client requests the meeting list, THE REST_API SHALL include Conflict information for meetings where source data disagrees, containing both the primary and alternative values with their source labels
4. THE REST_API SHALL expose a GET `/api/meetings/{id}` endpoint that returns a single Unified_Meeting record by identifier with HTTP status 200, or HTTP status 404 if the identifier does not exist
5. THE REST_API SHALL return responses with Content-Type `application/json` and respond within 2 seconds under normal operation

### Requirement 6: Display Unified Meetings in Frontend

**User Story:** As a sales team member, I want to view the reconciled meeting list in a web interface, so that I can quickly review my upcoming and past meetings.

#### Acceptance Criteria

1. THE Frontend SHALL display a list of all Unified_Meeting records retrieved from the REST_API showing at minimum: meeting title, date/time, and source indicator for each record
2. WHEN a user views a Unified_Meeting, THE Frontend SHALL indicate which source (CRM_Source, Calendar_Source, or both) contributed data to the record using distinct visual labels or icons
3. WHEN a Unified_Meeting contains Conflicts, THE Frontend SHALL visually distinguish conflicting fields (e.g., using color highlighting or an icon) and display both the primary and alternative values with their source labels
4. THE Frontend SHALL be served by the same Flask application as the REST_API at the root URL path
5. WHEN no Unified_Meeting records exist, THE Frontend SHALL display an empty state message indicating no meetings are available
6. THE Frontend SHALL display Unified_Meeting records sorted by meeting date/time in descending order (most recent first)

### Requirement 7: Single-Command Startup

**User Story:** As a developer or evaluator, I want to start the entire service with a single command, so that setup is straightforward and reproducible.

#### Acceptance Criteria

1. THE Event_Sync_Service SHALL start the REST_API and Frontend with a single documented shell command that requires no prior manual steps beyond installing dependencies
2. WHEN the Event_Sync_Service starts, THE Ingestion_Engine SHALL automatically ingest and reconcile the source data before the REST_API begins accepting requests, completing within 30 seconds for data files up to 1000 records each
3. THE Event_Sync_Service SHALL document the startup command in the project README with copy-paste ready instructions
4. IF the Ingestion_Engine encounters a fatal error during startup (e.g., missing data files), THEN THE Event_Sync_Service SHALL log the error and exit with a non-zero exit code rather than starting in a degraded state

### Requirement 8: Comprehensive README Documentation

**User Story:** As a developer or evaluator, I want a detailed README that explains how to run the service, the approach taken, and key decisions made, so that I can understand the project without reading all the code.

#### Acceptance Criteria

1. THE Event_Sync_Service SHALL include a README.md file at the project root that documents the prerequisites (Python version, dependencies), dependency installation steps, and the single shell command needed to start the service
2. THE README SHALL describe the reconciliation approach by explaining which fields are compared for matching (date proximity, attendee overlap, subject similarity), how Match_Confidence is determined, and the rationale for why those heuristics were chosen
3. THE README SHALL describe how data Conflicts are resolved by identifying the deterministic conflict resolution strategy used, which source takes priority for each field type, and why that strategy was selected
4. THE README SHALL document the time spent on development expressed in hours, broken down by major phase (ingestion, reconciliation, API, frontend, documentation)
5. IF AI tools were used during development, THEN THE README SHALL include or reference the AI-collaborated documentation (brainstorming, planning notes) that contributed to the development process; IF no AI tools were used, THEN THE README SHALL state that no AI collaboration occurred

### Requirement 9: Technology Stack Compliance

**User Story:** As a project evaluator, I want the service to use Python and Flask, so that it meets the specified technology constraints.

#### Acceptance Criteria

1. THE Event_Sync_Service SHALL be implemented using Python 3.9 or higher as the programming language
2. THE REST_API SHALL use the Flask framework for HTTP request handling and declare Flask as a dependency in a requirements.txt or equivalent dependency manifest
3. THE Frontend SHALL be served through Flask using Jinja2 templates or static file serving, without requiring a separate frontend build step or runtime
