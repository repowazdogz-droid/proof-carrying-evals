"""lean_checker.py - the second checker (Lean 4), behind the same abstraction.

Z3 proves per-decision arithmetic/boolean properties. Lean proves what Z3
structurally cannot: an inductive invariant over an unbounded SEQUENCE of
decisions. We do two things:

  1. prove_general_invariant() runs lean/Trace.lean ONCE. That file proves, for
     ALL traces of ANY length, that the prefix running-total monitor is sound
     (monitor_sound, by induction), plus per_step_insufficient: a kernel-checked
     witness that per-decision safety does not imply trace safety. This is the
     reusable theorem, and it is the honest statement of what Lean proves.

  2. prove_trace(start, cap, amounts) certifies the verdict for ONE concrete
     trace. The harness computes the expected boolean, then Lean's kernel
     certifies it via `decide` on the same `allPrefixesWithinCap` function. The
     verdict is accepted ONLY if Lean compiles the matching theorem.

Both run plain `lean` on a self-contained core-Lean file (no Mathlib, no lake),
which is why it is fast. #print axioms is captured so the record can state the
proof is axiom-clean.
"""

import os
import re
import subprocess

LEAN_BIN = os.path.expanduser("~/.elan/bin/lean")
LEAN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lean")
TRACE_FILE = os.path.join(LEAN_DIR, "Trace.lean")

# The shared definition block. Kept identical between the general-invariant file
# and the generated per-trace files so the verdict is certified against exactly
# the function the invariant is proved about.
LEAN_DEFS = """namespace PCEval

def prefixWithin (cap : Nat) : Nat -> List Nat -> Bool
  | _,   []        => true
  | run, a :: rest =>
      let run' := run + a
      if run' <= cap then prefixWithin cap run' rest else false

def allPrefixesWithinCap (start cap : Nat) (trace : List Nat) : Bool :=
  prefixWithin cap start trace
"""


def lean_available():
    return os.path.exists(LEAN_BIN)


def _run_lean(path, timeout=120):
    try:
        p = subprocess.run([LEAN_BIN, path], capture_output=True, text=True,
                           timeout=timeout, cwd=LEAN_DIR)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return -1, "", f"{e}"


def _axiom_report(stdout):
    lines = [ln.strip() for ln in stdout.splitlines()
             if "axiom" in ln.lower() or "does not depend" in ln.lower()]
    clean = all("does not depend on any axioms" in ln for ln in lines) and bool(lines)
    return {"lines": lines, "axiom_clean": clean}


def prove_general_invariant():
    """Run the reusable Trace.lean once. Returns the verdict for the general,
    all-traces inductive theorem and the per-step-insufficient witness."""
    if not lean_available():
        return {"available": False}
    rc, out, err = _run_lean(TRACE_FILE)
    ok = rc == 0
    return {
        "available": True,
        "file": "lean/Trace.lean",
        "compiled": ok,
        "theorems": ["monitor_sound", "per_step_insufficient"],
        "statement": ("for ALL traces of ANY length, the prefix running-total "
                      "monitor is sound (proved by induction); and per-decision "
                      "safety does not imply trace safety (kernel-checked witness)"),
        "axioms": _axiom_report(out),
        "stderr": err.strip()[:500],
    }


def eval_prefix(start, cap, amounts):
    """Pure-Python mirror of allPrefixesWithinCap, used to decide which theorem
    to ask Lean to certify and to locate the breaching prefix."""
    run = start
    for i, a in enumerate(amounts):
        run += a
        if run > cap:
            return False, i, run
    return True, None, run


def prove_trace(start, cap, amounts, label="trace"):
    """Kernel-certify the prefix-cap verdict for one concrete trace."""
    if not lean_available():
        return {"checker": "lean", "available": False,
                "verdict": "UNKNOWN", "passed": None}

    # Lean uses Nat: amounts must be non-negative integers. Z3 already proves
    # per-decision non-negativity; if something slipped through we say so.
    if any((not float(a).is_integer()) or a < 0 for a in amounts):
        return {"checker": "lean", "available": True,
                "verdict": "NOT_ENCODABLE",
                "passed": None,
                "note": ("trace contains a negative or non-integer amount; the "
                         "Nat trace model cannot encode it (z3 catches this "
                         "per-decision)"),
                "amounts": amounts}

    ints = [int(a) for a in amounts]
    holds, breach_idx, final_run = eval_prefix(int(start), int(cap), ints)

    list_lit = "[" + ", ".join(str(x) for x in ints) + "]"
    expected = "true" if holds else "false"
    thm_name = "trace_holds" if holds else "trace_breaches"
    src = (
        LEAN_DEFS
        + f"\ntheorem {thm_name} : allPrefixesWithinCap {int(start)} {int(cap)} "
        + f"{list_lit} = {expected} := by decide\n"
        + f"#print axioms {thm_name}\n\nend PCEval\n"
    )
    safe_label = re.sub(r"[^A-Za-z0-9_]", "_", label)
    path = os.path.join(LEAN_DIR, f"trace_{safe_label}.lean")
    with open(path, "w") as f:
        f.write(src)

    rc, out, err = _run_lean(path)
    ok = rc == 0
    verdict = "UNKNOWN"
    passed = None
    if ok:
        verdict = "PROVEN_HOLDS" if holds else "PROVEN_VIOLATED"
        passed = holds
    return {
        "checker": "lean",
        "available": True,
        "compiled": ok,
        "verdict": verdict,
        "passed": passed,
        "theorem": thm_name,
        "lean_proposition": f"allPrefixesWithinCap {int(start)} {int(cap)} {list_lit} = {expected}",
        "lean_file": f"lean/{os.path.basename(path)}",
        "start_running_total": int(start),
        "global_cap": int(cap),
        "trace_amounts": ints,
        "breach_prefix_index": breach_idx,
        "running_total_at_breach": final_run if not holds else None,
        "axioms": _axiom_report(out),
        "stderr": err.strip()[:500],
    }
