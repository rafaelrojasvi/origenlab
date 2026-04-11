#!/usr/bin/env node
/**
 * Export OrigenLab catalog HTML to PDF via Playwright (Chromium).
 *
 * Usage (from this directory, where HTML + catalog_assets_premium/ live):
 *   node export-catalog-pdf.mjs [input.html] [output.pdf] [multipage|continuous]
 *
 * Defaults:
 *   input:  catalog-pdf.html  (PDF-first layout; web = OrigenLab_*_Premium.html)
 *   output: catalog-multipage.pdf
 *   mode:   multipage  ← official A4 client deliverable (print CSS)
 *
 * See CATALOG_DELIVERY.md for when to send PDF vs share the HTML link.
 */

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".htm": "text/html; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".css": "text/css",
  ".js": "application/javascript",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".json": "application/json",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function safeJoin(root, urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const rel = decoded.replace(/^\/+/, "");
  const candidate = path.normalize(path.join(root, rel));
  const rootResolved = path.resolve(root);
  if (!candidate.startsWith(rootResolved)) {
    return null;
  }
  return candidate;
}

function startStaticServer(rootDir, port) {
  const server = http.createServer((req, res) => {
    let pathname = req.url ?? "/";
    if (pathname === "/" || pathname === "") {
      res.statusCode = 404;
      res.end("Specify the HTML file in the URL path, e.g. /OrigenLab_....html");
      return;
    }
    const filePath = safeJoin(rootDir, pathname);
    if (!filePath) {
      res.statusCode = 403;
      res.end("Forbidden");
      return;
    }
    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.statusCode = 404;
        res.end("Not found");
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      res.setHeader("Content-Type", MIME[ext] ?? "application/octet-stream");
      res.end(data);
    });
  });
  return new Promise((resolve, reject) => {
    server.listen(port, "127.0.0.1", () => resolve(server));
    server.on("error", reject);
  });
}

/** Screen-mode tweaks for single-scroll PDF (internal / optional; multipage is the official client PDF). */
const CONTINUOUS_SCREEN_INJECT = `
<style id="origenlab-playwright-pdf-continuous">
  body { padding: 0 !important; }
  html { background: var(--bg, #f4efe7); }
  .catalog-nav { display: none !important; }
</style>
`;

async function waitForImages(page) {
  await page.evaluate(() =>
    Promise.all(
      Array.from(document.images)
        .filter((img) => !img.complete)
        .map(
          (img) =>
            new Promise((resolve) => {
              img.addEventListener("load", resolve, { once: true });
              img.addEventListener("error", resolve, { once: true });
            }),
        ),
    ),
  );
}

async function main() {
  const inputName =
    process.argv[2] ?? "catalog-pdf.html";
  const outputName = process.argv[3] ?? "catalog-multipage.pdf";
  const mode = (process.argv[4] ?? "multipage").toLowerCase();

  if (mode !== "multipage" && mode !== "continuous") {
    console.error('Mode must be "multipage" or "continuous".');
    process.exit(1);
  }

  let htmlPath;
  if (path.isAbsolute(inputName)) {
    htmlPath = inputName;
  } else {
    const fromCwd = path.resolve(process.cwd(), inputName);
    const fromScript = path.resolve(__dirname, inputName);
    if (fs.existsSync(fromCwd)) {
      htmlPath = fromCwd;
    } else if (fs.existsSync(fromScript)) {
      htmlPath = fromScript;
    } else {
      htmlPath = fromCwd;
    }
  }
  if (!fs.existsSync(htmlPath)) {
    console.error("HTML not found:", htmlPath);
    console.error("(Tried cwd and the folder containing export-catalog-pdf.mjs.)");
    process.exit(1);
  }

  const rootDir = path.dirname(htmlPath);
  const htmlBase = path.basename(htmlPath);
  const outPath = path.isAbsolute(outputName)
    ? outputName
    : path.resolve(process.cwd(), outputName);

  const port = 8765 + Math.floor(Math.random() * 2000);
  const server = await startStaticServer(rootDir, port);
  const url = `http://127.0.0.1:${port}/${encodeURIComponent(htmlBase)}`;

  const browser = await chromium.launch({ headless: true });
  const page =
    mode === "continuous"
      ? await browser.newPage({ viewport: { width: 1200, height: 900 } })
      : await browser.newPage();

  try {
    await page.goto(url, { waitUntil: "networkidle", timeout: 120_000 });
    await waitForImages(page);

    if (mode === "multipage") {
      await page.pdf({
        path: outPath,
        format: "A4",
        printBackground: true,
        preferCSSPageSize: true,
        margin: { top: "0", right: "0", bottom: "0", left: "0" },
      });
    } else {
      await page.emulateMedia({ media: "screen" });
      await page.addStyleTag({ content: CONTINUOUS_SCREEN_INJECT });
      const { width, height } = await page.evaluate(() => {
        const el = document.documentElement;
        const b = document.body;
        return {
          width: Math.ceil(
            Math.max(el.scrollWidth, b.scrollWidth, el.offsetWidth, b.offsetWidth),
          ),
          height: Math.ceil(
            Math.max(el.scrollHeight, b.scrollHeight, el.offsetHeight, b.offsetHeight),
          ),
        };
      });
      await page.pdf({
        path: outPath,
        width: `${width}px`,
        height: `${height}px`,
        printBackground: true,
        margin: { top: "0", right: "0", bottom: "0", left: "0" },
      });
    }

    console.log("Wrote:", outPath);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
