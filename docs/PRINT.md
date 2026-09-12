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

The first of these that is installed is used:

1. Chrome, Chromium, or Edge
2. Firefox

Name a different one with `--browser`, either as a program on `PATH` or as a
full path:

```console
quarkfoil print lecture.md --browser firefox
quarkfoil print lecture.md --browser "/Applications/Firefox.app/Contents/MacOS/firefox"
```

Both browsers produce pages of the same size. Chromium reads the page size from
the presentation itself; Firefox prints on the paper its settings name, so
Quarkfoil writes the slide size into the temporary profile it prints with.

If neither browser is installed, the command says so and does nothing. Install
one, or open the presentation and use **Print / PDF** in a browser you have.

## While it runs

A deck of a few dozen slides takes a few seconds. Large images and video
posters take longer, since the browser waits for every font and image before
printing. `--timeout` raises the 180-second limit for a very large deck:

```console
quarkfoil print lecture.md --timeout 600
```

The browser writes the PDF beside its destination and Quarkfoil renames it into
place once it is complete, so an existing PDF is replaced in a single step and
is never left half written. A failed run leaves the previous file untouched.

## Video slides

A PDF page cannot play video. A video prints as a still frame, its poster
image when it has one. Export the presentation as a
[static website](EXPORT.md) when the motion matters.

## Printing from the browser instead

The editor toolbar and every exported presentation still offer **Print / PDF**,
described in the [export guide](EXPORT.md#print-or-save-as-pdf). Use it for a
quick look. Set the paper size to a custom 13.33 × 7.5 inches, the margins to
none, and enable background graphics if you want the same result by hand.
