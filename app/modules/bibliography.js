import { escapeHtml } from "./parser.js";

function plain(value = "") {
  return String(value).replace(/[{}]/g, "").replace(/--/g, "–").replace(/\\&/g, "&").trim();
}

export function parseBibliography(source) {
  if (!source.trim()) return [];
  const records = window.bibtexParse.toJSON(source);
  return records.map(record => ({
    key: record.citationKey,
    type: record.entryType,
    fields: Object.fromEntries(Object.entries(record.entryTags || {}).map(([key, value]) => [key.toLowerCase(), plain(value)])),
  }));
}

export function briefReference(entry) {
  const fields = entry?.fields || {};
  const authors = (fields.author || "Unknown author").split(/\s+and\s+/i);
  const family = authors[0].includes(",") ? authors[0].split(",")[0].trim() : authors[0].trim().split(/\s+/).pop();
  const author = authors.length > 1 ? `${family} et al.` : family;
  const venue = fields.journal || fields.booktitle || fields.publisher || "";
  const details = [venue, fields.volume, fields.pages || fields.number].filter(Boolean).join(" ");
  return [author, details, fields.year ? `(${fields.year})` : ""].filter(Boolean).join(", ");
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
    for (const overlay of slide.overlays.filter(item => item.type === "citation")) register(overlay.attrs.values.key || "");
  }
  return { source, entries, byKey, numbers, missing, error };
}

export function renderCitation(key, bibliography, { brief = false } = {}) {
  const number = bibliography?.numbers.get(key);
  const entry = bibliography?.byKey.get(key);
  if (!number || !entry) return `<span class="citation-missing">[? ${key}]</span>`;
  const doi = entry.fields.doi;
  const url = doi ? `https://doi.org/${encodeURI(doi)}` : entry.fields.url;
  const marker = `<span class="citation-number">[${number}]</span>`;
  const content = brief ? `${marker} ${escapeHtml(briefReference(entry))}` : marker;
  return url ? `<a class="citation" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${content}</a>` : `<span class="citation">${content}</span>`;
}
