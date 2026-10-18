// Minimal micron renderer for MeshDeck previews and node browsing.
// Micron (from NomadNet): `>`/`>>`/`>>>` headings, `` `= `` code fences,
// `` `!bold`! ``, `` `_underline`_ `` and `` `*italic`* `` toggles,
// `[label`target`params]` links, `-` horizontal rules, `•` bullets,
// `` `[literal]` `` inline literals, colour/alignment tags `Fxxx`/`Bxxx`/
// `a`/`b`/`c`/`f`/`l`/`r` and ``` `` ``` resets are stripped.
//
// The output is fed to {@html}, so every piece of page text must go through
// escapeHtml() and only our own markup is emitted. Unknown backtick tokens are
// dropped rather than leaked as text.

/** Pages above this size are refused (protects the browser, not the parser). */
export const MAX_RENDER_BYTES = 512 * 1024;

/** Placeholder for `\`` so an escaped backtick survives token stripping. */
const LITERAL_TICK = "\uE000";

function escapeHtml(s: string): string {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** Only these schemes may become clickable; anything else renders as text. */
const SAFE_URL_RE = /^(?:https?:\/\/|mailto:)[^\s"'<>]+$/i;

const INTERNAL_LINK_RE = /^([0-9a-fA-F]{32}):(\/.*)$/;

function htmlLink(label: string, target: string): string {
  const lab = escapeHtml(label.trim());
  const t = target.trim();
  if (!t) return lab;

  // Node-qualified page link: <32-hex node hash>:/page/other.mu
  const internal = INTERNAL_LINK_RE.exec(t);
  if (internal) {
    return `<a href="#" class="micron-link" data-node="${escapeHtml(
      internal[1] ?? "",
    )}" data-path="${escapeHtml(internal[2] ?? "")}">${lab}</a>`;
  }
  // Same-node relative link: /page/other.mu (the reader fills in the node).
  if (t.startsWith("/")) {
    return `<a href="#" class="micron-link" data-node="" data-path="${escapeHtml(t)}">${lab}</a>`;
  }
  if (SAFE_URL_RE.test(t)) {
    return `<a href="${escapeHtml(t)}" rel="noopener noreferrer" target="_blank">${lab}</a>`;
  }
  // Unknown scheme (javascript:, data:, …): never clickable.
  return lab;
}

function renderInline(raw: string): string {
  // Escaped backticks are literal text; strip any literal placeholder the
  // page itself might contain so it cannot smuggle HTML.
  const text = raw.replaceAll(LITERAL_TICK, "").replaceAll("\\`", LITERAL_TICK);
  const out: string[] = [];
  let bold = false;
  let underline = false;
  let italic = false;

  const closeAll = () => {
    if (italic) out.push("</em>");
    if (underline) out.push("</u>");
    if (bold) out.push("</strong>");
    italic = underline = bold = false;
  };

  let i = 0;
  while (i < text.length) {
    const ch = text.charAt(i);

    if (ch === "`") {
      // Inline literal: `[content]`
      if (text.charAt(i + 1) === "[") {
        const end = text.indexOf("]", i + 2);
        if (end !== -1 && text.charAt(end + 1) === "`") {
          out.push(
            `<code class="micron-inline-code">${escapeHtml(text.slice(i + 2, end))}</code>`,
          );
          i = end + 2;
          continue;
        }
      }

      const next = text.charAt(i + 1);
      if (next === "`") {
        closeAll();
        i += 2;
        continue;
      }
      if (next === "!") {
        bold = !bold;
        out.push(bold ? "<strong>" : "</strong>");
        i += 2;
        continue;
      }
      if (next === "_") {
        underline = !underline;
        out.push(underline ? "<u>" : "</u>");
        i += 2;
        continue;
      }
      if (next === "*") {
        italic = !italic;
        out.push(italic ? "<em>" : "</em>");
        i += 2;
        continue;
      }

      // Colour / alignment / reset tags.
      const token = /^`(?:[FB](?:T[0-9a-fA-F]{6}|[0-9a-fA-F]{3})|[fbaclr])/.exec(
        text.slice(i),
      );
      if (token) {
        i += token[0].length;
        continue;
      }

      // Unknown tag: drop the backtick and its word run so it cannot leak
      // into the rendered page as stray text.
      i += 1;
      while (i < text.length && /[A-Za-z0-9]/.test(text.charAt(i))) i += 1;
      continue;
    }

    if (ch === "[") {
      const end = text.indexOf("]", i + 1);
      if (end !== -1) {
        const inner = text.slice(i + 1, end);
        const parts = inner.split("`");
        const label = parts[0] ?? "";
        // `[label]` with no target is plain text; `[url]` links to the url.
        const target = parts.length === 1 ? label : (parts[1] ?? "");
        out.push(htmlLink(label, target));
        i = end + 1;
        continue;
      }
      out.push("[");
      i += 1;
      continue;
    }

    out.push(escapeHtml(ch));
    i += 1;
  }

  closeAll();
  return out.join("").trim().replaceAll(LITERAL_TICK, "`");
}

export function renderMicron(source: string): string {
  const bytes = new TextEncoder().encode(source).length;
  if (bytes > MAX_RENDER_BYTES) {
    return (
      `<p class="micron-notice">Page too large to render ` +
      `(${Math.ceil(bytes / 1024)} KiB; the limit is 512 KiB).</p>`
    );
  }
  if (source === "") return "";

  const out: string[] = [];
  let inCode = false;
  const code: string[] = [];

  const flushCode = () => {
    out.push(`<pre class="micron-code">${escapeHtml(code.join("\n"))}</pre>`);
    code.length = 0;
  };

  for (const rawLine of source.split("\n")) {
    const line = rawLine.replace(/\s+$/, "");
    if (line.trim() === "`=") {
      if (inCode) flushCode();
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      code.push(line);
      continue;
    }

    const m = line.match(/^(`?[!_*]?[Cc]?)?(>>>|>>|>)(.*)$/);
    if (m) {
      const marker = m[2] ?? ">";
      const level = marker === ">>>" ? 3 : marker === ">>" ? 2 : 1;
      out.push(`<h${level} class="micron-h${level}">${renderInline(m[3] ?? "")}</h${level}>`);
      continue;
    }
    if (line.trim() === "-" || line.trim() === "`-") {
      out.push("<hr/>");
      continue;
    }
    if (line.trim().startsWith("•")) {
      out.push(`<p class="micron-bullet">• ${renderInline(line.trim().slice(1).trim())}</p>`);
      continue;
    }
    if (line.trim() === "") {
      out.push("<br/>");
      continue;
    }
    out.push(`<p>${renderInline(line)}</p>`);
  }
  if (inCode) flushCode();
  return out.join("\n");
}
