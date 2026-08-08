# Security model

- Browser libraries are pinned and served locally; no runtime CDN is used.
- The selected project directory is the server's filesystem boundary. Traversal outside it is rejected.
- The server binds to `127.0.0.1` by default.
- Deck saves are size-limited, UTF-8 validated and written atomically.
- Asset uploads are size-limited and restricted to common image extensions.
- A restrictive Content Security Policy blocks scripts, frames, objects and network resources outside the application origin.
- Presentation Markdown must not contain executable JavaScript. Raw HTML is outside the supported format.
- SVG files are loaded through image elements, not injected into the application DOM.
- YAML is parsed as data and is never used to construct executable code.

Imported presentations and assets should still be treated as untrusted content. Review source and SVG files before marking a project safe for redistribution.
