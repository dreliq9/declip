# Media Kernel Architecture Decision Records

These ADRs are the compact normative index for the foundational Media Kernel. Detailed research, bakeoffs, and conformance evidence remain in the linked documents.

Status meanings:

- **Accepted** — governs Phase 1 unless an explicit reconsideration trigger is hit.
- **Superseded** — retained for history but no longer governs.
- **Proposed** — not yet binding.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-kernel-boundary.md) | Kernel family boundaries and Declip separation | Accepted |
| [0002](0002-exact-time.md) | Exact rational MediaTime / TimeRange semantics | Accepted |
| [0003](0003-language-and-c-abi.md) | Odin primary implementation + stable C ABI | Accepted |
| [0004](0004-state-vs-execution-identity.md) | Persistent State identity separate from execution identity | Accepted |
| [0005](0005-two-level-ir.md) | Typed Editorial IR -> operation-oriented Executable IR | Accepted |
| [0006](0006-semantic-loss.md) | Structured semantic-loss accounting | Accepted |
| [0007](0007-resource-lifetime.md) | Generational resource handles + explicit async/fence lifetime | Accepted |
| [0008](0008-canonical-serialization.md) | Deterministic CBOR + SHA-256 canonical persistence/hashing | Accepted |
| [0009](0009-core-abi-evolution.md) | Fixed leaves; growable descriptors pointer-nested/pointer-array | Accepted |
| [0010](0010-admission-separation.md) | Render success separate from typed artifact Admission | Accepted |

## Change rule

An accepted ADR is not changed by silently editing its conclusion. If production evidence invalidates it:

1. create a new ADR;
2. cite the concrete reconsideration evidence;
3. mark the old ADR superseded;
4. update dependent specifications/conformance fixtures explicitly.

The stable C ABI and canonical serialized forms require particular care: convenience refactors do not justify changing already exercised semantic contracts.
