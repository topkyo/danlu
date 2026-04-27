// MIRROR of src/aiwiki/input_router.py — keep in sync.
// Pure function, no IO, no LLM, no fetch.
const ROUTE = {
  URL: "url",
  PDF: "pdf",
  IMAGE: "image",
  REPO: "repo",
  NOTE: "note",
  ASK: "ask"
};

const IMAGE_SUFFIXES = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"];

function classifyUniversalInput(value) {
  const payload = (value || "").trim();
  if (!payload) {
    throw new Error("empty input");
  }

  const lowerPayload = payload.toLowerCase();

  if (lowerPayload.startsWith("http://") || lowerPayload.startsWith("https://")) {
    let urlPath = "";
    try {
      const url = new URL(payload);
      urlPath = url.pathname.toLowerCase();
    } catch (e) {
      // Ignored: fallback to naive parsing if invalid URL
    }
    
    if (urlPath.endsWith(".pdf")) {
      return { route: ROUTE.PDF, payload, reason: "pdf-suffix-on-url" };
    }
    if (IMAGE_SUFFIXES.some(suffix => urlPath.endsWith(suffix))) {
      return { route: ROUTE.IMAGE, payload, reason: "image-suffix-on-url" };
    }
    return { route: ROUTE.URL, payload, reason: "url-scheme" };
  }

  if (lowerPayload.endsWith(".pdf")) {
    return { route: ROUTE.PDF, payload, reason: "pdf-suffix" };
  }

  if (IMAGE_SUFFIXES.some(suffix => lowerPayload.endsWith(suffix))) {
    return { route: ROUTE.IMAGE, payload, reason: "image-suffix" };
  }

  if (lowerPayload.startsWith("git@")) {
    return { route: ROUTE.REPO, payload, reason: "git-ssh-shorthand" };
  }

  if (lowerPayload.startsWith("ssh://")) {
    return { route: ROUTE.REPO, payload, reason: "ssh-scheme" };
  }

  if (lowerPayload.endsWith(".git")) {
    return { route: ROUTE.REPO, payload, reason: "git-suffix" };
  }

  if (lowerPayload.startsWith("note:")) {
    const notePayload = payload.substring("note:".length).trim();
    if (!notePayload) {
      throw new Error("empty note payload");
    }
    return { route: ROUTE.NOTE, payload: notePayload, reason: "note-prefix" };
  }

  if (payload.includes("\n")) {
    return { route: ROUTE.NOTE, payload, reason: "multiline-text" };
  }

  if (lowerPayload.startsWith("ask:")) {
    const askPayload = payload.substring("ask:".length).trim();
    return { route: ROUTE.ASK, payload: askPayload, reason: "ask-prefix" };
  }

  if (payload.includes("?")) {
    return { route: ROUTE.ASK, payload, reason: "contains-question-mark" };
  }

  return { route: ROUTE.ASK, payload, reason: "default-ambiguous-text" };
}
