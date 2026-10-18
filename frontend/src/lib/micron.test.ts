// Unit tests for the micron renderer. The renderer feeds {@html} in the Pages
// reader, so the escaping tests here are security tests, not cosmetics.
import { describe, expect, it } from "vitest";
import { MAX_RENDER_BYTES, renderMicron } from "./micron";

describe("renderMicron block elements", () => {
  it("renders heading levels", () => {
    expect(renderMicron(">One")).toContain('<h1 class="micron-h1">One</h1>');
    expect(renderMicron(">>Two")).toContain('<h2 class="micron-h2">Two</h2>');
    expect(renderMicron(">>>Three")).toContain('<h3 class="micron-h3">Three</h3>');
  });

  it("renders plain lines as paragraphs", () => {
    expect(renderMicron("hello")).toBe("<p>hello</p>");
    expect(renderMicron("first\nsecond")).toBe("<p>first</p>\n<p>second</p>");
  });

  it("renders bullets", () => {
    expect(renderMicron("• one")).toContain('<p class="micron-bullet">• one</p>');
  });

  it("renders a horizontal rule", () => {
    expect(renderMicron("-")).toBe("<hr/>");
  });

  it("renders code fences verbatim and escaped", () => {
    const html = renderMicron("`=\nif (a < b) & c {}\n`=");
    expect(html).toBe('<pre class="micron-code">if (a &lt; b) &amp; c {}</pre>');
  });

  it("closes an unterminated code fence", () => {
    expect(renderMicron("`=\nstill code")).toContain("still code");
    expect(renderMicron("`=\nstill code")).toContain("micron-code");
  });

  it("returns nothing for empty input", () => {
    expect(renderMicron("")).toBe("");
  });
});

describe("renderMicron escaping (XSS)", () => {
  it("escapes script tags", () => {
    const html = renderMicron('<script>alert("x")</script>');
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("escapes attribute-breaking payloads", () => {
    const payload = '"><img src=x onerror=alert(1)>';
    const html = renderMicron(payload);
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
    expect(html).toContain("&quot;");
  });

  it("escapes payloads inside headings and bullets", () => {
    expect(renderMicron("> <img src=x onerror=alert(1)>")).not.toContain("<img");
    expect(renderMicron("• <script>x</script>")).not.toContain("<script>");
  });
});

describe("renderMicron formatting", () => {
  it("renders bold, underline and italic toggles", () => {
    expect(renderMicron("`!bold`!")).toBe("<p><strong>bold</strong></p>");
    expect(renderMicron("`_under`_")).toBe("<p><u>under</u></p>");
    expect(renderMicron("`*italics`*")).toBe("<p><em>italics</em></p>");
  });

  it("combines toggles and resets with ``", () => {
    expect(renderMicron("`!`_both``")).toBe("<p><strong><u>both</u></strong></p>");
  });

  it("closes unclosed toggles at the end of the line", () => {
    expect(renderMicron("`!oops")).toBe("<p><strong>oops</strong></p>");
  });

  it("keeps escaped backticks as text", () => {
    expect(renderMicron("a \\` b")).toBe("<p>a ` b</p>");
  });
});

describe("renderMicron links", () => {
  const node = "a".repeat(32);

  it("renders node-qualified page links as reader links", () => {
    const html = renderMicron(`[Other\`${node}:/page/other.mu]`);
    expect(html).toContain('<a href="#" class="micron-link"');
    expect(html).toContain(`data-node="${node}"`);
    expect(html).toContain('data-path="/page/other.mu"');
    expect(html).toContain(">Other</a>");
    expect(html).not.toContain("#/browse/");
  });

  it("renders relative page links with an empty data-node", () => {
    const html = renderMicron("[Next`/page/two.mu]");
    expect(html).toContain('data-node=""');
    expect(html).toContain('data-path="/page/two.mu"');
  });

  it("renders external links in a new tab", () => {
    const html = renderMicron("[site`https://example.com/x]");
    expect(html).toContain('<a href="https://example.com/x"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain(">site</a>");
  });

  it("treats a bare URL in brackets as label and target", () => {
    const html = renderMicron("[https://example.com]");
    expect(html).toContain('href="https://example.com"');
    expect(html).toContain(">https://example.com</a>");
  });

  it("renders a bracket without a target as plain text", () => {
    expect(renderMicron("[just a label]")).toBe("<p>just a label</p>");
  });

  it("never emits a link for unsafe schemes", () => {
    const html = renderMicron("[click`javascript:alert(1)]");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("href=");
    expect(html).toContain("click");
  });

  it("refuses link targets containing spaces or quotes", () => {
    const html = renderMicron('[x`https://e.com/" onmouseover="alert(1)]');
    expect(html).not.toContain("onmouseover=");
    expect(html).not.toContain("href=");
    expect(html).toContain("x");
  });
});

describe("renderMicron tokens and literals", () => {
  it("renders inline literals as code", () => {
    expect(renderMicron("run `[npm test]` now")).toBe(
      '<p>run <code class="micron-inline-code">npm test</code> now</p>',
    );
  });

  it("escapes inline literal contents", () => {
    expect(renderMicron("`[<b>x</b>]`")).toContain("&lt;b&gt;x&lt;/b&gt;");
  });

  it("strips unknown backtick tokens instead of leaking them", () => {
    expect(renderMicron("`Xyzabc hello")).toBe("<p>hello</p>");
    expect(renderMicron("`qwerty hello")).toBe("<p>hello</p>");
    expect(renderMicron("colour `F123here`f ok")).toBe("<p>colour here ok</p>");
  });
});

describe("renderMicron size cap", () => {
  it("refuses pages over 512 KiB", () => {
    const html = renderMicron("x".repeat(MAX_RENDER_BYTES + 1));
    expect(html).toContain("too large to render");
    expect(html.length).toBeLessThan(200);
  });

  it("renders a page exactly at the limit", () => {
    const html = renderMicron("x".repeat(MAX_RENDER_BYTES));
    expect(html).not.toContain("too large");
  });
});
