export function externalDeckAction({ knownHash, diskHash, dirty, valid }) {
  if (!diskHash || diskHash === knownHash) return "unchanged";
  if (!valid) return "conflict";
  return dirty ? "conflict" : "reload";
}

export function responseRevision(response) {
  return response.headers.get("ETag")?.replace(/^\"|\"$/g, "") || "";
}
