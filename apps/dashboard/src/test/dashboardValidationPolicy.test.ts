import { describe, expect, it } from "vitest";

const packageJson = JSON.parse(
  import.meta.glob("../../package.json", {
    query: "?raw",
    import: "default",
    eager: true,
  })["../../package.json"] as string,
) as { scripts?: Record<string, string> };

const readme = import.meta.glob("../../README.md", {
  query: "?raw",
  import: "default",
  eager: true,
})["../../README.md"] as string;

describe("dashboard validate script policy", () => {
  it("package.json defines validate as tests then build", () => {
    expect(packageJson.scripts?.validate).toBe("npm test && npm run build");
  });

  it("README documents npm run validate for dashboard PRs", () => {
    expect(readme).toMatch(/npm run validate/);
    expect(readme.toLowerCase()).toMatch(/before opening or merging dashboard prs|before.*dashboard prs/i);
  });
});
