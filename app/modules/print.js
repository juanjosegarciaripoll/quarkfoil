export const pdfPrintView = (search = window.location.search) => new URLSearchParams(search).has("print-pdf");

export function pdfPrintUrl(location = window.location) {
  const url = new URL(location.href);
  url.searchParams.set("print-pdf", "");
  url.searchParams.set("print-dialog", "");
  url.hash = "";
  return url.href;
}

export const printShortcut = event => Boolean(
  (event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "p"
);

export async function openPrintDialogWhenReady(root = document) {
  if (root.fonts?.ready) await root.fonts.ready;
  const images = [...root.images].filter(image => !image.complete);
  await Promise.all(images.map(image => new Promise(resolve => {
    image.addEventListener("load", resolve, { once: true });
    image.addEventListener("error", resolve, { once: true });
  })));
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  window.print();
}
