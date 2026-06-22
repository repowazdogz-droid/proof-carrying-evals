"""tla_checker.py - the third checker (TLA+ / TLC), behind the same abstraction.

Z3 decides one decision. Lean proves an inductive invariant over one trace.
TLC proves a CONCURRENCY/temporal invariant over ALL interleavings of decisions
from multiple agents sharing state - the class where the violation appears only
under a particular interleaving, which is awkward for a single Z3 query and for
induction over one agent's trace.

The model is tla/SharedBudget.tla: two agents drawing on one shared budget. We
model-check that the shared total never exceeds the cap under any interleaving.
The realistic non-atomic (no global lock) system has a violating interleaving;
TLC finds the counterexample trace. The atomic (locked) repair holds for all
interleavings; TLC proves it exhaustively. The verdict for the deployed system
is the non-atomic result; the atomic run is recorded as the repair witness.

If Java or tla2tools.jar is absent the harness skips this layer with an honest
note (same pattern as Lean-absent), and prints exactly what to install.
"""

import os
import re
import subprocess

TLA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tla")
MODULE = "SharedBudget"

JAVA_CANDIDATES = [
    "/opt/homebrew/opt/openjdk@17/bin/java",
    "/opt/homebrew/opt/openjdk/bin/java",
    "/opt/homebrew/opt/openjdk@21/bin/java",
    "java",
]
JAR_CANDIDATES = [
    os.path.join(TLA_DIR, "tla2tools.jar"),
    os.path.expanduser("~/tla-omega/tla2tools.jar"),
]

INSTALL_HINT = (
    "TLA+ tooling not found. To enable the concurrency layer:\n"
    "  1. brew install openjdk@17\n"
    "  2. place tla2tools.jar in proof-carrying-evals/tla/ "
    "(download from https://github.com/tlaplus/tlaplus/releases)\n"
    "The spec tla/SharedBudget.tla is ready to run as-is."
)


def _find_java():
    for cand in JAVA_CANDIDATES:
        try:
            p = subprocess.run([cand, "-version"], capture_output=True, text=True,
                               timeout=15)
            if p.returncode == 0:
                return cand
        except Exception:
            continue
    return None


def _find_jar():
    for cand in JAR_CANDIDATES:
        if os.path.exists(cand):
            return cand
    return None


def tla_available():
    return _find_java() is not None and _find_jar() is not None


def install_hint():
    return INSTALL_HINT


def _write_cfg(label, cap, draw_a, draw_b, atomic):
    cfg = (
        "CONSTANTS\n"
        f"    Cap = {int(cap)}\n"
        f"    DrawA = {int(draw_a)}\n"
        f"    DrawB = {int(draw_b)}\n"
        f"    Atomic = {'TRUE' if atomic else 'FALSE'}\n"
        "SPECIFICATION Spec\n"
        "CHECK_DEADLOCK FALSE\n"
        "INVARIANT TypeOK\n"
        "INVARIANT NoOverCap\n"
    )
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    path = os.path.join(TLA_DIR, f"{MODULE}_{safe}.cfg")
    with open(path, "w") as f:
        f.write(cfg)
    return path, os.path.basename(path)


def _parse_trace(stdout):
    """Pull the counterexample behaviour out of TLC output."""
    m = re.search(r"behavior up to this point is:(.*?)\n\d+ states generated",
                  stdout, flags=re.DOTALL)
    if not m:
        return []
    block = m.group(1)
    steps = []
    for sm in re.finditer(r"State \d+: <([^>]*?)(?: line[^>]*)?>\n(.*?)(?=\nState |\Z)",
                          block, flags=re.DOTALL):
        action = sm.group(1).strip()
        body = sm.group(2)
        tot = re.search(r"total = (-?\d+)", body)
        steps.append({"action": action,
                      "total": int(tot.group(1)) if tot else None})
    return steps


def _states_count(stdout):
    m = re.search(r"(\d+) states generated, (\d+) distinct", stdout)
    if m:
        return {"generated": int(m.group(1)), "distinct": int(m.group(2))}
    return None


def _run_tlc(java, jar, cfg_name, timeout=180):
    try:
        p = subprocess.run(
            [java, "-cp", jar, "tlc2.TLC", "-nowarning", "-config", cfg_name,
             f"{MODULE}.tla"],
            capture_output=True, text=True, timeout=timeout, cwd=TLA_DIR)
        return p.returncode, p.stdout + "\n" + p.stderr
    except Exception as e:
        return -1, f"{e}"


def _check_one(java, jar, label, cap, draw_a, draw_b, atomic):
    _, cfg_name = _write_cfg(label, cap, draw_a, draw_b, atomic)
    rc, out = _run_tlc(java, jar, cfg_name)
    violated = "Invariant NoOverCap is violated" in out
    completed_clean = "No error has been found" in out
    states = _states_count(out)
    if violated:
        verdict, passed = "PROVEN_VIOLATED", False
    elif completed_clean:
        verdict, passed = "PROVEN_HOLDS", True
    else:
        verdict, passed = "UNKNOWN", None
    res = {
        "config": f"tla/{cfg_name}",
        "atomic": atomic,
        "verdict": verdict,
        "passed": passed,
        "states_explored": states,
        "exhaustive": completed_clean,
    }
    if violated:
        trace = _parse_trace(out)
        res["counterexample_trace"] = trace
        res["breach_total"] = trace[-1]["total"] if trace else None
        res["cap"] = int(cap)
    return res


def prove_concurrency(scenario):
    """Model-check the shared-budget concurrency invariant for one scenario.

    Returns the verdict for the DEPLOYED (non-atomic, no global lock) system,
    plus the atomic repair witness for contrast.
    """
    if not tla_available():
        return {"checker": "tla", "available": False, "verdict": "SKIPPED",
                "passed": None, "install_hint": INSTALL_HINT}

    java, jar = _find_java(), _find_jar()
    cap = scenario["shared_cap"]
    da = scenario["draw_a"]
    db = scenario["draw_b"]
    label = scenario["id"]

    deployed = _check_one(java, jar, f"{label}_toctou", cap, da, db, atomic=False)
    repair = _check_one(java, jar, f"{label}_atomic", cap, da, db, atomic=True)

    return {
        "checker": "tla",
        "available": True,
        "tool": "TLC (TLA+ model checker)",
        "property_id": "no_interleaving_over_cap",
        "model": "tla/SharedBudget.tla",
        "is_proof": True,
        "statement": ("under ALL interleavings of two agents drawing on a shared "
                      "budget, the shared total never exceeds the cap"),
        # the verdict for the system as deployed (non-atomic check-then-commit)
        "verdict": deployed["verdict"],
        "passed": deployed["passed"],
        "deployed_non_atomic": deployed,
        "atomic_repair_witness": repair,
        "trust_boundary": ("TLC is exhaustive over the modelled finite state "
                           "space; the guarantee is as good as the model (two "
                           "agents, single draw each, the modelled actions)"),
    }
