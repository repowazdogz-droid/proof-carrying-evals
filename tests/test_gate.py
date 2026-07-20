"""Regression tests for this repo's aggregate gate, now backed by the shared
omega_gate model. Proves the record's aggregate can never overstate the
evidence: a skipped/missing-tool/timeout/errored/unexecuted checker is never
COMMITTED; a partial run is COMMITTED_PARTIAL (acted False), never COMMITTED.

Run: python3 -m pytest tests/ -q   (or)   python3 tests/test_gate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omega_record import gate_from_evidence, checker_state, build_omega_eval_record  # noqa: E402


def _gate(ev, action="commit"):
    return gate_from_evidence(ev, action)


# ---- the five not-run cases: never COMMITTED ------------------------------
def test_skipped_never_committed():
    ev = [{"checker": "c", "available": False, "verdict": "SKIPPED"}]
    assert checker_state(ev[0]) == "not_run"
    assert _gate(ev) == ("INCONCLUSIVE", False)


def test_missing_tool_never_committed():
    assert _gate([{"checker": "c", "available": False}]) == ("INCONCLUSIVE", False)


def test_timeout_never_committed():
    assert _gate([{"checker": "c", "status": "timeout"}]) == ("INCONCLUSIVE", False)


def test_error_never_committed():
    assert _gate([{"checker": "c", "error": "boom"}]) == ("INCONCLUSIVE", False)


def test_unexecuted_never_committed():
    assert _gate([{"checker": "c"}]) == ("INCONCLUSIVE", False)


# ---- run outcomes ---------------------------------------------------------
def test_failure_holds():
    ev = [{"checker": "c", "available": True, "verdict": "PROVEN_VIOLATED", "passed": False}]
    assert _gate(ev) == ("HELD", False)


def test_success_commits():
    ev = [{"checker": "c", "available": True, "verified": True, "verdict": "PROVEN_SAFE"}]
    assert _gate(ev) == ("COMMITTED", True)


# ---- the core aggregate honesty case --------------------------------------
def test_pass_plus_skip_is_partial_not_committed():
    ev = [
        {"checker": "z3", "available": True, "verified": True, "verdict": "PROVEN_HOLDS"},
        {"checker": "dreal", "available": False, "verdict": "SKIPPED"},
    ]
    g, acted = _gate(ev)
    assert g == "COMMITTED_PARTIAL"
    assert g != "COMMITTED"
    assert acted is False


def test_all_ran_and_passed_commits():
    ev = [{"checker": c, "available": True, "verified": True} for c in ("z3", "lean", "tla")]
    assert _gate(ev) == ("COMMITTED", True)


def test_failure_dominates_partial():
    ev = [
        {"checker": "z3", "available": True, "verified": True},
        {"checker": "dreal", "available": False, "verdict": "SKIPPED"},
        {"checker": "tla", "available": True, "verified": False},
    ]
    assert _gate(ev) == ("HELD", False)


# ---- end-to-end through build_omega_eval_record ---------------------------
def _record(ev, action):
    return build_omega_eval_record(
        record_id="t", created_at="2026-01-01T00:00:00Z", domain="d", action_id="a",
        actor_id="x", stakes="s", decision_text="dt", authorising_entity="ae",
        prior_state="ps", threshold_applied="ta", action_taken={"action": action},
        proof_evidence=ev, soft_judgment={}, boundary={}, previous_hash=None)


def test_record_partial_never_committed():
    rec = _record([
        {"checker": "z3", "available": True, "verified": True},
        {"checker": "dreal", "available": False, "verdict": "SKIPPED"},
    ], "commit")
    o = rec["outcome"]
    assert o["aggregate_state"] == "PARTIAL"
    assert o["gate_result"] == "COMMITTED_PARTIAL"
    assert o["acted"] is False
    assert o["components_not_run"] == ["dreal"]


def test_record_all_pass_committed():
    rec = _record([{"checker": "z3", "available": True, "verified": True}], "commit")
    assert rec["outcome"]["aggregate_state"] == "VERIFIED"
    assert rec["outcome"]["gate_result"] == "COMMITTED"
    assert rec["outcome"]["acted"] is True


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn(); print("PASS", fn.__name__)
        except Exception:
            failed += 1; print("FAIL", fn.__name__); traceback.print_exc()
    print("\n%d passed, %d failed" % (len(fns) - failed, failed))
    sys.exit(1 if failed else 0)
