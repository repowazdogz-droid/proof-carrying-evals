# Aggregate-gate migration (phase0-aggregate-fix)

`omega_record.py` now delegates the aggregate verdict to the shared `omega_gate`
model (invariant: no aggregate status may be strictly stronger than its weakest
required component). Regenerated with `python3 run.py --no-model`.

## Governed OMEGA records (`records/omega/`)

`--no-model` produces a 6-record hash-chained bundle (pce-001..006), all
regenerated with the new outcome format (`aggregate_state`, `components_passed`,
`components_not_run`, `components_failed`). chain_intact=True; seals verify;
tamper (flip gate_result) fails verification.

| record | before gate_result | after aggregate_state / gate_result / acted | passed/total | not_run |
|---|---|---|---|---|
| pce-001 | HELD | FAILED / HELD / false | 6/7 | [] (failed: z3) |
| pce-002 | HELD | FAILED / HELD / false | 6/7 | [] (failed: z3) |
| pce-003 | HELD | FAILED / HELD / false | 6/7 | [] (failed: z3) |
| pce-004 | HELD | FAILED / HELD / false | 6/7 | [] (failed: z3) |
| pce-005 | HELD | FAILED / HELD / false | 1/2 | [] (failed: lean) |
| pce-006 | HELD | FAILED / HELD / false | 3/4 | [] (failed: tla) |

pce-007..016 are **stale** artifacts of an earlier `2026-07-15` WITH-model run
(16-record bundle) and are NOT reproducible under `--no-model`; they were left
in place (and preserved as `*.original.json`), not regenerated. Recomputing the
NEW gate over their stored `proof_evidence` leaves every verdict unchanged
(HELD/ESCALATED/COMMITTED all agree), so no stale record is overstated.

## COMMITTED-with-skip check (the deliverable question)

Running the new `omega_gate` over the `proof_evidence` of **all 16** omega
records: **NO record is a COMMITTED-with-skip case.** The only two COMMITTED
records are pce-012 (7/7 ran+passed) and pce-013 (2/2 ran+passed); both have
`components_not_run = []`. pce-008 is ESCALATED (7/7 passed, model chose
escalate). Every HELD record has a genuinely failed component. Note: evidence
entries carry `available: null` with a real PROVEN verdict, which the shared
model correctly reads as "ran" (verdict-based), not as a skip.

## Per-decision records (`records/*.json`: c1..c8, s1, s2, planted)

These carry per-property proofs + a `seal` but **no single aggregate `outcome`
gate** (confirmed: `has_outcome = False` for all). The aggregate-with-skip
concern does not apply to them; they are built by `record.py`, not the aggregate
gate.

- test_gate.py: 12 passed, 0 failed.
