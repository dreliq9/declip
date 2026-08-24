# Media Kernel Canonical IR Architecture Spike

This Phase 0 spike tests one architectural question:

> Should durable editorial media state itself be represented as a generalized operation/dialect graph, or should durable media state remain strongly shaped editorial objects that lower into an operation-based executable IR?

The spike deliberately does **not** compare OTIO, MLIR, or another library as products. It compares the underlying representation strategy.

## Candidate A — two-level purpose-built IR

```text
Persistent State
    |
    v
Typed Editorial IR
    Asset / Track / Clip / Transition / OutputIntent
    |
    | verify + canonicalize
    v
Transformation
    |
    v
Executable Op IR
    Source / Trim / Transition / Gain / Mix / Encode / Mux
```

Durable editorial objects have media-shaped schemas and stable identity. Execution remains operation/graph based.

## Candidate B — generalized dialect/op IR

```text
Persistent State
    |
    v
Generic Op Graph
    editorial.asset
    editorial.clip
    editorial.transition
    editorial.output
    |
    | generic verification + lowering
    v
Generic Op Graph
    exec.source
    exec.trim
    exec.transition
    exec.gain
    exec.mix
    exec.encode
```

Editorial and execution concepts share the same generic operation/operand/attribute representation.

## Common fixture

Both candidates encode the same project:

- two 20-second video assets;
- one 60-second audio asset;
- first video clip: 5 seconds;
- second video clip: 5 seconds starting with a 12-frame dissolve overlap;
- sequence/output rate: 30000/1001;
- audio bed under the sequence;
- 1920x1080 output intent;
- explicit color intent.

The 12-frame transition duration is exact media time derived from 30000/1001 fps.

Both candidates must:

1. verify the valid fixture;
2. reject an out-of-bounds clip;
3. reject an overlong transition;
4. produce the same semantic digest;
5. lower into the same executable semantic plan;
6. emit `EXACT` when the target supports the transition;
7. emit `BAKED_LOSS_OF_EDITABILITY` when the target can preserve rendered appearance only by baking the transition;
8. preserve exact-time values in the lowered plan;
9. distinguish persistent editorial identity from transient executable node identity.

Candidate B additionally must reject a deliberately malformed generic editorial op with a required attribute omitted. Candidate A cannot represent that exact malformed state structurally because the field exists in the typed object.

## What is measured

The verification harness records:

- semantic equivalence;
- plan/loss equivalence;
- negative-case behavior;
- source bytes/LOC for the typed-editorial and generalized-editorial sections;
- number of generic attribute-lookup calls;
- number of generic kind-dispatch sites;
- executable-node count.

LOC is evidence, not the selection metric. The decision is driven by semantic clarity, validation locality, durable serialization shape, extensibility, lowering clarity, and the risk of conflating persistent and transient identities.

## Expected synthesis

A likely result is not “custom structs everywhere” versus “generic ops everywhere.” The useful hybrid under test is:

```text
Typed/versioned Editorial IR
        |
        v
controlled Transformation passes
        |
        v
operation/dialect-oriented Executable IR
```

That preserves the strongest idea from compiler-style IR research — verified ops, traits, lowering, target legality, semantic-loss accounting, pass management — without forcing user-authored durable media state into a generic compiler-operation container.
