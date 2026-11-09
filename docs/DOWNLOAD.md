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

## Backups: a ZIP archive and a PDF

A published talk can be kept in two complementary forms: the editable project,
which can be opened and changed again, and a PDF, which anyone can read without
Quarkfoil. `--zip` and `--pdf` write them; use either, both, or both together
with `--output`:

```console
quarkfoil download https://example.org/talks/quantum-simulation/ \
  --zip backups/quantum-simulation.zip --pdf backups/quantum-simulation.pdf
```

Without `--output`, no project directory is created; the project is assembled
in a temporary directory and removed afterwards.

The ZIP archive contains exactly the project `--output` would create, inside
one folder named after the talk, so unpacking it gives a project that opens
with `quarkfoil`. It is reproducible: entries are stored in a fixed order with
fixed timestamps and permissions, so downloading an unchanged talk again gives
an identical archive, and Quarkfoil reports that it is already up to date.

The archive is built to survive damage:

- Each file is compressed and checksummed on its own, so a damaged spot spoils
  one file and the others still extract.
- Photos, video, audio, fonts, and other already-compressed files are stored
  as they are rather than compressed again. Compressing them saves only a few
  per cent, and in a compressed file one bad byte spoils everything after it;
  in a stored file it spoils only that byte. This makes archives a few per
  cent larger than full compression would.
- Every file also carries its own header, so the files can be recovered even if
  the archive's index at its end is lost, for example by an interrupted copy.
- After writing, Quarkfoil reads the archive back, checks every file's checksum,
  and compares the file list and sizes with the project before keeping it. A
  write corrupted by a disk, network share, or sync client is reported and
  nothing is written.

A ZIP archive detects damage but cannot repair it. Keep copies in more than one
place; the PDF is a second, independent copy of what the talk shows.

`--sha256` writes a fingerprint beside each backup, `FILE.zip.sha256` and
`FILE.pdf.sha256`, in the format `sha256sum` reads. Check a stored copy later
from the folder that holds it:

```console
sha256sum -c quantum-simulation.zip.sha256
```

Because the archive is reproducible, an unchanged talk keeps the same
fingerprint from one backup to the next.

The PDF is printed from the recovered project with an installed browser, as
[`quarkfoil print`](PRINT.md) does: one slide-sized page per slide, without
speaker notes. It is printed with the current Quarkfoil rather than the player
the talk was published with, so talks published by older versions print the
same way. `--browser` names the browser to use.

Everything is assembled before anything is written. A missing asset, a missing
browser, or a failed print leaves no project, archive, or PDF; the browser is
checked before anything is downloaded. An existing archive that differs is a
conflict, and so is any existing PDF (a PDF records when it was made, so a new
one never matches the old) or a fingerprint that disagrees; `--force` replaces
them.

## What publication cannot preserve

Speaker notes are omitted by default when publishing, so a public talk normally
has no notes to download. Notes are recovered only if the talk was published
with `--notes`. Likewise, a bibliography published with `--trim-bibliography`
contains only the cited entries and their dependencies. Download cannot restore
content that was never placed on the site.

Use [`pack`](PACK.md) when the original local presentation is still available;
it preserves the local source directly and needs no network request. Use
`download` to recover or fork the public version.
