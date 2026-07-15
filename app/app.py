"""Application entry point for the Event Sync Service.

Orchestrates the startup sequence: ingestion → reconciliation → Flask server.
Handles fatal startup errors by logging and exiting with a non-zero code.
"""

import sys
import logging

from flask import Flask

from app.ingestion import IngestionEngine, IngestionError
from app.reconciliation import ReconciliationEngine
from app.api import api_bp, init_api
from app.frontend import frontend_bp, init_frontend


def create_app(
    crm_path: str = "data/crm_events.json",
    cal_path: str = "data/calendar_events.json",
) -> Flask:
    """Create Flask app with ingested and reconciled data.

    Startup sequence:
    1. Ingest CRM records from crm_path
    2. Ingest Calendar records from cal_path
    3. Reconcile records into unified meetings
    4. Initialize Flask app and register blueprints

    Data is fully reconciled before the server accepts requests (eager ingestion).

    Args:
        crm_path: Path to the CRM events JSON file.
        cal_path: Path to the Calendar events JSON file.

    Returns:
        A configured Flask application ready to serve requests.

    Raises:
        SystemExit: On fatal ingestion or reconciliation errors.
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        # Step 1: Ingest CRM source data
        engine = IngestionEngine()
        crm_result = engine.ingest_crm(crm_path)

        # Step 2: Ingest Calendar source data
        cal_result = engine.ingest_calendar(cal_path)

        # Step 3: Reconcile records into unified meetings
        reconciler = ReconciliationEngine()
        meetings = reconciler.reconcile(crm_result.records, cal_result.records)

        logger.info(
            "Ingested %d CRM + %d Calendar records",
            len(crm_result.records),
            len(cal_result.records),
        )
        logger.info("Reconciled into %d unified meetings", len(meetings))

    except IngestionError as e:
        logger.error("Fatal startup error during ingestion: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error during startup: %s", e)
        sys.exit(1)

    # Step 4: Create Flask app and wire blueprints
    app = Flask(__name__, template_folder="../templates")

    # Initialize blueprints with reconciled data
    init_api(meetings)
    init_frontend(meetings)

    # Register blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(frontend_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
