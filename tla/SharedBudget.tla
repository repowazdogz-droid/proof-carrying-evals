-------------------------------- MODULE SharedBudget --------------------------------
(***************************************************************************)
(* Two agents A and B draw concurrently on ONE shared budget. The global   *)
(* safety property is that the shared total never exceeds the cap under ANY *)
(* interleaving of their decisions.                                        *)
(*                                                                         *)
(* Each agent's own draw is within the per-transaction cap (what Z3 checks  *)
(* per decision) and each agent's own draw sequence stays within the cap    *)
(* (what Lean proves per single trace). The violation lives ONLY in the     *)
(* concurrent interleaving: a non-atomic read-then-commit lets both agents  *)
(* read the same stale total, each pass its guard against that snapshot,    *)
(* and both commit - driving the shared total over the cap. That is a       *)
(* property over interleaved events, which is TLC's home and is awkward for *)
(* a single Z3 query or induction over one trace.                          *)
(*                                                                         *)
(*   Atomic = TRUE  : check-and-commit is one step, guarding on the LIVE    *)
(*                    total. No interleaving violates (TLC proves it).      *)
(*   Atomic = FALSE : read and commit are separate steps, guarding on the   *)
(*                    STALE snapshot. Some interleaving violates (TLC finds  *)
(*                    the counterexample trace).                            *)
(***************************************************************************)
EXTENDS Integers

CONSTANTS Cap, DrawA, DrawB, Atomic

VARIABLES total,   \* the shared running total
          readA,   \* the snapshot A read (-1 = not yet read)
          readB,   \* the snapshot B read (-1 = not yet read)
          doneA,   \* A has committed its draw
          doneB    \* B has committed its draw

vars == << total, readA, readB, doneA, doneB >>

Init == /\ total = 0
        /\ readA = -1
        /\ readB = -1
        /\ doneA = FALSE
        /\ doneB = FALSE

(*-- Non-atomic path: read now, commit later, guard on the stale snapshot --*)

A_Read == /\ ~Atomic
          /\ ~doneA
          /\ readA = -1
          /\ readA' = total
          /\ UNCHANGED << total, readB, doneA, doneB >>

A_Commit == /\ ~Atomic
            /\ ~doneA
            /\ readA # -1
            /\ readA + DrawA <= Cap          \* guard on what A read earlier
            /\ total' = total + DrawA
            /\ doneA' = TRUE
            /\ UNCHANGED << readA, readB, doneB >>

B_Read == /\ ~Atomic
          /\ ~doneB
          /\ readB = -1
          /\ readB' = total
          /\ UNCHANGED << total, readA, doneA, doneB >>

B_Commit == /\ ~Atomic
            /\ ~doneB
            /\ readB # -1
            /\ readB + DrawB <= Cap
            /\ total' = total + DrawB
            /\ doneB' = TRUE
            /\ UNCHANGED << readA, readB, doneA >>

(*-- Atomic path: fused read-check-commit, guard on the LIVE total ---------*)

A_Atomic == /\ Atomic
            /\ ~doneA
            /\ total + DrawA <= Cap
            /\ total' = total + DrawA
            /\ doneA' = TRUE
            /\ UNCHANGED << readA, readB, doneB >>

B_Atomic == /\ Atomic
            /\ ~doneB
            /\ total + DrawB <= Cap
            /\ total' = total + DrawB
            /\ doneB' = TRUE
            /\ UNCHANGED << readA, readB, doneA >>

\* Concurrency is disjunction: TLC explores every interleaving of enabled steps.
Next == \/ A_Read \/ A_Commit \/ A_Atomic
        \/ B_Read \/ B_Commit \/ B_Atomic

Spec == Init /\ [][Next]_vars

TypeOK == /\ total \in Int
          /\ readA \in Int
          /\ readB \in Int
          /\ doneA \in BOOLEAN
          /\ doneB \in BOOLEAN

\* GLOBAL SAFETY: the shared total never exceeds the cap, under any interleaving.
NoOverCap == total <= Cap
================================================================================
