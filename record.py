"""record.py - the proof-carrying record and its seal.

A proof-carrying record is the auditable evidence that an evaluation actually
happened against a real spec. It contains the request, the output, the
provable-property results WITH the exact constraints checked, the
judge-needed results clearly marked as non-proof, and a SHA-256 hash over the
canonical JSON of everything else.

The hash makes the record tamper-evident: re-canonicalising and re-hashing
detects any change to the sealed content. It is not a number on a dashboard;
it is a sealed bundle you can hand to an auditor.
"""

import hashlib
import json


def canonical_json(obj) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_record(case, decision, proof_results, judge_results, model_name,
                 output_source):
    return {
        "schema": "proof-carrying-eval/v1",
        "case_id": case["id"],
        "case_category": case["category"],
        "model_under_eval": model_name,
        "output_source": output_source,  # "model" or "planted-adversarial"
        "request": {
            "text": case["request_text"],
            "context": case["context"],
        },
        "spec": case["spec_dict"],
        "output": {
            "action": decision.action,
            "amount": decision.amount,
            "destination": decision.destination,
            "justification": decision.justification,
            "parse_ok": decision.parse_ok,
        },
        "provable_properties": {
            "checker": "z3",
            "method": "z3 decision procedure (refute negation of property)",
            "scope": "per-decision (single decision in isolation)",
            "is_proof": True,
            "spec_consistency": proof_results["spec_consistency"],
            "results": proof_results["properties"],
            "n_proven_holds": proof_results["n_proven_holds"],
            "n_proven_violated": proof_results["n_proven_violated"],
            "all_provable_passed": proof_results["all_provable_passed"],
        },
        "judge_needed_properties": {
            "method": "local LLM soft judge",
            "is_proof": False,
            "disclaimer": ("These properties are NOT formally checkable. The "
                           "results below are soft opinion and must not be read "
                           "as proofs."),
            "soft_judgment": judge_results,
        },
    }


def build_trace_record(session, steps_eval, lean_general, lean_trace,
                        model_name, output_source):
    """A proof-carrying record for a whole session (trace).

    steps_eval: list of per-step dicts with the decision and its Z3 per-decision
    proof results. lean_general: the once-proved inductive invariant. lean_trace:
    the per-trace Lean verdict.
    """
    all_z3_passed = all(s["z3_all_passed"] for s in steps_eval)
    return {
        "schema": "proof-carrying-eval/v1-trace",
        "session_id": session["id"],
        "session_category": session["category"],
        "description": session["description"],
        "model_under_eval": model_name,
        "output_source": output_source,  # "model" or "planted-adversarial"
        "session_spec": {
            "start_running_total": session["start_running_total"],
            "global_cap": session["global_cap"],
            "per_decision_spec_snapshot": session["step_spec"][1],
        },
        "steps": [
            {
                "index": s["index"],
                "request": s["request_text"],
                "decision": s["decision"],
                "spent_amount": s["spent_amount"],
                "z3_per_decision": {
                    "checker": "z3",
                    "is_proof": True,
                    "all_passed": s["z3_all_passed"],
                    "results": s["z3_results"],
                },
            }
            for s in steps_eval
        ],
        "per_decision_summary": {
            "checker": "z3",
            "is_proof": True,
            "all_per_decision_checks_passed": all_z3_passed,
            "note": ("each decision was checked in isolation against the "
                     "running-total snapshot it was handed"),
        },
        "trace_property": {
            "checker": "lean",
            "is_proof": True,
            "property_id": "prefix_running_total_cap",
            "general_invariant": lean_general,
            "trace_verdict": lean_trace,
            "note": ("the running-total cap across the ordered prefix is an "
                     "inductive invariant over the unbounded trace; Z3 decides "
                     "single decisions, Lean proves the sequence property"),
        },
    }


def seal(record) -> dict:
    """Attach a SHA-256 seal over the canonical JSON of the record."""
    body = canonical_json(record)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    sealed = dict(record)
    sealed["seal"] = {
        "alg": "sha256",
        "hash": digest,
        "canonical_bytes": len(body),
    }
    return sealed


def verify_seal(sealed) -> bool:
    """Recompute the hash over everything but the seal and compare."""
    if "seal" not in sealed:
        return False
    claimed = sealed["seal"]["hash"]
    body = {k: v for k, v in sealed.items() if k != "seal"}
    recomputed = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return claimed == recomputed
