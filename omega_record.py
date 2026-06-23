"""omega_record.py - wire proof-carrying eval results onto the OMEGA governed
record format.

The point: an eval result IS a governed, auditable record, not a hashed blob.
The verdict and its proof travel together. This mirrors the OMEGA record schema
in ~/Omega/omega-measure/lib/omega-record.ts:

  - canonical stringification (sorted keys, JS-compatible number formatting),
  - sha256 content hash,
  - hash CHAIN via previous_hash, so a run of eval records is tamper-evident as
    a sequence (a Guardian-style audit bundle), not just per record,
  - subject + outcome with the OMEGA gate_result vocabulary
    (COMMITTED | HELD | ESCALATED).

We extend the governed-decision anatomy with proof_evidence (the multi-checker
proofs, each tagged with its checker and is_proof) and an explicit boundary
block (proof-vs-intent gap, per-checker scope, residual, soft judgments).
"""

import hashlib
import json
from omega_seal import (canonical_stringify, sha256, seal, verify, verify_chain, seal_omega, verify_omega, verify_seal)  # ONE canonical provenance spine (replaces the local copy)

OMEGA_SCHEMA_VERSION = "omega/1.0"
OMEGA_CONTRACTS_VERSION = "0.2.2"
RECORD_TYPE = "ProofCarryingEvalRecord"




def gate_from_proofs(any_violation: bool, model_action: str) -> tuple:
    """Map proof outcomes to the OMEGA gate vocabulary.

    A proven violation HOLDS the decision (governance would not act on it). A
    clean proof set COMMITS it. If the model itself chose to escalate, that is
    surfaced as ESCALATED.
    """
    if any_violation:
        return "HELD", False
    if model_action == "escalate":
        return "ESCALATED", False
    return "COMMITTED", True


def build_omega_eval_record(*, record_id, created_at, domain, action_id, actor_id,
                            stakes, decision_text, authorising_entity, prior_state,
                            threshold_applied, action_taken, proof_evidence,
                            soft_judgment, boundary, previous_hash):
    """Assemble one governed proof-carrying eval record (unsealed)."""
    any_violation = any(
        (p.get("verdict") == "PROVEN_VIOLATED") for p in proof_evidence)
    gate_result, acted = gate_from_proofs(
        any_violation, action_taken.get("action", ""))

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
        "outcome": {
            "gate_result": gate_result,
            "gate_reason": ("a provable property was PROVEN_VIOLATED; the eval "
                            "gate HELD the decision"
                            if any_violation else
                            "all provable properties proved to hold across all "
                            "checkers"),
            "acted": acted,
        },
        # proof evidence: the multi-checker proofs travel WITH the verdict
        "proof_evidence": proof_evidence,
        # judge-needed properties remain soft and explicitly non-proof
        "soft_judgment": soft_judgment,
        # the stated boundary / residual: proof-vs-intent gap and per-checker scope
        "boundary": boundary,
        "previous_hash": previous_hash,
    }
    return record



