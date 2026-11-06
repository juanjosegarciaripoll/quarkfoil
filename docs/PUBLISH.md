# Publish a collection of talks

`quarkfoil publish` puts a presentation into a *collection*: a folder holding
many talks that share one copy of the player and one pool of assets, with a
listing page in front of them. It is the third way Quarkfoil writes a
presentation out, beside a self-contained [static export](EXPORT.md) and an
editable [project copy](PACK.md), and it changes neither of them.

```console
quarkfoil publish lecture.md --site ~/talks
quarkfoil publish lecture.md --site homepage:talks/
```

The destination may be a local directory or an rsync destination; everything
else is identical.

## What a collection looks like

```text
talks/
├── index.html                    the listing, plain HTML
├── collection.json               heading, standfirst, and public URL
├── 2026-inc-school/
│   ├── index.html                the deck page
│   ├── presentation.md           published unchanged
│   └── meta.json                 what the listing is built from
└── assets/
    ├── quarkfoil/0.5.0/          player, Reveal.js, KaTeX, fonts, notices
    └── f/9c/9c3f1a2b…-transmon.png
```

Every asset is stored under a name derived from its content. Two decks that use
the same figure store it once, however many collections of slides reuse it, and
two *different* figures that happen to share a file name are simply two
entries. Nothing has to be renamed, and no collision has to be resolved.

The deck's own Markdown is published exactly as written, still saying
`figures/transmon.png`. The page carries a small map from those paths to the
pool, which the player consults when it renders. Nothing rewrites the
presentation, so what a reader downloads is what you wrote.

The runtime folder is named after the Quarkfoil version that built it.
Publishing with a newer Quarkfoil adds a folder rather than replacing one, so
talks published earlier keep rendering exactly as they did.

## What controls the listing

The listing is built from front matter, so a talk describes itself:

```yaml
---
title: Superconducting quantum circuits
description: A brief and biased introduction to circuit QED, from the Meissner
  effect to quantum simulation with transmons.
event: INC School, Innsbruck
date: 2026-09-07
---
```

