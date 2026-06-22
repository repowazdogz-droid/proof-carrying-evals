"""prover.py - the proof layer (swappable: Z3 today, Lean/TLA+ later).

For each PROVABLE property we do a real decision procedure, not an evaluation:
we declare symbolic decision variables, bind them to the concrete decision,
and ask the solver to refute the property. If the negation is unsatisfiable,
the property is PROVEN to hold. If it is satisfiable, the property is PROVEN
violated and the solver hands back a witnessing assignment.

Every result carries the exact assertions the solver checked, so the verdict
is auditable rather than a number on a dashboard.

This is the decidable fragment. Temporal or inductive properties would need a
different backend (Lean, TLA+); the interface here - prove_decision returning
per-property verdicts plus the constraints checked - is what a different
backend would implement.
"""

import z3

from properties import (
    PROVABLE_PROPERTIES,
    GovSpec,
    Decision,
    action_code,
    MALFORMED_CODE,
)


def _destination_code(spec: GovSpec, decision: Decision) -> int:
    if decision.destination is None:
        return MALFORMED_CODE
    try:
        return spec.approved_destinations.index(decision.destination)
    except ValueError:
        return MALFORMED_CODE


def _mk_vars():
    return {
        "a": z3.Int("action_code"),
        "m": z3.Real("amount"),
        "d": z3.Int("dest_code"),
    }


def prove_property(spec: GovSpec, decision: Decision, prop) -> dict:
    """Prove a single property holds or is violated for the concrete decision."""
    v = _mk_vars()
    a_val = action_code(decision.action)
    m_val = z3.RealVal(str(decision.amount))
    d_val = _destination_code(spec, decision)

    binding = [v["a"] == a_val, v["m"] == m_val, v["d"] == d_val]
    expr = prop["build"](spec, v)

    s = z3.Solver()
    for b in binding:
        s.add(b)
    # Prove the property by refuting its negation.
    s.add(z3.Not(expr))

    result = s.check()
    constraints = [c.sexpr() for c in s.assertions()]

    out = {
        "id": prop["id"],
        "description": prop["description"],
        "checker": prop.get("checker", "z3"),
        "scope": prop.get("scope", "decision"),
        "property_smt": expr.sexpr(),
        "bound_values": {
            "action_code": a_val,
            "amount": str(decision.amount),
            "dest_code": d_val,
        },
        "checked_assertions": constraints,
        "solver_result_on_negation": str(result),
    }

    if result == z3.unsat:
        out["verdict"] = "PROVEN_HOLDS"
        out["passed"] = True
        out["witness"] = None
    elif result == z3.sat:
        model = s.model()
        out["verdict"] = "PROVEN_VIOLATED"
        out["passed"] = False
        out["witness"] = {str(d): str(model[d]) for d in model.decls()}
    else:
        out["verdict"] = "UNKNOWN"
        out["passed"] = None
        out["witness"] = None
    return out


def spec_consistency(spec: GovSpec) -> dict:
    """Prove the spec is not vacuous: there exists SOME compliant decision.

    If this is unsat the spec is self-contradictory and 'provably compliant'
    would be meaningless, so we surface it.
    """
    v = _mk_vars()
    s = z3.Solver()
    # a valid action in range, amount real, dest in range or absent
    s.add(z3.Or(*[v["a"] == i for i in range(len(__import__("properties").ACTIONS))]))
    for prop in PROVABLE_PROPERTIES:
        s.add(prop["build"](spec, v))
    r = s.check()
    out = {"result": str(r), "checked_assertions": [c.sexpr() for c in s.assertions()]}
    if r == z3.sat:
        out["consistent"] = True
        m = s.model()
        out["example_compliant_assignment"] = {
            str(d): str(m[d]) for d in m.decls()
        }
    else:
        out["consistent"] = False
        out["example_compliant_assignment"] = None
    return out


def prove_decision(spec: GovSpec, decision: Decision) -> dict:
    """Run all provable properties against one decision."""
    results = [prove_property(spec, decision, p) for p in PROVABLE_PROPERTIES]
    n_violated = sum(1 for r in results if r["verdict"] == "PROVEN_VIOLATED")
    n_holds = sum(1 for r in results if r["verdict"] == "PROVEN_HOLDS")
    return {
        "spec_consistency": spec_consistency(spec),
        "properties": results,
        "n_properties": len(results),
        "n_proven_holds": n_holds,
        "n_proven_violated": n_violated,
        "all_provable_passed": n_violated == 0,
    }
