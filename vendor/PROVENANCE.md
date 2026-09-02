# Vendored packages

Two small packages this harness imports are not yet published on their own. They are
vendored here, unmodified, so the committed records can be verified and the harness
re-run from a clean clone.

| package | file | source | author | licence |
|---|---|---|---|---|
| `omega_seal` | `vendor/omega_seal/__init__.py` (138 lines, stdlib only: `hashlib`, `json`) | private repository `omega-seal`, commit of 2026-06-23 | Warren Smith | MIT, same as this repository |
| `omega_gate` | `vendor/omega_gate/__init__.py` (246 lines, no imports) | private repository `omega-gate`, commit of 2026-07-20 | Warren Smith | MIT, same as this repository |

`omega_record.py` puts `vendor/` first on `sys.path`, so these copies are the ones used
even on a machine where the packages are installed. `omega_seal` computes the
`content_hash` seal over a canonical JSON form of each record; `omega_gate` computes
the aggregate verdict with the invariant that no aggregate may be stronger than its
weakest required component (see `records/MIGRATION.md`).
