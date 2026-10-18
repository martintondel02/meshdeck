// Unit tests for the micron renderer. The renderer feeds {@html} in the Pages
// reader, so the escaping tests here are security tests, not cosmetics.
import { describe, expect, it } from "vitest";
import { renderMicron } from "./micron";

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
