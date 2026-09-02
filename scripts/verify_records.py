#!/usr/bin/env python3
"""FAST verification of the published experiment. No model, no solver, no network.

Checks, for every sealed record under records/omega/:
  1. the content_hash seal recomputes (omega_seal.verify), so the record is unaltered;
  2. the recorded aggregate verdict equals what omega_gate computes from the record's own
     proof evidence, so no record claims more than its weakest required component;
  3. records/MANIFEST.md and records/TABLE.md are exactly what the records generate;
  4. the headline counts hold: in the RERUN, 6 single-decision cases violate an encoded
     property, the judge passed 4 of them, and the formal checker proved all 6.
Exit status is non-zero on any failure.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor"))
sys.path.insert(0, ROOT)
import omega_seal  # noqa: E402
import omega_gate  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_tables  # noqa: E402

failures = []
records = sorted(glob.glob(os.path.join(ROOT, "records", "omega", "pce-0*.json")))
if len(records) != 32:
    failures.append(f"expected 32 sealed records (16 original + 16 rerun), found {len(records)}")
for path in records:
    d = json.load(open(path))
    name = os.path.relpath(path, ROOT)
    if not omega_seal.verify(d):
        failures.append(f"seal does not recompute: {name}")
    agg = omega_gate.aggregate(d.get("proof_evidence", []), d.get("governed_decision", {}).get("action_taken", {}).get("action"))
    recorded = d["outcome"].get("gate_result")
    if agg.gate_result != recorded:
        failures.append(f"aggregate mismatch in {name}: recorded {recorded}, recomputed {agg.gate_result}")

manifest, table, counts = build_tables.build()
for rel, txt in (("records/MANIFEST.md", manifest), ("records/TABLE.md", table)):
    if open(os.path.join(ROOT, rel)).read() != txt:
        failures.append(f"{rel} differs from what the records generate")
expected = dict(violating=6, judge_passed=4, formal_caught=6)
if counts != expected:
    failures.append(f"headline counts {counts} != {expected}")

print(f"records checked: {len(records)}; seals verified: {len(records) - sum('seal' in f for f in failures)}; counts: {counts}")
if failures:
    print("FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("PASS: every record seal recomputes, every aggregate matches omega_gate, MANIFEST/TABLE regenerate byte-identically, judge passed 4 of 6 violating decisions and the checker caught 6 of 6")
