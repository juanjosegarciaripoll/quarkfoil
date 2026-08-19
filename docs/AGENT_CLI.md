# Use Quarkfoil with an AI assistant

Quarkfoil can work with coding assistants that are allowed to read files and
run commands on your computer. This includes terminal-based assistants and
editor assistants with access to your presentation folder. An ordinary web
chat cannot use this feature unless you upload files and edit them manually.

You do not need to teach the assistant Quarkfoil's file format or prepare JSON
files yourself. Quarkfoil gives it a short built-in guide and applies its slide
changes safely.

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

## A prompt you can copy

Replace `lecture.md` with the name of your presentation and give the assistant
this instruction:

> Help me edit `lecture.md` with Quarkfoil. Before making changes, run
> `quarkfoil deck guide`. Follow its inspect-and-apply workflow instead of
> editing the Markdown file directly. Ask me before deleting any slide.

That is enough for the assistant to discover the available commands. You can
then make normal requests, for example:

- “Make slide 3 shorter and easier to read.”
- “Add a summary slide after the results.”
- “Move the motivation slide before the model description.”
- “Review the deck and suggest changes, but do not apply them yet.”

Open the presentation in Quarkfoil while you work if you want to review each
change visually. A clean editor reloads changes made by the assistant. If you
have unsaved browser edits, Quarkfoil asks you to compare the two versions
instead of silently replacing either one.

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

### Edit one slide without JSON

Inspect one slide as a directly editable document:

```console
quarkfoil deck inspect lecture.md --slides 12 --format edit > slide-12.md
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
quarkfoil deck apply lecture.md --edit slide-12.md
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

Delete and move documents contain YAML only:

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
transactions, and source-file workflows. Agents editing Markdown directly
should prefer the YAML framework above.

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
- `move`: move `slide` after `after`; zero moves it to the beginning.
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
Failures leave the original file byte-for-byte unchanged. Untouched Markdown
and the deck's newline style are retained. On POSIX systems its permission bits
are retained; on Windows Quarkfoil uses the native replacement operation to
retain file attributes and access-control lists. Revisions are SHA-256 hashes
of the exact UTF-8 file bytes, without newline normalization.
A clean browser editor reloads the external revision; an editor with unsaved
work uses its normal external-change reconciliation flow.
