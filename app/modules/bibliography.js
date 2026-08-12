import { escapeHtml } from "./parser.js";

const LATEX_ACCENTS = new Map([
  ["'", "\u0301"], ["`", "\u0300"], ["\"", "\u0308"], ["^", "\u0302"], ["~", "\u0303"],
  ["=", "\u0304"], [".", "\u0307"], ["u", "\u0306"], ["v", "\u030c"], ["H", "\u030b"],
  ["c", "\u0327"], ["k", "\u0328"], ["b", "\u0331"], ["d", "\u0323"], ["r", "\u030a"],
]);

const LATEX_LETTERS = new Map([
  ["aa", "å"], ["AA", "Å"], ["ae", "æ"], ["AE", "Æ"], ["oe", "œ"], ["OE", "Œ"],
  ["o", "ø"], ["O", "Ø"], ["l", "ł"], ["L", "Ł"], ["ss", "ß"], ["i", "ı"], ["j", "ȷ"],
]);

function latexToUnicode(value) {
  return String(value)
    .replace(/\\(["'`^~=.]|[uvHckbdr])\s*(?:\{\s*([A-Za-zıȷ])\s*\}|([A-Za-zıȷ]))/g, (_, accent, braced, bare) => {
      const letter = braced || bare;
      return `${letter}${LATEX_ACCENTS.get(accent)}`.normalize("NFC");
    })
    .replace(/\\(AA|AE|OE|aa|ae|oe|ss|[oOliLj])\b(?:\{\})?/g, (_, command) => LATEX_LETTERS.get(command))
    .replace(/\\([#$%&_{}])/g, "$1")
    .replace(/~/g, " ")
    .replace(/[{}]/g, "");
}

function plain(value = "") {
  return latexToUnicode(value).replace(/--/g, "–").trim();
}

const BIBLIOGRAPHY_FIELD_ORDER = [
  "author", "editor", "title", "journal", "booktitle", "publisher", "school", "institution",
  "series", "edition", "volume", "number", "pages", "address", "month", "year", "doi", "url", "note",
];
const BIBLIOGRAPHY_FIELD_POSITION = new Map(BIBLIOGRAPHY_FIELD_ORDER.map((field, index) => [field, index]));

function bibliographyRecords(source) {
  try { return window.bibtexParse.toJSON(source); }
  catch (reason) {
    const message = reason instanceof Error ? reason.message : String(reason);
    throw new Error(`Invalid BibTeX: ${message}`);
  }
}

export function parseBibliography(source) {
  if (!source.trim()) return [];
  const records = bibliographyRecords(source);
  return records.map(record => ({
    key: record.citationKey,
    type: record.entryType,
    fields: Object.fromEntries(Object.entries(record.entryTags || {}).map(([key, value]) => [key.toLowerCase(), plain(value)])),
  }));
}

export function formatBibliography(source) {
  if (!source.trim()) return "";
  if (/^\s*%/m.test(source)) throw new Error("Remove or convert % comments before reformatting the bibliography");
  if (/@(?:comment|preamble|string)\s*\{/i.test(source)) {
    throw new Error("Reformat supports ordinary bibliography entries, not @comment, @preamble, or @string directives");
  }
  const records = bibliographyRecords(source);
  if (records.some(record => !record.citationKey || !record.entryTags)) {
    throw new Error("Reformat supports ordinary bibliography entries, not @comment, @preamble, or @string directives");
  }
  records.sort((left, right) => {
    const a = left.citationKey.toLocaleLowerCase();
    const b = right.citationKey.toLocaleLowerCase();
    return a < b ? -1 : a > b ? 1 : left.citationKey < right.citationKey ? -1 : left.citationKey > right.citationKey ? 1 : 0;
  });
  return `${records.map(record => {
    const fields = Object.entries(record.entryTags).map(([key, value]) => [key.toLocaleLowerCase(), String(value).trim()]);
    fields.sort(([left], [right]) => {
      const a = BIBLIOGRAPHY_FIELD_POSITION.get(left) ?? BIBLIOGRAPHY_FIELD_ORDER.length;
      const b = BIBLIOGRAPHY_FIELD_POSITION.get(right) ?? BIBLIOGRAPHY_FIELD_ORDER.length;
      return a - b || left.localeCompare(right);
    });
    const width = Math.max(...fields.map(([key]) => key.length));
    const body = fields.map(([key, value]) => `  ${key.padEnd(width)} = {${value}},`).join("\n");
    return `@${record.entryType.toLocaleLowerCase()}{${record.citationKey},\n${body}\n}`;
  }).join("\n\n")}\n`;
}

export function uniqueCitationKey(proposed, existingKeys) {
  const base = String(proposed || "reference");
  const used = new Set([...existingKeys].map(key => String(key).toLocaleLowerCase()));
  if (!used.has(base.toLocaleLowerCase())) return base;
  for (const suffix of "abcdefghijklmnopqrstuvwxyz") {
    const candidate = `${base}${suffix}`;
    if (!used.has(candidate.toLocaleLowerCase())) return candidate;
  }
  let counter = 2;
  while (used.has(`${base}${counter}`.toLocaleLowerCase())) counter += 1;
  return `${base}${counter}`;
}

export function renameBibliographyEntry(source, key) {
  if (!/^[\w:./+-]+$/.test(key)) throw new Error(`Invalid citation key '${key}'`);
  let replaced = false;
  const renamed = String(source).replace(/^(\s*@[a-z]+\s*\{\s*)[^,\s]+/i, (whole, prefix) => {
    replaced = true;
    return `${prefix}${key}`;
  });
  if (!replaced) throw new Error("DOI service returned no bibliography entry");
  return renamed;
}

export function briefReference(entry) {
  const fields = entry?.fields || {};
  const authors = (fields.author || "Unknown author").split(/\s+and\s+/i);
  const family = authors[0].includes(",") ? authors[0].split(",")[0].trim() : authors[0].trim().split(/\s+/).pop();
  const author = authors.length > 1 ? `${family} et al.` : family;
  const type = String(entry?.type || "").toLocaleLowerCase();
  const thesis = type === "phdthesis" ? "PhD thesis" : type === "mastersthesis" ? "Master's thesis" : "";
  const venue = fields.journal || fields.booktitle || fields.publisher || fields.school || fields.institution || "";
  const details = thesis
    ? [thesis, venue].filter(Boolean).join(", ")
    : [venue, fields.volume, fields.pages || fields.number].filter(Boolean).join(" ");
  return [author, details, fields.year ? `(${fields.year})` : ""].filter(Boolean).join(", ");
}

export function attributionKeys(overlay) {
  const value = overlay?.attrs?.values?.keys || overlay?.attrs?.values?.key || "";
  return [...new Set(String(value).split(/[\s,;]+/).filter(Boolean))];
}

export function prepareBibliography(source, deck) {
  let entries = [];
  let error = null;
  try { entries = parseBibliography(source); } catch (reason) { error = reason.message; }
  const byKey = new Map(entries.map(entry => [entry.key, entry]));
  const numbers = new Map();
  const missing = new Set();
  const register = key => {
    if (!numbers.has(key)) numbers.set(key, numbers.size + 1);
    if (!byKey.has(key)) missing.add(key);
  };
  for (const slide of deck.slides) {
    const content = [slide.title, ...slide.cells.map(item => item.source), ...slide.overlays.map(item => item.source)].join("\n");
    const prose = content.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g).filter((_, index) => index % 2 === 0).join("\n");
    for (const match of prose.matchAll(/(?<!\\)\[@([\w:./+-]+)(?:\s*;\s*@([\w:./+-]+))*\]/g)) {
      for (const key of match[0].matchAll(/@([\w:./+-]+)/g)) register(key[1]);
    }
    for (const overlay of slide.overlays.filter(item => item.type === "citation" && item.attrs.values.display === "number")) {
      for (const key of attributionKeys(overlay)) register(key);
    }
  }
  return { source, entries, byKey, numbers, missing, error };
}

export function renderCitation(key, bibliography, { brief = false } = {}) {
  const number = bibliography?.numbers.get(key);
  const entry = bibliography?.byKey.get(key);
  if (!entry || (!brief && !number)) return `<span class="citation-missing">[? ${key}]</span>`;
  const doi = entry.fields.doi;
  const url = doi ? `https://doi.org/${encodeURI(doi)}` : entry.fields.url;
  const marker = `<span class="citation-number">[${number}]</span>`;
  const content = brief ? escapeHtml(briefReference(entry)) : marker;
  return url ? `<a class="citation" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${content}</a>` : `<span class="citation">${content}</span>`;
}
