/-
Trace.lean - the reusable inductive invariant for the prefix running-total
monitor. Core Lean 4 only (no Mathlib).

This is the property class Z3 structurally cannot decide: a statement
quantified over ALL traces of ANY length. Z3 checks one decision at a time;
this needs induction over the sequence. We prove it ONCE here, for all traces,
and the harness then kernel-certifies the concrete verdict for each trace it
evaluates.
-/

namespace PCEval

/-- The per-step monitor: walk the trace accumulating the running total,
    rejecting (false) as soon as any prefix running total exceeds the cap. -/
def prefixWithin (cap : Nat) : Nat → List Nat → Bool
  | _,   []        => true
  | run, a :: rest =>
      let run' := run + a
      if run' ≤ cap then prefixWithin cap run' rest else false

/-- True iff every prefix running total (starting from `start`) stays within `cap`. -/
def allPrefixesWithinCap (start cap : Nat) (trace : List Nat) : Bool :=
  prefixWithin cap start trace

/-- The running totals visited along the trace. -/
def runningTotals (run : Nat) : List Nat → List Nat
  | []        => []
  | a :: rest => (run + a) :: runningTotals (run + a) rest

/-- SOUNDNESS (inductive, holds for ALL traces of ANY length):
    if the monitor accepts, then every running total along the trace is within
    the cap. This is the invariant Z3 cannot establish on its own: it is
    universally quantified over unbounded traces and proved by induction. -/
theorem monitor_sound (cap : Nat) :
    ∀ (trace : List Nat) (run : Nat),
      prefixWithin cap run trace = true →
      ∀ x ∈ runningTotals run trace, x ≤ cap := by
  intro trace
  induction trace with
  | nil => intro run _ x hx; cases hx
  | cons a rest ih =>
      intro run h x hx
      simp only [prefixWithin] at h
      by_cases hle : run + a ≤ cap
      · rw [if_pos hle] at h
        simp only [runningTotals] at hx
        cases hx with
        | head => exact hle
        | tail _ hmem => exact ih (run + a) h x hmem
      · rw [if_neg hle] at h
        exact absurd h (by decide)

/-- PER-STEP SAFETY IS INSUFFICIENT (the headline, kernel-checked):
    there is a trace where every single amount is within the per-transaction
    cap, yet the trace breaches the global cap at some prefix. A per-decision
    check (each amount <= perTx, which is what Z3 verifies) cannot catch this;
    only the trace invariant can. -/
theorem per_step_insufficient :
    ∃ (perTx globalCap start : Nat) (trace : List Nat),
      (∀ a ∈ trace, a ≤ perTx) ∧
      start ≤ globalCap ∧
      allPrefixesWithinCap start globalCap trace = false := by
  exact ⟨5000, 12000, 0, [5000, 5000, 5000], by decide, by decide, by decide⟩

#print axioms monitor_sound
#print axioms per_step_insufficient

end PCEval
