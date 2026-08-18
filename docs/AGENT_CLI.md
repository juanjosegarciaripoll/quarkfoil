# Agent command-line interface

Quarkfoil provides a machine-readable interface for tools and language-model
agents that need to inspect or structurally edit a presentation. It uses the
same presentation model as the editor and protects every write with a SHA-256
revision check.

An agent can learn the complete compact protocol without loading this page:

```console
quarkfoil deck guide
```

## Inspect a presentation

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

`--no-notes` changes only the returned JSON. It does not modify the presentation,
and the returned revision still identifies the complete file including notes.

## Apply a transaction

Create a transaction containing the inspected revision and one or more
operations:

```json
{
  "revision": "sha256:0123456789abcdef...",
  "operations": [
    {
      "operation": "replace",
      "slide": 2,
      "source": "## Revised method {.layout-1}\n\nNew content.\n"
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
- `insert`: insert one slide from `source` after `after`; zero inserts at the
  beginning.
- `delete`: delete `slide`. The final slide cannot be deleted.
- `move`: move `slide` after `after`; zero moves it to the beginning.

Operations run sequentially. A slide number in each operation refers to the
presentation produced by the preceding operation in the same transaction.

On success, the command returns a new snapshot as JSON. Add `--no-notes` to
omit notes from that returned snapshot without removing them from the saved
presentation.

## Conflict and safety behavior

Quarkfoil acquires a cross-process lock shared with running editor servers,
reads the current file, and compares its revision while holding that lock. If
the revision differs, the command exits with status 3 and changes nothing.
Invalid transactions exit with status 2 and also change nothing.

After all operations succeed, Quarkfoil validates the complete result, writes a
temporary sibling file, flushes it, and atomically replaces the presentation.
A clean browser editor reloads the external revision; an editor with unsaved
work uses its normal external-change reconciliation flow.
