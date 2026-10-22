# Incident window

Two incident reports can cover the same outage. Adding their durations overstates
downtime; treating a mitigation update as recovery understates it. This contract
turns a frozen incident report into bounded, reproducible outage accounting.

## What it does

The owner registers a component, region, explicit UTC window, downtime budget,
incident IDs, and a commit-pinned report URL with SHA-256. That record cannot be
edited. Anyone can request its one-time review.

The leader and validators independently fetch the report and interpret each
declared incident. They distinguish component/region scope, actual onset, complete
restoration, an explicitly ongoing outage, and insufficient evidence. Every
timestamp is an exact UTC source token. Each quote must be verbatim and include
the incident ID. Whitespace reflow is resolved to the original span. If a quoted
sentence omits its ID prefix, its original source line must supply the exact ID;
another incident's label cannot anchor it. A validator checks the leader's witnesses, then extracts its own
facts. Different supporting quote spans can agree; different event facts cannot.

After consensus, code clips intervals to the accounting window, sorts and unions
overlapping or touching intervals, and computes integer seconds and availability
parts per million. An outage explicitly continuing beyond the window is censored
at the window end. A missing recovery without that ongoing evidence yields
`INCOMPLETE`; zero-valued numeric fields then carry no availability conclusion.
`budget_exceeded` uses `downtime > budget`, so equality is within budget.

## Interface

| Method | Purpose |
| --- | --- |
| `register(id, policy_json)` | Owner-only immutable policy; see `demo.json` |
| `review(id)` | Permissionless consensus review; cannot overwrite a receipt |
| `get_policy(id)` | Canonical registered policy |
| `get_review(id)` | Result, interval offsets in seconds, evidence and policy hash |
| `has_complete_accounting(id)` | False before review and for incomplete evidence |

The stored `policy_sha256` commits to canonical JSON, including the source digest.
Transport, UTF-8, size and hash failures abort and leave review retryable. A
completed incomplete review needs a new ID and newly frozen evidence to revisit.

## StudioNet evidence

Final deployment: [0xa7A0f1157413b1063fCC661d72577C06879632D2](https://explorer-studio.genlayer.com/address/0xa7A0f1157413b1063fCC661d72577C06879632D2).
The deployed source matches commit `432b3a3`. The seven zero-value transactions
and three onchain reads are indexed in [evidence/index.json](evidence/index.json).

| Case | Observed result |
| --- | --- |
| `overlap` | COMPLETE; 2,400 seconds, one merged interval, budget exceeded |
| `ongoing` | COMPLETE; 900 seconds, censored at window end |
| `mitigated` | INCOMPLETE; no availability conclusion |

All three final reviews reached MAJORITY_AGREE with successful leader execution.
The overlap review needed one leader rotation. This is majority agreement, not a
claim that every validator agreed. Earlier unsuccessful runs remain documented
under [evidence/development](evidence/development/README.md).

## Reproduce

Python 3.13 was used for 47 direct-mode tests. These exercise the actual SDK and
storage, with controlled web/LLM responses. `run_validator()` explicitly tests
agreement, disagreement, false recovery evidence and malformed proposals. Direct
mode is not a live multi-validator network.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest -q
$env:GENVM_VERSION='v0.2.12'
.\.venv\Scripts\genvm-lint check contracts/incident_window.py
```

For StudioNet use the script's disposable local account, never a funded wallet:

```powershell
python scripts/studio_demo.py deploy
python scripts/studio_demo.py wait <transaction-id>
python scripts/studio_demo.py register overlap
python scripts/studio_demo.py wait <transaction-id>
python scripts/studio_demo.py review overlap
python scripts/studio_demo.py wait <transaction-id>
python scripts/studio_demo.py read overlap
```

Repeat register/review/read for `ongoing` and `mitigated`. Reads and receipts go to
`evidence/`; keys and full RPC receipts stay in ignored `.local/`. Each invocation
performs at most one write. If a write's outcome is unknown, inspect the existing
transaction rather than repeating it. `verify_evidence.py` checks saved evidence;
it is an offline integrity check, not a fresh RPC query.
The script also refuses the SDK's static consensus-address fallback when live
address discovery fails; read retries are bounded and signed writes are not retried.

## Boundaries

This accounts only for the owner-declared incidents, component and report. It
does not discover missing incidents or verify the operator's report against real
traffic. Synthetic fixtures are operator-controlled examples, not uptime claims.
Maintenance exclusions, partial degradation weighting and multi-region aggregation
are outside this primitive. Quotes and hashes establish provenance, not truth.
Validator agreement can still share a semantic error. No payouts or transfers
are implemented. StudioNet state can be reset.

The pinned-source pattern, Windows test cleanup and receipt tooling build on
[Benchmark pair](https://github.com/mrcactus66/benchmark-pair). Outage semantics,
window state, interval accounting and tests are new here. The scripts are shared
with Version applicability; the contracts remain standalone.

References: [custom consensus](https://docs.genlayer.com/developers/intelligent-contracts/features/non-determinism),
[direct testing](https://docs.genlayer.com/api-references/genlayer-test/direct).