`title` and `description` are the ordinary [format fields](FORMAT.md#front-matter);
`description` falls back to `subtitle`. `event` and `date` are read only by the
listing. `date` is required for a published talk, and an unreadable or missing
one stops the publish rather than guessing a year for a public page.

Add `unlisted: true` to publish a talk that the listing leaves out. The page is
reachable by its URL; it simply does not appear.

The page groups talks by year, newest year first and newest talk first inside
it. It is generated at publish time and shipped as static HTML: every title,
event and description sits in the markup, so search engines read the whole
listing without running any JavaScript.

`--index-title` and `--index-lede` set the heading and the sentence under it.
Both are remembered in `collection.json`, so a later publish does not reset
them, and editing that file changes the page on the next publish.

Set the public address once as well:

```console
quarkfoil publish lecture.md --site homepage:talks/ \
  --site-url https://example.org/talks/
```

The normalized URL is remembered as `url` in `collection.json`, just like the
heading and standfirst. Every later publish to that destination reads it before
staging the talk and writes the resolved settings back. Quarkfoil cannot infer
this address from an rsync destination: `homepage:talks/` says where files go,
not which DNS name and web-server path exposes them. `--index-only --site-url`
can initialize or change the setting without publishing a deck. If the public
URL itself changes, republish existing decks so their static canonical and card
tags acquire the new address.

Use `--index-only` to rebuild the listing without publishing a deck, and
`--no-index` to publish a deck without touching it.

## Link-sharing cards

Once the collection has a public URL, every published talk includes canonical,
Open Graph, and Twitter/X metadata with absolute URLs. Quarkfoil renders the
first visible Front page slide onto a 1200x630 card; if there is no such slide,
it uses the first visible slide. The 16:9 slide is centered
without cropping, leaving narrow side margins on the approximately 1.91:1
social canvas. Chrome, Chromium, or Edge is required for this capture, as with
`export --preview`.

Front matter can select a different slide by stable heading ID:

```yaml
social:
  slide: main-result
  alt: Main experimental result of the talk
```

```markdown
## Main result {#main-result .layout-1}
```

A one-based page number is accepted for convenience, but a stable ID survives
insertions and reordering. Alternatively, use a prepared figure without
launching a browser:

```yaml
social:
  image: figures/social-card.png
  alt: Quantum processor and its control stack
```

`social.image` stays inside the presentation directory and is copied into the
same content-addressed pool as other figures. Reusing identical bytes reuses
the uploaded object; changing the card creates a new hashed URL, which also
avoids stale social-crawler caches. For custom cards, 1200x630 PNG, JPEG, or
WebP is a good target; social platforms do not consistently accept SVG cards.
Do not set both `social.image` and `social.slide`. When neither is set, the
opening-slide default applies. `social.alt` defaults to the presentation title.

## A course is one entry, not nine

A talk that belongs to a course, a school, or any other run of related talks
names it:

```yaml
series: Quantum Simulation Platforms
part: 3
series-description: Nine lectures on the platforms that simulate quantum matter.
```

The listing then shows **one card for the series** — its name, the occasion,
how many talks it holds, and the range of dates — instead of burying single
talks under nine siblings. The card links to a page of its own at
`series/<name>/`, which lists the talks in the order they were given: by
`part` when every member has one, and by date otherwise.

`series-description` is read from whichever member defines it first, so it
need not be repeated in each deck. A series is filed under the year of its
most recent talk, so one that runs across New Year appears once. `series` is
the only field needed; `part` and `series-description` are optional.

The pages under `series/` are regenerated from the talks on every publish, so
a series whose talks are gone loses its page. A talk may not be named
`series`, which is reserved for them.

## Publishing a course in one go

Several decks can be published together, which is how a course is meant to go
up:

```console
quarkfoil publish presentations/0*.md --site homepage:talks/
```

They are staged as one collection update: the shared figures cross the wire
once for the whole course rather than once per lecture, and the listing is
rebuilt a single time at the end. Each deck's folder is named after its file;
`--name` renames one, and so applies only when publishing a single deck.

## Speaker notes are left out

A published deck's `presentation.md` is a file anyone can open, and speaker
notes are written for the presenter, so publishing omits them. The deck on
disk is untouched: only the published copy loses them, and the notes you
present from stay where they are.

Add `--notes` to publish them anyway, which also restores Reveal.js's speaker
view on the published page. `--no-notes` is accepted and is the default.

This is the one place `publish` deliberately differs from
[`export`](EXPORT.md), which keeps notes unless `--no-notes` is given: an
export is a folder you hand to someone, while publishing puts the deck at a
public URL.

## Publishing to a web host

A remote `--site` is an ordinary rsync destination:

| You write | Meaning |
|---|---|
| `~/talks`, `./talks`, `C:\talks` | local directory |
| `homepage:talks/` | remote over ssh |
| `user@host:/var/www/talks/` | remote over ssh |
| `rsync://host/module/talks/`, `host::module/talks/` | rsync daemon |

Quarkfoil reports which it read before it transfers anything. A target is
remote when it starts with `rsync://`, contains `::`, or has two or more
characters before a colon, so a Windows drive letter stays local.

For an existing collection, Quarkfoil uses three remote sessions: one read and
two writes. The first rsync reads `collection.json` and every talk's
`meta.json` together. The shared pool and collection-owned pages then need
different write policies:

```console
rsync ... --include=meta.json --include=collection.json homepage:talks/ <state>/
rsync -rltpL --ignore-existing <staged>/assets/ homepage:talks/assets/
rsync -rltpL --delete --delay-updates \
  <staged>/2026-inc-school <staged>/index.html \
  <staged>/collection.json <staged>/series homepage:talks/
```

The shared half is **append-only**: `--ignore-existing` never deletes, and a
name that already exists holds the same bytes by construction, so nothing is
re-sent. Every talk folder and the generated listing, settings, and series
pages are named as sources in one batched transfer. A re-published talk owns
its folder, and `--delay-updates` swaps files in at the end so a reader does not
catch it half-changed. Although the destination is the collection root,
`--delete` applies only inside the explicitly named source directories. It
cannot remove another talk, the asset pool, or an unrelated root file.

Nothing is mirrored locally. Quarkfoil stages the deck in a temporary folder of
symlinks — a few hundred kilobytes — and rsync sends only the bytes the host is
missing. The staging folder is removed afterwards.

`--dry-run` passes through to every transfer and reports what would move.
Publishing to a remote target needs `rsync` on the `PATH`; `--rsync` selects a
different program. Quarkfoil handles no credentials: ssh does, exactly as it
does for your other rsync targets.

## What the collection does not do

Files are never removed from the pool, so a figure replaced by a new version
leaves its predecessor behind. That is what makes publishing safe to interrupt
and safe to run from any machine. Collecting the unreferenced ones is a
deliberate, separate operation, not something a publish does on its own.

An image written inside prose, rather than as a slide's own image block, is not
resolved through the asset map. Quarkfoil keeps a private copy of it beside the
deck so the page is still correct, and says so while publishing.

## Recover an editable project

The published Markdown and its asset map let the command line reconstruct
the public version as a local project without changing the site:

```console
quarkfoil download https://example.org/talks/quantum-simulation/ \
  --output presentations/quantum-simulation
```

See [Download a published talk](DOWNLOAD.md) for conflict handling and the
limits imposed by notes omitted during publishing or a trimmed bibliography.
