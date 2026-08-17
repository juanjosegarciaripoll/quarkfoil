import { parseDeck } from "./parser.js";

export function externalDeckAction({ knownHash, diskHash, dirty, valid }) {
  if (!diskHash || diskHash === knownHash) return "unchanged";
  if (!valid) return "conflict";
  return dirty ? "conflict" : "reload";
}

function slideKeys(deck) {
  const occurrences = new Map();
  return deck.slides.map(slide => {
    if (slide.headingAttrs.id) return `id:${slide.headingAttrs.id}`;
    const title = slide.title.trim();
    const occurrence = (occurrences.get(title) || 0) + 1;
    occurrences.set(title, occurrence);
    return `title:${title}:${occurrence}`;
  });
}

function sameList(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function chooseThreeWay(base, browser, disk) {
  if (browser === disk) return { side: "browser", conflict: false };
  if (browser === base) return { side: "disk", conflict: false };
  if (disk === base) return { side: "browser", conflict: false };
  return { side: "browser", conflict: true };
}

export function externalMergePlan(baseSource, browserSource, diskSource) {
  const base = parseDeck(baseSource);
  const browser = parseDeck(browserSource);
  const disk = parseDeck(diskSource);
  const keys = slideKeys(base);
  const browserKeys = slideKeys(browser);
  const diskKeys = slideKeys(disk);
  const sameSections = base.sections.map(item => item.raw).join("\n") === browser.sections.map(item => item.raw).join("\n")
    && base.sections.map(item => item.raw).join("\n") === disk.sections.map(item => item.raw).join("\n");
  if (!sameList(keys, browserKeys) || !sameList(keys, diskKeys) || !sameSections) {
    return { automatic: false, reason: "Slides or sections were inserted, deleted, reordered, or renamed; review the Markdown manually.", mergedSource: browserSource, changes: [] };
  }
  const changes = [];
  const replacements = [];
  for (let index = 0; index < base.slides.length; index += 1) {
    const baseRaw = base.slides[index].raw;
    const browserRaw = browser.slides[index].raw;
    const diskRaw = disk.slides[index].raw;
    if (browserRaw === baseRaw && diskRaw === baseRaw) continue;
    const choice = chooseThreeWay(baseRaw, browserRaw, diskRaw);
    changes.push({ key: keys[index], title: base.slides[index].title || `Slide ${index + 1}`, index, ...choice });
    replacements.push({ start: disk.slides[index].range.start, end: disk.slides[index].range.end, index });
  }
  const baseFront = baseSource.slice(0, base.frontMatterRange.end);
  const browserFront = browserSource.slice(0, browser.frontMatterRange.end);
  const diskFront = diskSource.slice(0, disk.frontMatterRange.end);
  if (browserFront !== baseFront || diskFront !== baseFront) {
    const choice = chooseThreeWay(baseFront, browserFront, diskFront);
    changes.unshift({ key: "front-matter", title: "Presentation settings", index: -1, ...choice });
    replacements.push({ start: 0, end: disk.frontMatterRange.end, index: -1 });
  }
  return { automatic: true, base, browser, disk, diskSource, changes, replacements };
}

export function renderExternalMerge(plan, selections = {}) {
  if (!plan.automatic) return plan.mergedSource;
  let source = plan.diskSource;
  for (const replacement of [...plan.replacements].sort((left, right) => right.start - left.start)) {
    const change = plan.changes.find(item => item.index === replacement.index);
    const side = selections[change.key] || change.side;
    const deck = side === "disk" ? plan.disk : plan.browser;
    const value = replacement.index === -1
      ? deck.source.slice(0, deck.frontMatterRange.end)
      : deck.slides[replacement.index].raw;
    source = `${source.slice(0, replacement.start)}${value}${source.slice(replacement.end)}`;
  }
  return source;
}

export function responseRevision(response) {
  return response.headers.get("ETag")?.replace(/^\"|\"$/g, "") || "";
}
