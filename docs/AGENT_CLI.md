# Use Quarkfoil with an AI assistant

Quarkfoil can work with coding assistants that are allowed to read files and
run commands on your computer. This includes terminal-based assistants and
editor assistants with access to your presentation folder. An ordinary web
chat cannot use this feature unless you upload files and edit them manually.

You do not need to teach the assistant Quarkfoil's file format or prepare JSON
files yourself. Quarkfoil provides installed, version-matched guidance for its
workflow, Markdown format, layouts, overlays, assets, citations, publishing,
and authoring conventions, then applies slide changes safely.

## Before you begin

Install or upgrade Quarkfoil as described in the
[installation guide](INSTALLATION.md). Check that this command works in a
terminal:

```console
quarkfoil deck guide
```

Then open the folder containing your presentation in your coding assistant.
Only give an assistant access to folders and files you are comfortable sharing
with that service.

The bare guide is a compact index. An assistant can load only the knowledge its
task needs:

```console
quarkfoil deck guide workflow
quarkfoil deck guide operations
quarkfoil deck guide metadata
quarkfoil deck guide format
quarkfoil deck guide layouts
quarkfoil deck guide overlays
quarkfoil deck guide assets
quarkfoil deck guide citations
quarkfoil deck guide publishing
quarkfoil deck guide authoring
quarkfoil deck guide reproduction
quarkfoil deck guide examples
```

`quarkfoil deck guide --all` prints the complete installed reference. Because
the guidance comes from the installed Quarkfoil version, an assistant does not
need an application-specific skill or an internet copy of the documentation.
For reconstruction from PowerPoint, PDF, or screenshots, the `reproduction`
topic explains resolved type sizes, image-only regions, free-canvas choices,
overlay line breaks, geometry, overflow budgets, and visual verification. See
also the [authoring and source-reconstruction guide](AUTHORING.md).

The `publishing` topic explains how an assistant can update a local or remote
collection, including the required front matter, rsync-over-SSH target syntax,
safe dry runs, and the boundary between Quarkfoil and web-server configuration.
The `operations` topic contains the exact guarded headers for insertion,
deletion, movement, and literal substitution; assistants need not load those
schemas for an ordinary slide replacement.

The `metadata` topic covers guarded front-matter changes. It is the supported
way to change titles, authors, dates, themes, publication fields, asset paths,
defaults, and custom metadata without opening the deck file directly. For
link-sharing cards, use `social.image` with a project-relative figure or
`social.slide` with a stable slide ID, plus optional `social.alt`. Omitting
both selectors uses the Front page slide. Run `quarkfoil deck guide publishing`
for the public collection URL and complete publishing workflow.

## Treat the presentation file as opaque

The assistant must use `quarkfoil deck inspect` whenever it needs presentation
content and `quarkfoil deck apply` for every presentation change. It must not
read, select, parse, or rewrite the deck with `cat`, `sed`, `awk`, `grep`,
Python, regular-expression scripts, or a generic patching tool. Those routes
bypass slide boundaries, private-note filtering, parser validation, revision
guards, and atomic saving.

Quarkfoil can generate guarded edit documents in a new directory:

```console
quarkfoil deck inspect lecture.md --slides 12 --format edit --output lecture-edit
```

The assistant may use its normal text editor or patch capability on
`lecture-edit/slide-0012.md`, retain the generated YAML header, and apply it:

```console
quarkfoil deck apply lecture.md --edit lecture-edit/slide-0012.md
```

This is the only place a generic editing tool belongs in the workflow: it may
edit a generated transaction document, never `lecture.md` itself.

### Edit presentation metadata

Generate a guarded document containing the current front-matter mapping:

```console
quarkfoil deck inspect lecture.md --format metadata --output metadata.yml
```

Edit the YAML mapping after the generated header, keeping fields you do not
intend to change. Unknown fields and comments remain present. Removing a field
from the mapping removes it from front matter. Apply the document through the
same guarded interface used for slides:

```console
quarkfoil deck apply lecture.md --edit metadata.yml
```

Quarkfoil validates the YAML and revision, changes only front matter, and keeps
the slide source byte-for-byte unchanged. Nested `assets`, `defaults`, `social`,
and other mappings require no special flags.

## A prompt you can copy

Replace `lecture.md` with the name of your presentation and give the assistant
this instruction:

