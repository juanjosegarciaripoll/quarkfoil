# Third-party licenses

Quarkfoil distributes the following pinned browser components. All four are
licensed under the permissive MIT License. Their complete upstream notices are
stored beside the vendored files and are included in Quarkfoil's source and
binary distributions.

| Component | Version | License and copyright notice | Source/archive SHA-256 |
|---|---:|---|---|
| Reveal.js | 5.2.1 | [MIT](app/vendor/reveal/LICENSE) — Copyright © 2011–2024 Hakim El Hattab and reveal.js contributors | `ad6fe79a57309a80a09a7ea7fa1d8cb260caf045567cb2198d70c0c896336257` |
| KaTeX, including its distributed fonts | 0.16.22 | [MIT](app/vendor/katex/LICENSE) — Copyright © 2013–2020 Khan Academy and other contributors | `aecf657d52774c7af21bd72da7825ef7844ac38af8a879e9fd200568f38a5cb4` |
| Marked | 15.0.12 | [MIT](app/vendor/marked/LICENSE.md) — Copyright © 2018+ MarkedJS and © 2011–2018 Christopher Jeffrey | `3e7e7d7feb3e5d58cb6c804f68ab5c24cc7e5eb6270fd6e5cbb9124739217d0c` |
| js-yaml | 4.1.0 | [MIT](app/vendor/yaml/LICENSE) — Copyright © 2011–2015 Vitaly Puzrin | `45dc3dd03dc07a06705a2c2989b8c7f709013f04bd5386e3279d4e447f07ebd7` |

The MIT License permits use, copying, modification, publication, distribution,
sublicensing, and sale. Its copyright and permission notices must remain in
copies or substantial portions of the software; the linked files satisfy that
notice requirement for the vendored copies.

When updating a dependency, review the new release's license and copyright
notice, update this document, and update the pinned checksum in
[`tools/fetch_vendor.py`](tools/fetch_vendor.py).
