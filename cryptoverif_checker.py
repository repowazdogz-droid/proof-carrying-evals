"""cryptoverif_checker.py - the fourth checker (CryptoVerif), behind the same
abstraction.

Z3 decides one decision. Lean proves an inductive invariant over one trace. TLC
proves a concurrency invariant over all interleavings. CryptoVerif proves a
property NONE of them can even state: cryptographic/computational soundness.

The property: decision-authorisation unforgeability. The governance gateway
accepts a decision only if it carries a valid signature under the authoriser's
key. We prove that no probabilistic poly-time adversary - holding the public key
and a chosen-message signing oracle - can make the gateway accept a decision the
authoriser never signed, UNDER the single assumption that the signature scheme
is UF-CMA. CryptoVerif derives the concrete advantage bound Psign.

This lives in the COMPUTATIONAL model: the adversary is any probabilistic
algorithm and "secure" means a bound on its forgery probability in the security
parameter. Z3 / Lean / TLA+ have no poly-time adversary, no advantage, and no
security parameter, so they cannot express the property at all.

  cryptoverif/DecisionAuth.ocv         - the deployed (signature-checked) gateway
  cryptoverif/DecisionAuth_bypass.ocv  - the forgeable design (accepts without
                                         verifying), the contrast witness

If the CryptoVerif binary is absent the harness skips with an honest note and
the exact install steps (same pattern as Lean/TLA+).
"""

import os
import re
import shutil
import subprocess

CV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptoverif")
SECURE_SPEC = "DecisionAuth.ocv"
BYPASS_SPEC = "DecisionAuth_bypass.ocv"

CV_CANDIDATES = [
    os.path.expanduser("~/.opam/proverif/bin/cryptoverif"),
    "cryptoverif",
]

INSTALL_HINT = (
    "CryptoVerif not found. To enable the computational-soundness layer:\n"
    "  1. opam install cryptoverif   (or build from "
    "https://bblanche.gitlabpages.inria.fr/CryptoVerif/)\n"
    "  2. ensure the cryptoverif binary is on PATH or at "
    "~/.opam/<switch>/bin/cryptoverif\n"
    "The specs cryptoverif/DecisionAuth.ocv and DecisionAuth_bypass.ocv are "
    "ready to run as-is."
)

ASSUMPTIONS = {
    "model": "computational (probabilistic poly-time adversary)",
    "adversary": ("any PPT algorithm holding the public key and a chosen-message "
                  "signing oracle"),
    "assumption": "the signature scheme is UF-CMA (existentially unforgeable)",
    "proves": ("no PPT adversary makes the gateway accept a decision the "
               "authoriser never signed, except with probability <= Psign"),
    "does_not_cover": ("the UF-CMA assumption itself, side channels, key "
                       "management, or whether the signed decision was the "
                       "RIGHT decision (proof-vs-intent gap)"),
}


def _find_cv():
    for cand in CV_CANDIDATES:
        if os.path.isabs(cand):
            if os.path.exists(cand) and os.access(cand, os.X_OK):
                return cand
        else:
            found = shutil.which(cand)
            if found:
                return found
    return None


def cryptoverif_available():
    return _find_cv() is not None


def install_hint():
    return INSTALL_HINT


def _run(binary, spec, timeout=180):
    try:
        p = subprocess.run([binary, spec], capture_output=True, text=True,
                           timeout=timeout, cwd=CV_DIR)
        return p.returncode, p.stdout + "\n" + p.stderr
    except Exception as e:
        return -1, f"{e}"


def _bound(out):
    m = re.search(r"RESULT Proved .*? up to probability (.+)", out)
    return m.group(1).strip() if m else None


def _check(binary, spec):
    rc, out = _run(binary, spec)
    proved = "All queries proved." in out
    could_not = "Could not prove" in out
    if proved:
        verdict, passed = "PROVEN_HOLDS", True
    elif could_not:
        verdict, passed = "NOT_PROVED", False
    else:
        verdict, passed = "UNKNOWN", None
    return {"spec": f"cryptoverif/{spec}", "verdict": verdict, "passed": passed,
            "advantage_bound": _bound(out)}


def prove_authorisation():
    """Prove decision-authorisation unforgeability for the deployed gateway, and
    run the forgeable-design contrast witness."""
    if not cryptoverif_available():
        return {"checker": "cryptoverif", "available": False, "verdict": "SKIPPED",
                "passed": None, "install_hint": INSTALL_HINT}

    binary = _find_cv()
    secure = _check(binary, SECURE_SPEC)
    bypass = _check(binary, BYPASS_SPEC)

    return {
        "checker": "cryptoverif",
        "available": True,
        "tool": "CryptoVerif 2.12 (computational model)",
        "property_id": "decision_authorisation_unforgeable",
        "model": "cryptoverif/DecisionAuth.ocv",
        "is_proof": True,
        "statement": ("no probabilistic poly-time adversary can make the gateway "
                      "accept a decision the authoriser never signed, under the "
                      "UF-CMA assumption"),
        # verdict for the deployed (signature-checked) gateway
        "verdict": secure["verdict"],
        "passed": secure["passed"],
        "advantage_bound": secure["advantage_bound"],
        "deployed_signature_checked": secure,
        "forgeable_design_witness": bypass,
        "assumptions": ASSUMPTIONS,
        "trust_boundary": ("the proof is sound in the computational model UNDER "
                           "the UF-CMA assumption and the CryptoVerif TCB; it does "
                           "not establish UF-CMA itself nor that the signed "
                           "decision was correct in intent"),
    }
