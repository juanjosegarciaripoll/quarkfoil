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
├── collection.json               its heading and standfirst
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

Use `--index-only` to rebuild the listing without publishing a deck, and
`--no-index` to publish a deck without touching it.

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

Two transfers run, and they differ deliberately:

```console
rsync -rltL --ignore-existing <staged>/assets/  homepage:talks/assets/
rsync -rltL --delete --delay-updates <staged>/2026-inc-school/  homepage:talks/2026-inc-school/
```

The shared half is **append-only**: `--ignore-existing` never deletes, and a
name that already exists holds the same bytes by construction, so nothing is
re-sent. The deck's own folder is mirrored, because a re-published talk owns
it; `--delay-updates` swaps its files in at the end, so a reader loading the
talk mid-publish does not catch it half-changed. `--delete` is never run at the
root of the collection: publishing a talk cannot remove another one.

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
