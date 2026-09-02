"""omega_gate - the ONE shared aggregate-state model for the OMEGA verification
tower.

GOVERNING INVARIANT
    No aggregate status may be strictly stronger than its weakest required
    component. A component that did not execute (skipped / unavailable / errored
    / timed-out / not-executed) caps the aggregate strictly below "fully
    verified"; a component that ran and failed caps it at "failed".

Every verification repository (single-paradigm checkers and the multi-paradigm
engines) computes its aggregate verdict from THIS module, so the semantics are
identical everywhere.

FOUR AGGREGATE STATES  (weakest -> strongest)
    FAILED        a required component ran and its property did NOT hold
    INCONCLUSIVE  no component produced a positive proof (evidence absent)
    PARTIAL       every component that executed passed, but >= 1 required
                  component did NOT execute (only the executed checkers passed)
    VERIFIED      every required component executed and passed

Legacy OMEGA gate_result mapping (records keep BOTH aggregate_state and
gate_result for continuity):
    VERIFIED     -> COMMITTED   (acted=True)   [or ESCALATED if the model escalated]
    PARTIAL      -> COMMITTED_PARTIAL (acted=False)
    INCONCLUSIVE -> INCONCLUSIVE (acted=False)
    FAILED       -> HELD        (acted=False)

acted is True ONLY for VERIFIED. Nothing acts on partial or absent evidence.

CONSUMER CONTRACT (read before parsing gate_result anywhere)
    - Compare `gate_result` with EXACT EQUALITY only:  gate_result == "COMMITTED".
    - NEVER use substring or prefix matching. `COMMITTED_PARTIAL` lexically starts
      with `COMMITTED`, so `"COMMITTED" in gate_result` or
      `gate_result.startswith("COMMIT")` would WRONGLY treat a partial (or
      inconclusive-of-committed) result as a full commit.
    - Prefer `aggregate_state` (VERIFIED / PARTIAL / INCONCLUSIVE / FAILED) as the
      canonical semantic state; `gate_result` is the legacy compatibility label.
    - `acted == True` means, and means ONLY, that every required component executed
      and passed (aggregate_state == VERIFIED). Use `acted` as the machine-readable
      "fully verified" signal; it is never True for PARTIAL, INCONCLUSIVE or FAILED.
"""

# ---- aggregate states -----------------------------------------------------
VERIFIED = "VERIFIED"
PARTIAL = "PARTIAL"
INCONCLUSIVE = "INCONCLUSIVE"
FAILED = "FAILED"

# ordering for the invariant (higher = strictly stronger evidence)
_STRENGTH = {FAILED: 0, INCONCLUSIVE: 1, PARTIAL: 2, VERIFIED: 3}

# ---- per-component classifications ---------------------------------------
C_PASSED = "passed"    # ran and its property held
C_FAILED = "failed"    # ran and its property did NOT hold
C_VIOLATED = "violated"  # ran and proved a violation (a kind of failed)
C_NOT_RUN = "not_run"  # skipped / unavailable / errored / timed-out / unexecuted

# component strength, mapped onto the aggregate scale, for the invariant check
_COMPONENT_CAP = {
    C_PASSED: VERIFIED,       # a passed component permits (does not force) VERIFIED
    C_NOT_RUN: PARTIAL,       # a not-run component caps the aggregate at PARTIAL
    C_FAILED: FAILED,         # a failed component caps the aggregate at FAILED
    C_VIOLATED: FAILED,
}

# gate_result vocabulary (legacy OMEGA record field)
GATE = {
    VERIFIED: "COMMITTED",
    PARTIAL: "COMMITTED_PARTIAL",
    INCONCLUSIVE: "INCONCLUSIVE",
    FAILED: "HELD",
}

_NONRUN_VERDICTS = {"SKIPPED", "UNAVAILABLE", "NOT_RUN", "NOTRUN", "UNEXECUTED",
                    "ERROR", "TIMEOUT", "N/A", "NA", "NONE"}
_NONRUN_STATUSES = {"skipped", "unavailable", "not_run", "notrun", "unexecuted",
                    "error", "timeout"}
_PASS_VERDICTS = {"PROVEN_SAFE", "PROVEN_HOLDS", "PROVEN", "REFINES",
                  "HELD_PROVEN", "VERIFIED", "PASS", "PASSED", "SAFE", "UNSAT_SAFE"}
_FAIL_VERDICTS = {"PROVEN_VIOLATED", "VIOLATED", "ALARM_RAISED", "DEFECT_FOUND",
                  "FAILED", "FAIL", "NOT_PROVEN", "UNSAFE"}


