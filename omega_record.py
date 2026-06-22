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

OMEGA_SCHEMA_VERSION = "omega/1.0"
OMEGA_CONTRACTS_VERSION = "0.2.2"
RECORD_TYPE = "ProofCarryingEvalRecord"


def canonical_stringify(value) -> str:
    """Faithful port of omega-record.ts canonicalStringify.

    Sorted keys, undefined/None dropped from objects, JS-compatible number
    formatting (integers print without a trailing .0).
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_stringify(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = [k for k in sorted(value.keys()) if value[k] is not None]
        return "{" + ",".join(
            json.dumps(k, ensure_ascii=False) + ":" + canonical_stringify(value[k])
            for k in keys) + "}"
    raise TypeError(f"cannot canonicalise {type(value)}")


def sha256(value) -> str:
    s = value if isinstance(value, str) else canonical_stringify(value)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


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


def seal_omega(record) -> dict:
    """Attach the content_hash (over the canonical record) - the tamper-evident
    seal that also chains to previous_hash."""
    sealed = dict(record)
    sealed["content_hash"] = sha256(record)
    return sealed


def verify_omega(sealed) -> bool:
    claimed = sealed.get("content_hash")
    if not claimed:
        return False
    body = {k: v for k, v in sealed.items() if k != "content_hash"}
    return sha256(body) == claimed


def verify_chain(sealed_records) -> dict:
    """Verify each record's own seal AND that previous_hash links the chain."""
    ok = True
    prev = None
    for r in sealed_records:
        if not verify_omega(r):
            ok = False
        if r.get("previous_hash") != prev:
            ok = False
        prev = r.get("content_hash")
    return {"chain_intact": ok, "length": len(sealed_records),
            "head_hash": sealed_records[-1]["content_hash"] if sealed_records else None}
