# Download a published talk

`quarkfoil download` reconstructs an editable Quarkfoil project from a talk
that was published into a collection:

```console
quarkfoil download https://example.org/talks/quantum-simulation/ \
  --output presentations/quantum-simulation
```

The command is non-destructive. It reads the public website and does not alter
or remove the published talk.

## What is recovered

A published talk keeps its Markdown unchanged in `presentation.md`, while most
of its figures live in the collection's content-addressed asset pool. The
published page contains a map from the Markdown's original project paths to
those pooled objects. Download reverses that map:

```text
presentations/quantum-simulation/
├── quantum-simulation.md
├── references.bib
├── figures/
│   └── apparatus.svg
└── data/
    └── measurements.csv
```

Quarkfoil also retrieves private copies used by Markdown links or images that
the published player cannot route through the pool, the configured
bibliography, and files that were published from `assets.include`. It writes
none of the website machinery: `index.html`, `meta.json`, shared runtimes, and
the hashed `assets/` tree remain publication artifacts.

New publications remember the original Markdown file name in `meta.json` and
download restores it. For an older publication that does not carry that field,
the talk folder becomes the file name. Override either result with `--name`:

```console
quarkfoil download https://example.org/talks/quantum-simulation/ \
  --output presentations/new-course --name lecture-01.md
```

The result opens like any local project:

```console
quarkfoil presentations/new-course/lecture-01.md
```

## Safe repeated downloads

Download assembles the complete project in a temporary sibling directory. A
missing or unsafe asset leaves the destination unchanged and no partial project
behind. Every restored path must remain inside the output directory, and pooled
objects must remain on the published site's origin.

An existing output directory is reused, and unrelated files survive. Quarkfoil
refuses to replace a differing file and lists conflicts. `--force` replaces
those files deliberately:

```console
quarkfoil download URL --output PROJECT --force
```

`--timeout` controls the limit for each network request. The default is 30
seconds; large videos are streamed rather than held in memory.

## What publication cannot preserve

Speaker notes are omitted by default when publishing, so a public talk normally
has no notes to download. Notes are recovered only if the talk was published
with `--notes`. Likewise, a bibliography published with `--trim-bibliography`
contains only the cited entries and their dependencies. Download cannot restore
content that was never placed on the site.

Use [`pack`](PACK.md) when the original local presentation is still available;
it preserves the local source directly and needs no network request. Use
`download` to recover or fork the public version.
