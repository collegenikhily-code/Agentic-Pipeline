"""M1 unit tests for state machine.

No PostgreSQL required - tests logic only.
"""

import pytest
from seo_aeo_geo_pipeline.state import StateMachine, can_transition


class TestStateMachine:
    """State machine transition logic tests."""

    def test_valid_forward_transitions(self):
        """M1: Valid forward state transitions are allowed."""
        # DISCOVERED → RESEARCHING → QUALIFIED → SPEC_READY → GENERATING → VALIDATING
        # → REPAIRING → APPROVED → PUBLISHED
        assert StateMachine.can_transition("DISCOVERED", "RESEARCHING") == True
        assert StateMachine.can_transition("RESEARCHING", "QUALIFIED") == True
        assert StateMachine.can_transition("QUALIFIED", "SPEC_READY") == True
        assert StateMachine.can_transition("SPEC_READY", "GENERATING") == True
        assert StateMachine.can_transition("GENERATING", "VALIDATING") == True
        assert StateMachine.can_transition("VALIDATING", "APPROVED") == True
        assert StateMachine.can_transition("APPROVED", "PUBLISHED") == True

    def test_failure_transitions_from_qualified(self):
        """M1: From QUALIFIED, can transition to failure states."""
        assert StateMachine.can_transition("QUALIFIED", "REJECTED") == True
        assert StateMachine.can_transition("QUALIFIED", "NOINDEX") == True
        assert StateMachine.can_transition("QUALIFIED", "FAILED") == True

    def test_published_is_terminal(self):
        """M1: PUBLISHED is terminal - no outgoing transitions allowed."""
        # PUBLISHED should NOT be able to transition to any other state
        assert StateMachine.can_transition("PUBLISHED", "REJECTED") == False
        assert StateMachine.can_transition("PUBLISHED", "GENERATING") == False
        assert StateMachine.can_transition("PUBLISHED", "NOINDEX") == False
        assert StateMachine.can_transition("PUBLISHED", "QUALIFIED") == False
        assert StateMachine.can_transition("PUBLISHED", "DISCOVERED") == False

    def test_failure_states_terminal(self):
        """M1: Failure states have no outgoing transitions to quality states."""
        for failure in ["REJECTED", "NOINDEX", "FAILED"]:
            # These should not transition to quality/forward states
            assert StateMachine.can_transition("REJECTED", "QUALIFIED") == False
            assert StateMachine.can_transition("NOINDEX", "QUALIFIED") == False
            assert StateMachine.can_transition("FAILED", "QUALIFIED") == False


def test_can_transition_basic():
    """Basic can_transition test."""
    assert can_transition("DISCOVERED", "RESEARCHING") == True
    assert can_transition("DISCOVERED", "REJECTED") == True
    assert can_transition("PUBLISHED", "REJECTED") == False
    assert can_transition("PUBLISHED", "GENERATING") == False