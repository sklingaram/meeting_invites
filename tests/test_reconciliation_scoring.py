"""Unit tests for ReconciliationEngine match confidence scoring (Task 4.1)."""

from datetime import datetime

import pytest

from app.models import NormalizedRecord
from app.reconciliation import ReconciliationEngine


@pytest.fixture
def engine():
    return ReconciliationEngine()


class TestDateProximityScore:
    """Tests for _date_proximity_score()."""

    def test_identical_times_returns_1(self, engine):
        dt = datetime(2024, 1, 15, 10, 0)
        assert engine._date_proximity_score(dt, dt) == 1.0

    def test_15_minutes_apart_returns_0_5(self, engine):
        dt_a = datetime(2024, 1, 15, 10, 0)
        dt_b = datetime(2024, 1, 15, 10, 15)
        assert engine._date_proximity_score(dt_a, dt_b) == 0.5

    def test_30_minutes_apart_returns_0(self, engine):
        dt_a = datetime(2024, 1, 15, 10, 0)
        dt_b = datetime(2024, 1, 15, 10, 30)
        assert engine._date_proximity_score(dt_a, dt_b) == 0.0

    def test_beyond_30_minutes_returns_0(self, engine):
        dt_a = datetime(2024, 1, 15, 10, 0)
        dt_b = datetime(2024, 1, 15, 11, 0)
        assert engine._date_proximity_score(dt_a, dt_b) == 0.0

    def test_none_first_returns_0(self, engine):
        assert engine._date_proximity_score(None, datetime(2024, 1, 1, 10, 0)) == 0.0

    def test_none_second_returns_0(self, engine):
        assert engine._date_proximity_score(datetime(2024, 1, 1, 10, 0), None) == 0.0

    def test_both_none_returns_0(self, engine):
        assert engine._date_proximity_score(None, None) == 0.0

    def test_order_independent(self, engine):
        dt_a = datetime(2024, 1, 15, 10, 0)
        dt_b = datetime(2024, 1, 15, 10, 20)
        assert engine._date_proximity_score(dt_a, dt_b) == engine._date_proximity_score(dt_b, dt_a)


class TestAttendeeOverlapScore:
    """Tests for _attendee_overlap_score()."""

    def test_identical_sets_returns_1(self, engine):
        s = {"alice@ex.com", "bob@ex.com"}
        assert engine._attendee_overlap_score(s, s) == 1.0

    def test_no_overlap_returns_0(self, engine):
        assert engine._attendee_overlap_score({"alice@ex.com"}, {"bob@ex.com"}) == 0.0

    def test_both_empty_returns_0(self, engine):
        assert engine._attendee_overlap_score(set(), set()) == 0.0

    def test_case_insensitive(self, engine):
        assert engine._attendee_overlap_score({"Alice@EX.com"}, {"alice@ex.com"}) == 1.0

    def test_partial_overlap(self, engine):
        # {a, b} & {b, c} => intersection=1, union=3 => 1/3
        score = engine._attendee_overlap_score({"a", "b"}, {"b", "c"})
        assert abs(score - 1 / 3) < 1e-9

    def test_one_empty_returns_0(self, engine):
        assert engine._attendee_overlap_score({"alice@ex.com"}, set()) == 0.0


class TestSubjectSimilarityScore:
    """Tests for _subject_similarity_score()."""

    def test_identical_returns_1(self, engine):
        assert engine._subject_similarity_score("Weekly Meeting", "Weekly Meeting") == 1.0

    def test_empty_first_returns_0(self, engine):
        assert engine._subject_similarity_score("", "Something") == 0.0

    def test_empty_second_returns_0(self, engine):
        assert engine._subject_similarity_score("Something", "") == 0.0

    def test_partial_similarity(self, engine):
        score = engine._subject_similarity_score("Q4 Portfolio Review", "Portfolio Review Q4")
        assert 0.0 < score < 1.0

    def test_completely_different(self, engine):
        score = engine._subject_similarity_score("AAAA", "ZZZZ")
        assert score == 0.0


class TestComputeMatchConfidence:
    """Tests for compute_match_confidence()."""

    def test_perfect_match_returns_1(self, engine):
        rec_a = NormalizedRecord(
            source_id="CRM-1", source="crm", title="Weekly Sync",
            start_time=datetime(2024, 1, 1, 10, 0),
            attendees=["alice@ex.com", "bob@ex.com"],
        )
        rec_b = NormalizedRecord(
            source_id="CAL-1", source="calendar", title="Weekly Sync",
            start_time=datetime(2024, 1, 1, 10, 0),
            attendees=["alice@ex.com", "bob@ex.com"],
        )
        assert engine.compute_match_confidence(rec_a, rec_b) == 1.0

    def test_no_match_below_threshold(self, engine):
        rec_a = NormalizedRecord(
            source_id="CRM-2", source="crm", title="Budget Planning",
            start_time=datetime(2024, 6, 15, 14, 0),
            attendees=["dave@ex.com"],
        )
        rec_b = NormalizedRecord(
            source_id="CAL-2", source="calendar", title="Sprint Retro",
            start_time=datetime(2024, 1, 1, 8, 0),
            attendees=["eve@ex.com"],
        )
        confidence = engine.compute_match_confidence(rec_a, rec_b)
        assert confidence < engine.CONFIDENCE_THRESHOLD

    def test_confidence_in_bounds(self, engine):
        rec_a = NormalizedRecord(
            source_id="CRM-3", source="crm", title="Standup",
            start_time=datetime(2024, 3, 1, 9, 0),
            attendees=["x@ex.com"],
        )
        rec_b = NormalizedRecord(
            source_id="CAL-3", source="calendar", title="Daily Standup",
            start_time=datetime(2024, 3, 1, 9, 10),
            attendees=["x@ex.com", "y@ex.com"],
        )
        confidence = engine.compute_match_confidence(rec_a, rec_b)
        assert 0.0 <= confidence <= 1.0

    def test_weighted_formula(self, engine):
        """Verify the weighted sum formula: 0.4*date + 0.3*attendee + 0.3*subject."""
        rec_a = NormalizedRecord(
            source_id="CRM-4", source="crm", title="Review",
            start_time=datetime(2024, 1, 1, 10, 0),
            attendees=["a@x.com", "b@x.com"],
        )
        rec_b = NormalizedRecord(
            source_id="CAL-4", source="calendar", title="Review",
            start_time=datetime(2024, 1, 1, 10, 15),  # 15 min => date_score=0.5
            attendees=["a@x.com", "b@x.com"],  # identical => attendee_score=1.0
        )
        # date_score = 0.5, attendee_score = 1.0, subject_score = 1.0
        # confidence = 0.4*0.5 + 0.3*1.0 + 0.3*1.0 = 0.2 + 0.3 + 0.3 = 0.8
        confidence = engine.compute_match_confidence(rec_a, rec_b)
        assert abs(confidence - 0.8) < 1e-9
