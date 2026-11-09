import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ControlDetailView } from "@/components/ControlDetailView";

import { control } from "./fixtures";

describe("ControlDetailView", () => {
  it("renders content, parameters, properties, references and source identity", () => {
    render(<ControlDetailView control={control()} />);
    expect(screen.getByText(/Nested item/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Parameters" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Properties" })).toBeInTheDocument();
    expect(screen.getByText("Policy template")).toBeInTheDocument();
    expect(screen.getByText(/Source:/)).toHaveTextContent("revision 1");
    expect(screen.getByText("ac-1", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText(/Add to Profile — coming later/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add to profile/i })).toBeNull();
  });

  it("renders untrusted markup and unsafe links inertly", () => {
    const hostile = control({
      title: "<img src=x onerror=alert(1)>",
      parts: [
        {
          name: "statement",
          prose: '<script>window.__pwned = true</script><b>bold</b> [x](javascript:alert(1))',
          props: [],
          links: [{ href: "javascript:alert(1)", text: "click me" }],
          parts: [],
        },
      ],
      references: [
        { uuid: "r", title: "<i>ref</i>", description: "<u>d</u>", citation: null, rlinks: [{ href: "data:text/html,<script>1</script>" }] },
      ],
      links: [{ href: "https://example.com", text: "ok" }],
    });
    const { container } = render(<ControlDetailView control={hostile} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("u")).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
    expect(screen.getByText(/<b>bold<\/b>/)).toBeInTheDocument();
    for (const anchor of container.querySelectorAll("a")) {
      expect(anchor.getAttribute("href")).toMatch(/^https?:/);
      expect(anchor.getAttribute("rel")).toContain("noopener");
    }
    expect(screen.queryByRole("link", { name: /click me/ })).toBeNull();
    expect(screen.getAllByText(/link disabled/).length).toBeGreaterThan(0);
  });

  it("copes with optional/missing OSCAL elements", () => {
    render(
      <ControlDetailView
        control={control({ parts: [], parameters: [], properties: [], links: [], references: [], ancestors: [], group: null })}
      />,
    );
    expect(screen.queryByRole("heading", { name: "Parameters" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Source identity" })).toBeInTheDocument();
  });
});
