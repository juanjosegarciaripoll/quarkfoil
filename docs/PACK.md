# Pack a project folder

`quarkfoil pack` copies a presentation and the files it actually uses into a
separate folder that remains an ordinary Quarkfoil project. Unlike
[static export](EXPORT.md), the result contains no player, no browser
libraries, and no `index.html`: it is source, and you keep editing it.

```console
quarkfoil pack lecture.md --output ~/talks/cern-2026
```

Open the copy exactly as you open any presentation:

```console
quarkfoil ~/talks/cern-2026/lecture.md
```

## What is copied

- The presentation itself, under its own file name.
- Images, videos, and posters referenced by the slides.
- The bibliography configured in front matter.
- Every directory listed under `assets.include`, recursively.

Paths keep their positions relative to the presentation, so the copy resolves
its figures without editing a single link. Files in the project that the deck
never mentions, including unused figures, are left behind; list a directory
under `assets.include` when you want it preserved wholesale. See the
[format reference](FORMAT.md#asset-folders) for the configuration and path
rules, which are the same ones static export obeys.

```text
cern-2026/
├── lecture.md
├── references.bib
└── figures/
    └── hardware-model.svg
```

This makes `pack` the way to split one crowded folder into one project per
talk, to hand a colleague a deck that is complete on arrival, or to archive a
presentation with exactly the assets it needs.

## Options

`--no-notes` removes speaker notes from the copied presentation. `--trim-bibliography`
keeps only the entries the slides cite, together with the entries those depend
on. Both options change the copy only; the original presentation and its
bibliography are untouched. They behave exactly as the
[matching export options](EXPORT.md#trim-the-bibliography).

## Repeated packs and existing folders

Quarkfoil assembles the copy in a temporary sibling folder and publishes it
only after everything succeeded, so a failed run leaves the destination as it
was.

An existing destination is reused. Unrelated files already there, such as your
own notes or a Git repository, are kept, and packing an unchanged project
again does nothing. Because the destination is a folder you edit, Quarkfoil
refuses to overwrite a file whose content differs from the one it is about to
write, and names the offending paths:

```console
$ quarkfoil pack lecture.md --output ~/talks/cern-2026
quarkfoil pack: Destination already holds different files; pass --force to replace them: lecture.md
```

Add `--force` to replace them. Use it deliberately: the differing file is
usually work done in the destination that packing again would discard.

The destination may not be an existing file, and it may not be the
presentation's own directory.

## Pack or export?

| Goal | Command |
| --- | --- |
| Keep working on the presentation elsewhere | `quarkfoil pack` |
| Publish or hand over a presentation-only website | `quarkfoil export` |

Both start from the same deck, and one does not replace the other: pack a
project to move it, export it when it is ready to be shown.