def component_state(p):
    """Classify one component/checker result dict into C_PASSED / C_FAILED /
    C_VIOLATED / C_NOT_RUN.

    Precedence is deliberate: a NOT-RUN signal is checked FIRST, so a skipped or
    errored checker can never be misread as a pass or a fail. Only after a
    component is known to have executed do we consult its success signal
    (`verified` / `passed` booleans preferred; verdict string as fallback).
    A component with no definite signal is treated as NOT_RUN — we never invent
    a pass.
    """
    if not isinstance(p, dict):
        return C_NOT_RUN

    verdict = p.get("verdict")
    if verdict is None:
        verdict = p.get("result")
    if verdict is None:
        verdict = p.get("headline_verdict")
    vU = verdict.upper() if isinstance(verdict, str) else None

    # 1) did it NOT run?  (checked before any pass/fail interpretation)
    if p.get("available") is False:
        return C_NOT_RUN
    if p.get("exercised") is False:
        return C_NOT_RUN
    if vU in _NONRUN_VERDICTS:
        return C_NOT_RUN
    if str(p.get("status", "")).lower() in _NONRUN_STATUSES:
        return C_NOT_RUN
    if p.get("error") or p.get("timed_out") or p.get("skipped_reason"):
        return C_NOT_RUN

    # 2) it executed -> classify by explicit success signal first
    if p.get("verified") is True or p.get("passed") is True:
        return C_PASSED
    if p.get("verified") is False or p.get("passed") is False:
        return C_FAILED

    # 3) verdict-string fallback
    if vU in _PASS_VERDICTS:
        return C_PASSED
    if vU in _FAIL_VERDICTS:
        return C_VIOLATED if vU in ("PROVEN_VIOLATED", "VIOLATED") else C_FAILED

    # 4) no definite signal -> treat as not executed (never invent a pass)
    return C_NOT_RUN


def _name(p):
    for k in ("checker", "paradigm", "id", "title", "name"):
        v = p.get(k) if isinstance(p, dict) else None
        if v:
            return v
    return "component"


class Aggregate:
    """Result of an aggregate evaluation."""

    __slots__ = ("state", "gate_result", "acted", "total", "passed",
                 "not_run", "failed", "reason", "model_action")

    def __init__(self, state, gate_result, acted, total, passed, not_run,
                 failed, reason, model_action):
        self.state = state
        self.gate_result = gate_result
        self.acted = acted
        self.total = total
        self.passed = passed          # count
        self.not_run = not_run        # list of component names
        self.failed = failed          # list of component names
        self.reason = reason
        self.model_action = model_action

    def to_outcome(self):
        """Dict for embedding in an OMEGA record's `outcome` block."""
        return {
            "aggregate_state": self.state,
            "gate_result": self.gate_result,
            "gate_reason": self.reason,
            "acted": self.acted,
            "components_total": self.total,
            "components_passed": self.passed,
            "components_not_run": self.not_run,
            "components_failed": self.failed,
        }

    def __repr__(self):
        return ("Aggregate(state=%s gate=%s acted=%s passed=%d/%d not_run=%s failed=%s)"
                % (self.state, self.gate_result, self.acted, self.passed,
                   self.total, self.not_run, self.failed))


def aggregate(evidence, model_action=None):
    """Compute the honest aggregate over a list of component result dicts.

    Applies the governing invariant: the aggregate is never strictly stronger
    than its weakest component.

      any component FAILED/VIOLATED                 -> FAILED
      else zero components passed                   -> INCONCLUSIVE
      else any component NOT_RUN                    -> PARTIAL
      else (all executed and passed)               -> VERIFIED

    model_action == "escalate" is honoured only when the evidence is otherwise
    VERIFIED (you cannot escalate a decision whose evidence is incomplete).
    """
    evidence = list(evidence or [])
    states = [component_state(p) for p in evidence]
    failed_names = [_name(p) for p, s in zip(evidence, states)
                    if s in (C_FAILED, C_VIOLATED)]
    notrun_names = [_name(p) for p, s in zip(evidence, states) if s == C_NOT_RUN]
    n_pass = sum(1 for s in states if s == C_PASSED)

    if failed_names:
        state = FAILED
    elif n_pass == 0:
        state = INCONCLUSIVE
    elif notrun_names:
        state = PARTIAL
    else:
        state = VERIFIED

    gate = GATE[state]
    acted = state == VERIFIED
    if state == VERIFIED and model_action == "escalate":
        gate, acted = "ESCALATED", False

    if state == FAILED:
        reason = ("FAILED: %d component(s) ran and did not hold (%s); the "
                  "aggregate is capped at its weakest component"
                  % (len(failed_names), ", ".join(map(str, failed_names))))
    elif state == INCONCLUSIVE:
        reason = ("INCONCLUSIVE: no component produced a positive proof (%d of "
                  "%d did not run: %s); evidence is absent"
                  % (len(notrun_names), len(evidence),
                     ", ".join(map(str, notrun_names)) or "none"))
    elif state == PARTIAL:
        reason = ("PARTIAL: the %d component(s) that executed passed, but %d "
                  "required component(s) did NOT run (%s); the aggregate is "
                  "capped below VERIFIED because a not-run component verifies "
                  "nothing" % (n_pass, len(notrun_names),
                               ", ".join(map(str, notrun_names))))
    else:
        reason = ("VERIFIED: every one of the %d required components executed "
                  "and passed" % len(evidence))

    return Aggregate(state, gate, acted, len(evidence), n_pass, notrun_names,
                     failed_names, reason, model_action)


def invariant_holds(evidence, model_action=None):
    """True iff the computed aggregate is NOT strictly stronger than the weakest
    component. Used by tests; the property it checks is the module's contract.
    """
    agg = aggregate(evidence, model_action)
    if not evidence:
        return agg.state in (INCONCLUSIVE,)
    caps = [_COMPONENT_CAP[component_state(p)] for p in evidence]
    weakest_cap = min(caps, key=lambda s: _STRENGTH[s])
    # VERIFIED via escalate maps to ESCALATED/acted False, still not stronger.
    return _STRENGTH[agg.state] <= _STRENGTH[weakest_cap]
