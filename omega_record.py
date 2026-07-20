"""omega_record.py - wire proof-carrying eval results onto the OMEGA governed
record format.

The verdict and its proof travel together: canonical stringification, sha256
content hash, hash CHAIN via previous_hash, and an outcome block using the OMEGA
gate vocabulary.

AGGREGATE SEMANTICS (2026-07-20): the aggregate verdict is computed by the ONE
shared model `omega_gate`, whose governing invariant is:

    No aggregate status may be strictly stronger than its weakest required
    component.

A component that did not execute (skipped / unavailable / errored / timed-out /
unexecuted) can never be recorded as verified; it caps the aggregate at PARTIAL
(gate_result COMMITTED_PARTIAL) or, if nothing ran, INCONCLUSIVE. `COMMITTED`
(aggregate_state VERIFIED, acted=True) is emitted only when EVERY component
executed and passed. See the omega_gate package for the full model and tests.
"""

from omega_seal import (canonical_stringify, sha256, seal, verify, verify_chain,  # noqa: F401
                        seal_omega, verify_omega, verify_seal)  # ONE provenance spine
import omega_gate  # ONE shared aggregate-state model

OMEGA_SCHEMA_VERSION = "omega/1.0"
OMEGA_CONTRACTS_VERSION = "0.2.2"
RECORD_TYPE = "ProofCarryingEvalRecord"


# ---- backwards-compatible thin wrappers over the shared model -------------
def checker_state(p):
    """Classify one proof-evidence entry: 'passed' | 'failed' | 'violated' |
    'not_run'. Delegates to omega_gate.component_state."""
    return omega_gate.component_state(p)


def gate_from_evidence(proof_evidence, model_action=None):
    """Return (gate_result, acted) for the evidence set, via omega_gate.

    gate_result in {COMMITTED, COMMITTED_PARTIAL, INCONCLUSIVE, HELD, ESCALATED};
    acted is True only when every component executed and passed (VERIFIED).
    """
    a = omega_gate.aggregate(proof_evidence, model_action)
    return a.gate_result, a.acted


def build_omega_eval_record(*, record_id, created_at, domain, action_id, actor_id,
                            stakes, decision_text, authorising_entity, prior_state,
                            threshold_applied, action_taken, proof_evidence,
                            soft_judgment, boundary, previous_hash):
    """Assemble one governed proof-carrying eval record (unsealed).

    The outcome block carries BOTH the honest `aggregate_state`
    (VERIFIED/PARTIAL/INCONCLUSIVE/FAILED) and the legacy `gate_result`, plus a
    component run-accounting so a reader can never conclude more verification
    occurred than the evidence shows.
    """
    agg = omega_gate.aggregate(proof_evidence, action_taken.get("action", ""))
    outcome = agg.to_outcome()

    record = {
        "record_type": RECORD_TYPE,
        "schema_version": OMEGA_SCHEMA_VERSION,
        "contracts_version": OMEGA_CONTRACTS_VERSION,
        "record_id": record_id,
        "created_at": created_at,
        "subject": {
            "domain": domain,
            "action": action_id,
            "actor_id": actor_id,
            "stakes": stakes,
        },
        "governed_decision": {
            "decision": decision_text,
            "authorising_entity": authorising_entity,
            "prior_state": prior_state,
            "threshold_applied": threshold_applied,
            "action_taken": action_taken,
        },
        "outcome": outcome,
        # proof evidence: the multi-checker proofs travel WITH the verdict
        "proof_evidence": proof_evidence,
        # judge-needed properties remain soft and explicitly non-proof
        "soft_judgment": soft_judgment,
        # the stated boundary / residual: proof-vs-intent gap and per-checker scope
        "boundary": boundary,
        "previous_hash": previous_hash,
    }
    return record