> Help me edit `lecture.md` with Quarkfoil. Before making changes, run
> `quarkfoil deck guide`. Treat `lecture.md` as opaque: do not read or modify it
> with shell text tools, Python, or a generic patch tool. Access it only through
> `quarkfoil deck inspect` and `quarkfoil deck apply`; generic editing tools may
> modify only generated edit documents. Ask me before deleting any slide.

That is enough for the assistant to discover the available commands. You can
then make normal requests, for example:

- “Make slide 3 shorter and easier to read.”
- “Add a summary slide after the results.”
- “Move the motivation slide before the model description.”
- “Review the deck and suggest changes, but do not apply them yet.”

## Create a presentation without starting the editor

An assistant can initialize a presentation and continue working without
starting a long-running browser server:

```console
quarkfoil deck create lecture.md \
  --title "Quantum simulation" \
  --author "Ada Lovelace" \
  --theme scientific-dark
```

The parent directory must already exist. The command accepts `.md` and
`.markdown`, initializes a missing or whitespace-only file, and refuses to
replace any nonempty file. It prints the path and initial revision as JSON.
After creation, the normal inspect-and-apply workflow applies.

Open the presentation in Quarkfoil while you work if you want to review each
change visually. A clean editor reloads changes made by the assistant. If you
have unsaved browser edits, Quarkfoil asks you to compare the two versions
instead of silently replacing either one.

## Let the assistant see the slides

Checking the structure of a deck does not show whether text is clipped,
an equation runs off the slide, or an overlay covers a figure. The assistant can
look for itself:

```console
quarkfoil deck render lecture.md --slides 4,7 --output lecture-render
```

This writes `slide-04.png` and `slide-07.png`, each 1280 × 720 pixels and named
by the slide's number in the deck, and prints their paths as JSON. Without
`--slides` every presented slide is rendered; without `--output` the images go
to a new temporary directory. `--width 640` produces smaller images. The images
show the slide as presented, with every fragment visible and without speaker
notes. Trashed slides are not presented and cannot be rendered.

