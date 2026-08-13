# Security and trust model

Quarkfoil is a local editing tool, not a hardened multi-user web service.

## Defaults

- The server binds to `127.0.0.1` unless explicitly configured otherwise.
- The chosen presentation directory is the filesystem boundary; traversal outside it is rejected.
- Browser libraries are pinned and served locally. No runtime CDN is used.
- A restrictive Content Security Policy blocks external scripts, frames, objects, and connections.
- Markdown raw HTML is escaped rather than executed.
- SVG is loaded through `<img>` elements and is not injected into the application DOM.
- YAML is parsed as data and is not used to construct code.
- Deck saves are UTF-8 validated, size-limited, conflict-checked, and atomic.
- Local-server deck saves require a matching revision and are serialized so two
  API writers cannot both save against the same base revision.
- Asset uploads are size-limited and restricted to supported image and video extensions.

## Desktop bundles

The desktop launcher preserves the same server architecture. It always binds
an available port on `127.0.0.1`, disables source-development reloading, and
opens that loopback URL in the default browser. There is no desktop option to
bind a network interface. Closing the launcher stops the server and releases
the port; the launcher does not silently switch an existing process to a new
project root.

When a console is unavailable, startup and lifecycle diagnostics are written
to `Quarkfoil/Logs/quarkfoil.log` below `%LOCALAPPDATA%` on Windows or to
`~/Library/Logs/Quarkfoil/quarkfoil.log` on macOS. Linux uses
`${XDG_STATE_HOME:-~/.local/state}/quarkfoil/quarkfoil.log`. Logs include deck
paths and local URLs and should be reviewed before sharing. Development
bundles are unsigned and must not be treated as authenticated release
artifacts.

## User responsibilities

- Treat imported Markdown and assets as untrusted until reviewed.
- Review SVG files before redistributing a project.
- Do not bind Quarkfoil to a public or untrusted network interface.
- Keep backups or use version control; browser recovery snapshots are not archival storage.
- External editors and coding agents operate with their own filesystem
  permissions, outside Quarkfoil's project-directory boundary. Restrict their
  working directory and review their changes before saving or distributing a deck.
- Obtain permission for images, fonts, papers, and other material included in presentations.

## Reporting a vulnerability

Until a public repository and security contact are established, do not publish sensitive vulnerability details with a release archive. Add a private reporting address to this document before public distribution.
