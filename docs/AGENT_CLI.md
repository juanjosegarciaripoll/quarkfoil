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

This hides notes from the assistant's command output. When the assistant
replaces a slide with `--no-notes`, Quarkfoil keeps that slide's existing notes.
Deleting a whole slide still deletes its notes with it.

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

The remainder of this page documents the machine-readable interface. Most
users do not need to run these commands themselves.

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
omit notes from that returned snapshot and preserve existing notes on replaced
slides. Explicitly deleting a slide still removes the complete slide.

### Conflict and safety behavior

Quarkfoil acquires a cross-process lock shared with running editor servers,
reads the current file, and compares its revision while holding that lock. If
the revision differs, the command exits with status 3 and changes nothing.
Invalid transactions exit with status 2 and also change nothing.

After all operations succeed, Quarkfoil validates the complete result, writes a
temporary sibling file, flushes it, and atomically replaces the presentation.
A clean browser editor reloads the external revision; an editor with unsaved
work uses its normal external-change reconciliation flow.