Rendering uses Chrome, Chromium, Edge, or Firefox, whichever is installed
first, as [printing](PRINT.md#browsers) does; `--browser` names one. If the
deck changes while it is being rendered the command fails with
`revision_changed`, so the images always match the revision it reports.

## Keep speaker notes private

Speaker notes are sent to the assistant by default because they can provide
useful context. If they contain private material, add this sentence to your
prompt:

> Always use `--no-notes` when inspecting or applying this presentation.

This hides notes from the assistant's command output. It never changes the
stored notes. Replacing a slide keeps its existing notes by default; deleting a
whole slide still deletes its notes with it.

## If something goes wrong

- If the assistant reports that `quarkfoil` was not found, install Quarkfoil
  and restart the assistant or its terminal.
- If it reports that the presentation changed, ask it to inspect the deck
  again and retry. This normally means you edited the deck at the same time.
- If your assistant cannot run terminal commands, it cannot use this
  integration directly. You can still ask it for Markdown and paste the result
  into Source mode yourself.
- Keep a normal version-control history or backups for important presentations,
  just as you would for any other document.

## Command reference for tool builders

The preferred agent workflow uses editable YAML-and-Markdown documents. Agents
should use this interface unless they specifically need the compatibility JSON
protocol. It keeps Markdown and LaTeX literal, carries its own revision guards,
and makes several edits in one atomic application without generating escaped
strings.

Before generating unfamiliar Quarkfoil structures, query the relevant guide
topic rather than guessing directive names or layout regions. The browser's
JavaScript parser remains canonical; `deck inspect` and `deck apply` validate
the same document structure through its Python mirror.

### Edit one slide without JSON

Ask Quarkfoil to create one directly editable document in a new directory:

```console
quarkfoil deck inspect lecture.md --slides 12 --format edit --output lecture-edit
```

The output begins with a guarded YAML header and continues as literal Markdown:

```yaml
---
quarkfoil_edit: 1
operation: replace
deck_revision: sha256:0123456789abcdef...
slide: 12
slide_revision: sha256:fedcba9876543210...
title: Result
layout: 1+1
section: null
trashed: false
notes: replace
---

## Result {.layout-1-1}

Literal Markdown and $\LaTeX$.
```

Edit the Markdown normally, keep the YAML header, and apply it:

```console
quarkfoil deck apply lecture.md --edit lecture-edit/slide-0012.md
```

The result is a concise YAML receipt. Quarkfoil checks both the exact deck
revision and the exact source fingerprint of the addressed slide while holding
the deck lock. A mismatch changes nothing. With `--no-notes`, inspection omits
speaker notes and writes `notes: preserve`; otherwise it includes notes and
writes `notes: replace` so visible note edits round-trip.

Repeat `--edit` to apply several documents sequentially in one atomic write:

```console
quarkfoil deck apply lecture.md \
  --edit revise-method.md \
  --edit move-summary.yml \
  --edit insert-outlook.md
```

Every document must carry the same deck revision. Slide numbers use sequential
semantics, so each operation addresses the deck produced by the preceding one.
Target fingerprints make stale target numbers fail instead of modifying a
different slide. Positional `after` values remain the caller's responsibility.

The five edit-document operations are:

- `replace`: YAML fields `slide`, `slide_revision`, and `notes`, followed by
  exactly one Markdown slide.
- `insert`: YAML field `slide`, meaning the resulting slide position, followed
  by exactly one Markdown slide.
- `delete`: YAML fields `slide` and `slide_revision`, with no body.
- `move`: YAML fields `slide`, `slide_revision`, and `after`, with no body.
- `substitute`: YAML fields `slide`, `slide_revision`, `expect`, `replacement`,
  and optional `count`. Use YAML literal blocks (`|-`) for multiline or
  equation-heavy fragments.

All operations also require `quarkfoil_edit: 1`, `operation`, and
`deck_revision`. Unknown fields, duplicate YAML keys, aliases, anchors, and
custom YAML tags are rejected.

Insert a new slide at its resulting position with YAML followed by Markdown:

```yaml
---
quarkfoil_edit: 1
operation: insert
deck_revision: sha256:0123456789abcdef...
slide: 13
---

## Outlook {.layout-1}

Literal Markdown and $\sum_i n_i$.
```

Delete, move, trash, and restore documents contain YAML only. Trash and
restore take the same header as delete:

```yaml
---
quarkfoil_edit: 1
operation: delete
deck_revision: sha256:0123456789abcdef...
slide: 12
slide_revision: sha256:fedcba9876543210...
---
```

```yaml
---
quarkfoil_edit: 1
operation: move
deck_revision: sha256:0123456789abcdef...
slide: 12
slide_revision: sha256:fedcba9876543210...
after: 5
---
```

For a literal substitution, keep both Markdown fragments in YAML block
scalars. Backslashes and quotes need no JSON escaping:

```yaml
---
quarkfoil_edit: 1
operation: substitute
deck_revision: sha256:0123456789abcdef...
slide: 12
slide_revision: sha256:fedcba9876543210...
count: 1
expect: |-
  The phase is $\ket{\mathbb{Z}_2}$.
replacement: |-
  The phase is $\ket{\mathbb{Z}_2 \times \mathbb{Z}_2}$.
---
```

`expect` must occur exactly `count` times within the addressed slide. The
default count is one. A mismatch exits with status 4 and changes nothing.

For a readable projection that is not intended to be applied, request several
slides at once:

```console
quarkfoil deck inspect lecture.md --slides 8,9,10 --format markdown
```

Quarkfoil separates them with numbered HTML comments. To create independent,
round-trippable files instead, select a new output directory:

```console
quarkfoil deck inspect lecture.md --slides 8,9,10 \
  --format edit --output inspected-slides
```

Quarkfoil creates the directory atomically with `manifest.yml` and one edit
document per slide. The destination must not already exist.

### Render slides to images

```console
quarkfoil deck render lecture.md [--slides 1,4] [--output DIRECTORY] \
  [--width 1280] [--browser PROGRAM] [--timeout SECONDS] [--compact]
```

On success the command prints:

```json
{
  "revision": "sha256:...",
  "output": "/abs/path/lecture-render",
  "browser": "/usr/bin/chromium",
  "width": 1280,
  "height": 720,
  "images": [{"slide": 4, "title": "Result", "file": "/abs/path/lecture-render/slide-04.png"}]
}
```

The output directory is created if missing; files of the same names are
replaced one at a time and other files are left alone. Errors are JSON on
stderr: `slide_not_found` and `slide_trashed` (exit 2) before a browser starts,
`browser_not_found` (exit 2), `render_failed` (exit 1) when the browser fails
or times out, and `revision_changed` (exit 2) when the deck changed during
rendering.

### YAML results and failures

Applying edit documents returns a short YAML receipt rather than echoing the
deck or the edited Markdown:

```yaml
quarkfoil_result: 1
revision: sha256:abcdef0123456789...
dry_run: false
operations:
  - operation: replace
    input: slide-12.md
    result_slide: 12
    slide_revision: sha256:9876543210abcdef...
diagnostics: []
```

Edit-document errors are YAML on standard error. Exit status 3 means the deck
changed after inspection. Exit status 4 means a narrower operation assumption
failed, such as a stale slide fingerprint or an exact substitution mismatch:

```yaml
quarkfoil_error: 1
error: slide_revision_mismatch
message: Slide 12 no longer identifies the inspected slide
operation: 1
input: slide-12.md
slide: 12
expected_slide_revision: sha256:0123456789abcdef...
actual_slide_revision: sha256:fedcba9876543210...
```

In every failure case, Quarkfoil leaves the presentation byte-for-byte
unchanged. `--dry-run` remains available for an explicitly requested preview,
but normal application already validates every ordered operation before its
single atomic write.

### Advanced compatibility: JSON protocol

The remainder of this page documents the original JSON interface. It remains
supported for existing integrations, callers that already produce structured
transactions, and source-file workflows. Agents changing slides should prefer
the guarded YAML framework above.

### Inspect a presentation

```console
quarkfoil deck inspect lecture.md
```

The command writes JSON containing the complete Markdown source, its revision,
parser diagnostics, and the numbered source of each slide. Slide numbers belong
to that revision: they must not be reused after the file changes.

Speaker notes are included by default. To keep notes out of an agent's context:

```console
quarkfoil deck inspect lecture.md --no-notes
```

`--no-notes` removes notes from the returned JSON, and the returned revision
still identifies the complete file including notes.

For a smaller response, `--no-source` omits the complete deck source,
`--slides 2,5` returns only those slides, and `--compact` removes indentation.
Requested slides are returned in deck order, and requesting a missing slide is
an error. Each slide includes a `slide_revision` fingerprint of its exact
stored source to help identify unchanged slides after a conflict. The
fingerprint is calculated before output redaction and therefore includes stored
notes. With `--no-notes`, it is not the hash of the returned `source` field.
The deck revision always identifies the exact complete file bytes and remains
the write guard.

Each projected slide also reports the governing section as an `id` and title,
or `null` before the first section. If a structural parser error makes slide
boundaries unreliable, numbered projection is rejected; use a full inspection
to diagnose and repair the source. This includes an `unterminated_fence` error
when a Markdown backtick or tilde fence reaches its directive boundary or the
end of the presentation without closing.

### Apply a transaction

Create a transaction containing the inspected revision and one or more
operations:

```json
{
  "revision": "sha256:0123456789abcdef...",
  "operations": [
    {
      "operation": "replace",
      "slide": 2,
      "source": "## Revised method {.layout-1}\n\nNew content.\n",
      "notes": "preserve"
    },
    {
      "operation": "insert",
      "after": 2,
      "source": "## Additional result {.layout-1}\n\nResult.\n"
    }
  ]
}
```

Apply it atomically:

```console
quarkfoil deck apply lecture.md transaction.json
```

Use `-`, or omit the transaction filename, to read JSON from standard input.
The revision can instead be supplied separately:

```console
quarkfoil deck apply lecture.md operations.json --if-revision sha256:0123456789abcdef...
```

Supported operations are:

- `replace`: replace `slide` with exactly one slide supplied as `source`.
  Its optional `notes` policy is `preserve` (the default), `replace` (use notes
  in `source`), or `remove`. Under `preserve`, any notes supplied in `source`
  are ignored.
- `insert`: insert one slide from `source` after `after`; zero inserts at the
  beginning.
- `delete`: delete `slide`. The final slide cannot be deleted.
- `move`: move `slide` after `after`; zero moves it to the beginning. A trashed
  slide cannot be moved (restore it first), and `after` cannot name a trashed
  slide, which would place the moved slide inside the Trash section; `insert`
  follows the same rule.
- `trash`: mark `slide` `.trashed` and move it into the
  `# Trash {#quarkfoil-trash .section .trash}` section at the end of the deck,
  creating the section if needed. The result is the text the editor's Trash
  command writes, and every trashed slide found elsewhere is gathered into the
  section too. The last active slide cannot be trashed, and no transaction may
  leave the presentation without an active slide.
- `restore`: remove `.trashed` from `slide` and move it after the last active
  slide; the Trash section disappears with its last slide.
- `substitute`: replace literal `expect` text within one `slide`. The text must
  occur exactly once by default; set `count` to another positive exact count.
  A mismatch exits with status 4 and changes nothing. `replacement` may be
  empty.

For equation-heavy or otherwise complex Markdown, `replace` and `insert` may
use `source_file` instead of `source`:

```json
{
  "operation": "replace",
  "slide": 12,
  "source_file": "fragments/slide-12.md",
  "source_revision": "sha256:0123456789abcdef..."
}
```

The file contains ordinary, unescaped Markdown. Exactly one of `source` and
`source_file` is required. Relative paths use the transaction file's directory,
or the current directory when the transaction comes from standard input.
Quarkfoil reads each fragment once and validates all fragments before locking
and changing the deck. `source_revision` is optional; when present, it must
match the SHA-256 revision of the exact fragment bytes. Fragment files must be
UTF-8, contain exactly one slide, and are never copied or deleted by Quarkfoil.

Operations run sequentially. A slide number in each operation refers to the
presentation produced by the preceding operation in the same transaction.
For example, inserting after slide 2 makes the inserted slide number 3, so a
following replacement of slide 3 replaces the new slide. Trashed slides remain
part of the numbering. Moving a slide after itself is invalid; moving it to its
current position changes nothing.

Number shifts caused by structural operations are not all listed as changed
slides. For example, after deleting slide 2, the old slide 3 is now slide 2:

```json
{"operations": [
  {"operation": "delete", "slide": 2},
  {"operation": "substitute", "slide": 2, "expect": "Old third", "replacement": "Revised third"}
]}
```

The second operation addresses the already-renumbered deck. Quiet results list
surviving slides explicitly targeted by operations, while `operation_results`
records moves, deletions, and final target numbers.

On success, the command returns a new snapshot and revision as JSON. Add
`--no-notes` to omit notes from that returned snapshot; it does not control the
replacement policy. Use `--quiet` for the revision, changed slides,
per-operation results, and diagnostics without a full-deck snapshot. Use
`--compact` for unindented JSON. Use `--dry-run` (or `--check`) to resolve and
validate every sequential operation without writing the presentation. Dry-run
is not recommended for ordinary edits: normal apply performs the same
validation, checks the exact deck revision, and commits only after the complete
transaction succeeds. Use dry-run only when a separate preview is wanted.
Quiet changed-slide records omit Markdown source; they retain the final number,
section, title, layout, trash state, and exact stored-source fingerprint.

Run `quarkfoil deck protocol` for the versioned, machine-readable contract.
Successful data is written to standard output. Errors are JSON on standard
error: status 2 means an invalid request, and status 3 is a revision conflict.
Status 4 means a `substitute` expectation did not match its exact requested
count. Validation errors identify the failing operation. Parser warnings are
returned as diagnostics; parser errors reject the transaction. Deleting the
last slide from a section succeeds but returns an `empty_section` warning.

### Conflict and safety behavior

Quarkfoil acquires a cross-process lock shared with running editor servers,
reads the current file, and compares its revision while holding that lock. If
the revision differs, the command exits with status 3 and changes nothing.
Invalid transactions exit with status 2 and also change nothing.

After all operations succeed, Quarkfoil validates the complete result, writes a
temporary sibling file, flushes it, and atomically replaces the presentation.
Failures leave the original file byte-for-byte unchanged. Untouched Markdown is
retained, and the result is written as UTF-8 without a byte-order mark and with
LF line endings, whatever the deck or the edit documents used (see
[encoding and line endings](FORMAT.md#encoding-and-line-endings)). On POSIX systems its permission bits
are retained; on Windows Quarkfoil uses the native replacement operation to
retain file attributes and access-control lists. Revisions are SHA-256 hashes
of the exact UTF-8 file bytes, without newline normalization: the first write
to a CRLF deck therefore changes its revision.
A clean browser editor reloads the external revision; an editor with unsaved
work uses its normal external-change reconciliation flow.
