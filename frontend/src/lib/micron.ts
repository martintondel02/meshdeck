// Minimal micron renderer for MeshDeck previews and node browsing.
// Micron (from NomadNet): `>`/`>>`/`>>>` headings, `` `= `` code fences,
// `*bold*`/`!bold!` toggles, `_underline_`, `[label`target`params]` links,
// `-` horizontal rules, `•` bullets, inline tokens `Fxxx`/`Bxxx` (colors),
// `a`/`b`/`f` resets and `c` center alignment are stripped.

function escapeHtml(s: string): string {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const TOKEN_RE = /`(?:[A-Ba-bFf]\w*|[acf])/g; // color + alignment/reset tokens

function renderInline(raw: string): string {
  let text = " " + raw + " "; // pad so tokens at edges match

  // links first: [label`target`params] or [label`target] or plain [label]
  const linkRe = /\[([^`[]+?)(?:`([^`\]]+))(?:`[^`\]]+)?\]/g;
  text = text.replace(linkRe, (_m, label: string, target?: string) => {
    const lab = escapeHtml(label.trim());
    if (target) {
      const [host = "", pagePath = ""] = target.split(":", 2);
      if (pagePath) {
        const node = escapeHtml(host);
        const pp = escapeHtml(pagePath);
        return `<a href="#/browse/${encodeURIComponent(node)}/${encodeURIComponent(pp)}" data-node="${node}" data-path="${pp}">${lab}</a>`;
      }
      return `<a href="${escapeHtml(target)}" rel="noopener noreferrer" target="_blank">${lab}</a>`;
    }
    return lab;
  });

  text = text.replace(TOKEN_RE, "");
  text = escapeHtml(text);

  // style toggles after escaping (backticks survive escapeHtml)
  text = text.replace(/`([*!_])([^`]+?)\1/g, (_m, mark: string, inner: string) => {
    if (mark === "*") return `<strong>${inner}</strong>`;
    if (mark === "!") return `<strong>${inner}</strong>`;
    return `<u>${inner}</u>`;
  });
  // leftovers: bare markers
  return text.replace(/`([*!_])/g, "").trim();
}

export function renderMicron(source: string): string {
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
    if (line.trim() === "`=" || line.trim() === "`= ".trim()) {
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
    if (line === "-" || line === "`-") {
      out.push("<hr/>");
      continue;
    }
    if (line.trim().startsWith("•") || line.trim().startsWith("• ")) {
      out.push(`<p class="micron-bullet">• ${renderInline(line.trim().slice(1))}</p>`);
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
