# Earlier deployment

These receipts belong to the first deployment at
`0x0B3591bD930cD7119C845B1ded6181A705cf9cC3`, before witness handling and the OPEN
schema instruction were revised. They are not evidence for the final contract.

The overlap review reached majority agreement. The ongoing-outage review ended
UNDETERMINED / MAJORITY_DISAGREE after three rotations. Earlier rounds reported
`Open incident needs explicit ongoing evidence` and `Quote lacks incident ID`.
The final leader supplied the expected ongoing evidence, but agreement was still
insufficient. Final validator receipts do not expose their independent extraction,
so their precise semantic differences cannot be reconstructed from these files.

The revised contract maps whitespace-reflowed witnesses back to original source
spans, requires an exact incident-ID token, and can recover an omitted ID prefix
only from the same original source line. The prompt explicitly requires a
nonempty ongoing witness even though an OPEN incident has no recovery timestamp.
New regression tests cover source-label recovery and similar-ID rejection.

All fixtures are synthetic and operator-authored. Full RPC receipts are retained
locally; these public receipts preserve outcome, execution and vote information.
