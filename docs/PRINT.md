# Print a PDF

Quarkfoil turns a presentation into a PDF with one page per slide:

```console
quarkfoil print lecture.md
```

The result is `lecture.pdf` beside the deck. Choose another name with
`--output`:

```console
quarkfoil print lecture.md --output ~/talks/cern-2026.pdf
```

## Pages the size of a slide

Slides are laid out on a 16:9 canvas of 1280 × 720 CSS pixels, so every page of
the PDF is exactly 13.33 × 7.5 inches (338.7 × 190.5 mm). Nothing is scaled
down to fit a sheet of A4 or Letter, and no white margin is added around the
slide.

That is the difference between this command and printing from the browser
yourself. A browser's print dialog puts the slides on whatever paper it was
last set to, which letterboxes a 16:9 deck onto a portrait page; the dialog's
paper setting also overrides the page size the presentation asks for. Printing
through `quarkfoil print` states the page size to the browser directly.

Speaker notes are left out, as they are when publishing.

## Browsers

Quarkfoil has no PDF renderer of its own. It exports the presentation to a
temporary website, serves it on a loopback address, and asks a browser already
installed on the computer to print it. The browser runs headlessly in a
throwaway profile and never touches the one you browse with.

Quarkfoil drives the browser through its own automation interface: the Chrome
DevTools Protocol for Chrome, Chromium, and Edge, and WebDriver BiDi for
Firefox. Both listen only on a loopback port the browser chooses. Quarkfoil
waits until the presentation reports that every slide is laid out and every
font and image has loaded, then asks for the PDF. It never relies on a guess at
how long loading takes.

Quarkfoil tries the installed browsers in this order and uses the first one
that starts:

1. Chrome, Chromium, or Edge
2. Firefox

A browser that is installed but cannot run headlessly is skipped with a note
explaining why, and the next one is tried. The usual case is a Chromium build
installed without an AppArmor profile on Ubuntu 23.10 or later, where AppArmor
blocks Chromium's sandbox; Quarkfoil never disables the sandbox to work around
it.

Name a different one with `--browser`, either as a program on `PATH` or as a
full path:

```console
quarkfoil print lecture.md --browser firefox
quarkfoil print lecture.md --browser "/Applications/Firefox.app/Contents/MacOS/firefox"
```

Both browsers produce pages of the same size: Quarkfoil states the slide size,
zero margins, and background printing in the print request itself.

A browser named with `--browser` is the only one tried. If it, or every
installed browser, fails to start, the command reports the browser's own
explanation and does nothing. If no browser is installed, it says so. Install
one, or open the presentation and use **Print / PDF** in a browser you have.

## While it runs

A deck of a few dozen slides takes a few seconds. Large images and video
posters take longer, since the browser waits for every font and image before
printing. `--timeout` raises the 180-second limit for a very large deck:

```console
quarkfoil print lecture.md --timeout 600
```

Quarkfoil writes the PDF beside its destination and renames it into place once
it is complete, so an existing PDF is replaced in a single step and
is never left half written. A failed run leaves the previous file untouched.

## Images instead of a PDF

`quarkfoil deck render` uses the same browsers to write one PNG image per slide.
It is meant for AI assistants checking their own edits, and is described in
[Use Quarkfoil with an AI assistant](AGENT_CLI.md#let-the-assistant-see-the-slides).

## Video slides

A PDF page cannot play video. A video prints as a still frame, its poster
image when it has one. Export the presentation as a
[static website](EXPORT.md) when the motion matters.

## Printing from the browser instead

The editor toolbar and every exported presentation still offer **Print / PDF**,
described in the [export guide](EXPORT.md#print-or-save-as-pdf). Use it for a
quick look. Set the paper size to a custom 13.33 × 7.5 inches, the margins to
none, and enable background graphics if you want the same result by hand.
