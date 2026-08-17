# Referenced-only figure export plan

## Objective

Change static export so `assets.figures` is treated as an import destination,
not as a directory that is always published wholesale. Copy only figure files
referenced by the exported Markdown, while continuing to copy every directory
listed under `assets.include` recursively.

The exported presentation must retain the same project-relative paths as the
source deck. The presentation-directory boundary, atomic destination creation,
and no-overwrite behavior remain unchanged.

## Current behavior

`_configured_asset_folders()` combines `assets.figures` and `assets.include`
into one set. `_copy_project_assets()` recursively enumerates every configured
folder, so unused files under the figure-import directory are currently copied.
It also independently copies local paths discovered in Markdown, `src` and
`poster` attributes, and the configured bibliography.

## Implementation

1. Replace the combined configured-folder helper with parsed asset settings
   that preserve the distinction between one figure directory and the list of
   recursively included directories. Use the existing YAML front-matter loader
   rather than maintaining a second line-oriented interpretation.
2. Validate `assets.figures` and every `assets.include` entry as normalized,
   project-relative paths. Reject absolute paths, the project root, traversal,
   symlink escapes, and configured paths that exist as non-directories. A
   missing configured directory remains valid.
3. Build the export copy set from:
   - local Markdown image and link destinations;
   - overlay and video `src` and `poster` attributes;
   - the configured bibliography;
   - every regular file below each `assets.include` directory.
4. Do not enumerate `assets.figures`. References below it will already be in
   the copy set through Markdown or attribute discovery. Keep referenced files
   outside that directory working as they do now.
5. Preserve URL decoding, query/fragment removal, project-boundary checks,
   deterministic ordering, missing-reference errors, and target parent
   creation.
6. Keep `--no-notes` asset selection based on the note-free exported source,
   so an asset referenced only by removed notes is not published.
7. Keep `--preview` behavior unchanged. Its generated PNG is written directly
   into the configured figure directory inside the temporary export and does
   not need a source-project reference.
8. Keep imported-icon license discovery based on referenced icon paths. Do not
   copy unused icon SVGs or the private figure-directory metadata merely
   because they share the import directory.

## Regression coverage

Add exporter tests that prove:

- a referenced figure is copied and an unused sibling is omitted;
- nested referenced figures retain their relative paths;
- a custom `assets.figures` directory follows the same referenced-only rule;
- image paths, ordinary download links, video sources, and video posters are
  copied;
- URL-encoded local paths are decoded and copied correctly;
- remote, absolute, and fragment-only URLs are not treated as project files;
- every file under `assets.include` is retained, including unreferenced files;
- an asset referenced only from speaker notes is omitted with `--no-notes`;
- a referenced missing file still fails the export atomically;
- configured paths outside the project remain rejected;
- generated link-sharing previews still land under the configured figure
  directory and appear in Open Graph metadata.

Run the complete Python suite, a real local static-player browser check, a CDN
static-player browser check when network access is available, `git diff
--check`, and the final status inspection.

## Documentation changes

Update `docs/FORMAT.md` and `docs/EXPORT.md` to state explicitly:

- `assets.figures` selects the editor's import destination and only referenced
  files from it are exported;
- `assets.include` is the mechanism for directories that must be preserved
  wholesale;
- local files referenced outside `assets.figures` are still copied
  individually.

This is a behavior change from Quarkfoil 0.4.0 and should be noted in the
changelog when it is implemented.
