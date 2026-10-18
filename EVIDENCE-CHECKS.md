# Local evidence checks, without completion theater

The playbook asks whether an independent reader can check evidence. A scorecard
alone cannot answer that. This optional, standard-library Python tool gives a
reviewer a repeatable way to compare an explicitly selected local evidence bundle
with a manifest of small claims. It does not change existing scores or shipping
rules, and is not a new completion gate.

## Quick start

Requires Python 3.9+ on a POSIX system with `O_NOFOLLOW` and descriptor-relative
file operations (Linux/macOS). No packages, credentials, network or installation.

1. Stage only non-sensitive evidence in a dedicated directory. Do not point this
   tool at an entire home directory or live agent workspace. A public bundle must
   be reviewed for secrets and private data before sharing; this tool is not a
   secret scanner or permission to share.
2. Have the requester/reviewer agree the acceptance criteria. List every criterion
   in a manifest, using `human_review` wherever it cannot be machine-checked.
3. Record the actual evidence hashes and a deliberately bounded review window.
   Preserve the agreed manifest in the review thread or version control. The tool
   cannot authenticate a manifest or prevent its author weakening the criteria.
4. Run:

   ```sh
   python3 tools/check-evidence.py --root examples/evidence --manifest manifest.json
   ```

The bundled example is intentionally dated October 18, 2026. Outside its declared
window it reports `unknown`. Do not silently refresh an old receipt's dates to make
it pass: collect current evidence and document the change. The manifest's times
are declarations, not proof of when a file was produced. The CLI uses the system
clock and does not offer a switch to backdate a live verification.

Tests use a fixed clock and temporary synthetic files:

```sh
python3 -m unittest discover -s tests -p 'test_check_evidence.py' -v
```

## Manifest v1

Required top-level keys: `version` (integer 1), `task`, timezone-aware `recorded_at`
and `valid_until` (exclusive), and 1–100 `criteria`. Unknown fields/check kinds,
duplicate JSON keys, duplicate IDs, missing fields and non-finite numbers fail
closed. Each criterion has a unique `id`, a small `claim`, and a `kind`:

- `artifact_sha256`: requires relative `path` and lowercase `sha256`. A match means
  only that the observed bytes have that hash. It does not validate the claim's
  meaning, quality, creation time, origin or author.
- `json_equals`: also requires RFC 6901 `pointer` and JSON `expected`. Compares the
  value in the hash-bound local JSON artifact. A report saying three tests passed
  is still a report; matching it does not prove any test was run. Comparisons are
  type-strict, including integer versus decimal and boolean versus number. JSON
  decimals use exact decimal parsing, avoiding binary rounding and underflow.
- `human_review`: no artifact fields. Always remains `human_review_required`.
  For example, whether an output answers the current request or whether permission
  was actually granted should not be certified from a self-authored field.

No inline commands, plug-ins, imports, URLs, scripts, remote fetching or arbitrary
expressions are supported. The tool never opens links from evidence. It reads
only named regular files under the caller-selected root, with a 1 MiB per-file
limit. Absolute/traversal/dot paths and symlink components are refused. Opening
relative to directory descriptors avoids a symlink-swap escape during traversal.
Named pipes and devices are refused. `SENSITIVE_*` and `knowledge_base` paths are
also excluded. These exclusions do not constitute comprehensive secret detection.
The caller-selected root is trusted; choose a stable dedicated bundle, not a
concurrently modified workspace. Hard links and a malicious/mutating filesystem
are outside the containment guarantee. Each check describes the bytes it read,
not an atomic snapshot of the whole bundle.

## Report interpretation

Reports include the checked time, exact manifest hash, criterion IDs, observed
artifact hashes, sizes, and narrow statuses:

| Status | Meaning |
| --- | --- |
| `artifact_identity_matched` | Observed bytes match the declared hash |
| `recorded_value_matched` | Hash-bound JSON contains the declared value |
| `mismatch` | Bytes or value differ |
| `unknown` | Missing, malformed, unsafe, oversized, or outside declared window |
| `human_review_required` | The tool cannot evaluate this criterion |

Every report says `task_acceptance: not_assessed` and
`authorization: not_assessed`. In particular, matching a stored approval field
would not authorize an action. No score, `COMPLETE` signal, funds release, deploy,
queue change or other action is produced. Existing quality-trend reporting remains
unchanged; its score and this tool's observations answer different questions.

Exit codes: 0 means all supported observations matched and/or human review remains;
1 means at least one mismatch/unknown; 2 means the manifest itself could not be
read/validated. **Exit 0 is never task acceptance or permission to ship.** A human
must still inspect the criteria, source trust, omitted requirements, effect on the
real target, and adequacy of the checks. This is a review aid, not an independent
witness, signature, freshness attestation or comprehensive sandbox.

## Why this addition

The [playbook](PLAYBOOK.md) asks for falsifiable evidence and independent checks.
Bob's [July 20 account](https://blog.bobrenze.com/2026/07/20/the-agent-who-lied-to-itself/)
describes an audit repeating an earlier log instead of checking actual files.
His [October 1 essay](https://blog.bobrenze.com/2026/10/01/receipts-are-the-point/)
recognizes that receipts can be forged or mis-scoped and urges separating observed
from inferred claims. The [October 12 essay](https://blog.bobrenze.com/2026/10/12/verification-is-not-overhead-it-is-the-product/)
asks that review become cheaper while authority stays explicit.

This tool operationalizes a small part of those goals. It deliberately stops short
of treating local records as proof of external events. Future trusted adapters
would need separate source/authenticity and permission designs, not a new label
that says “independent.”
