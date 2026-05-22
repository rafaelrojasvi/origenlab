import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MailtoEmailLink, buildMailtoHref } from "./MailtoEmailLink";

describe("MailtoEmailLink", () => {
  it("builds email-only href without subject or body", () => {
    expect(buildMailtoHref("buyer@acme.cl")).toBe("mailto:buyer@acme.cl");
    expect(buildMailtoHref("buyer@acme.cl?subject=secret")).toBeNull();
    expect(buildMailtoHref("")).toBeNull();
  });

  it("renders anchor without query parameters", () => {
    render(<MailtoEmailLink email="ops@origenlab.cl" />);
    const link = screen.getByRole("link", { name: "mailto" });
    expect(link.getAttribute("href")).toBe("mailto:ops@origenlab.cl");
    expect(link.getAttribute("href")).not.toMatch(/subject=|body=/i);
  });
});
