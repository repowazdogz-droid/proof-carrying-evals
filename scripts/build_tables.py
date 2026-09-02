#!/usr/bin/env python3
"""Regenerate records/MANIFEST.md and records/TABLE.md from the sealed records.

Reads JSON only. No model, no solver, no network. Run with --check to compare
against the committed files instead of rewriting them (exit 1 on any difference).
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "records", "omega")


def load(path):
    d = json.load(open(path))
    s = d["subject"]
    sj = d.get("soft_judgment") or {}
    viol = [p["property_id"] for p in d.get("proof_evidence", []) if p["verdict"] != "PROVEN_HOLDS"]
    checkers = sorted(set(p["checker"] for p in d.get("proof_evidence", [])))
    scen, _, src = s["action"].partition("/")
    return dict(file=os.path.basename(path), scenario=scen, source=src or "trace", actor=s.get("actor_id"),
                scores=sj.get("scores") or [], final_pass=sj.get("final_pass"), viol=viol, checkers=checkers,
                gate=d["outcome"].get("gate_result"), created=d.get("created_at", "")[:16].replace("T", " "))


def build():
    runs = {
        "ORIGINAL (2026-07-15 model run + 2026-07-20 12:41 planted-only run)": sorted(glob.glob(os.path.join(REC, "pce-0*.original.json"))),
        "RERUN (2026-07-20 16:35, all cases with the model present)": sorted(glob.glob(os.path.join(REC, "pce-0[0-9][0-9].json"))),
    }
    man = ["# Record manifest\n",
           "Every sealed record under `records/omega/` belongs to one of two runs. Files named `pce-NNN.original.json` are the ORIGINAL run and are never overwritten; files named `pce-NNN.json` are the RERUN. Record numbers were assigned per run, so the same number can name a different scenario in the two runs; use the scenario column, never the number, to identify a case.\n",
           "Judge = `qwen2.5-coder:14b` via Ollama, temperature 0.7, three seeds (1000, 1001, 1002); pass threshold 7. The judge sees the request, the case context and the decision; it does not see the governance spec verbatim. For `/model` rows the same model authored the decision. Formal verdicts are per encoded property; `PROVEN_VIOLATED` means the checker proved the decision breaks that property.\n"]
    table_rows = []
    for run, files in runs.items():
        man.append(f"\n## {run}\n\n| record | scenario | source | actor | judge scores | judge pass | formal violated | checkers | gate | created |\n|---|---|---|---|---|---|---|---|---|---|")
        for f in files:
            r = load(f)
            man.append(f"| `{r['file']}` | {r['scenario']} | {r['source']} | {r['actor']} | {r['scores'] or 'n/a'} | {r['final_pass']} | {', '.join(r['viol']) or 'none'} | {', '.join(r['checkers'])} | {r['gate']} | {r['created']} |")
            if run.startswith("RERUN") and r["scores"] and r["scenario"].startswith("c"):
                table_rows.append(r)
    viol = [r for r in table_rows if r["viol"]]
    ok = [r for r in table_rows if not r["viol"]]
    lines = ["| scenario | decision source | judge (3 seeds) | judge verdict | formal verdict | violated property | record |", "|---|---|---|---|---|---|---|"]
    for r in sorted(viol, key=lambda r: (r["scenario"], r["source"])):
        lines.append(f"| {r['scenario']} | {r['source']} | {'/'.join(map(str, r['scores']))} | {'PASS' if r['final_pass'] else 'FAIL'} | PROVEN_VIOLATED | {', '.join(r['viol'])} | `{r['file']}` |")
    lines += ["", "Non-violating single-decision rows in the same run (judge and formal agree):", "",
              "| scenario | decision source | judge (3 seeds) | judge verdict | formal verdict | record |", "|---|---|---|---|---|---|"]
    for r in sorted(ok, key=lambda r: (r["scenario"], r["source"])):
        lines.append(f"| {r['scenario']} | {r['source']} | {'/'.join(map(str, r['scores']))} | {'PASS' if r['final_pass'] else 'FAIL'} | all properties PROVEN_HOLDS | `{r['file']}` |")
    counts = dict(violating=len(viol), judge_passed=sum(1 for r in viol if r["final_pass"]), formal_caught=len(viol))
    return "\n".join(man) + "\n", "\n".join(lines) + "\n", counts


def main():
    manifest, table, counts = build()
    targets = {os.path.join(ROOT, "records", "MANIFEST.md"): manifest, os.path.join(ROOT, "records", "TABLE.md"): table}
    if "--check" in sys.argv:
        bad = [p for p, txt in targets.items() if open(p).read() != txt]
        for p in bad:
            print("DIFFERS from committed:", os.path.relpath(p, ROOT))
        print("counts:", counts)
        sys.exit(1 if bad else 0)
    for p, txt in targets.items():
        open(p, "w").write(txt)
    print("wrote MANIFEST.md and TABLE.md; counts:", counts)


if __name__ == "__main__":
    main()
