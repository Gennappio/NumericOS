import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Markdown } from "./Markdown"

describe("Markdown", () => {
  it("renders headings, lists, tables and code", () => {
    const { container } = render(
      <Markdown
        source={"## Scheme\n\n- explicit\n- implicit\n\n| dt | stable |\n| --- | --- |\n| 1e-4 | yes |\n\n`u_t`"}
      />,
    )

    expect(screen.getByRole("heading", { level: 2, name: "Scheme" })).toBeVisible()
    expect(screen.getAllByRole("listitem")).toHaveLength(2)
    expect(screen.getByRole("table")).toBeVisible()
    expect(container.querySelector("code")?.textContent).toBe("u_t")
  })

  it("renders mathematics with KaTeX, inline and displayed", () => {
    const { container } = render(
      <Markdown source={"Stable when $\\alpha \\Delta t / \\Delta x^2 \\le 1/2$:\n\n$$u_t = \\alpha \\nabla^2 u$$"} />,
    )

    expect(container.querySelectorAll(".katex")).toHaveLength(2)
    expect(container.querySelector(".katex-display")).not.toBeNull()
    // The source of a formula stays available to assistive technology and to selection.
    expect(container.querySelector("annotation")?.textContent).toContain("\\Delta t")
  })

  it("does not render raw HTML written by the agent", () => {
    const { container } = render(
      <Markdown source={'Text <script>alert(1)</script> <img src=x onerror="alert(1)"> end'} />,
    )

    expect(container.querySelector("script")).toBeNull()
    expect(container.querySelector("img")).toBeNull()
    expect(container.textContent).toContain("Text")
  })

  it("keeps only safe link protocols", () => {
    const { container } = render(
      <Markdown source={"[docs](https://example.org) [bad](javascript:alert(1))"} />,
    )

    const links = container.querySelectorAll("a")
    expect(links[0].getAttribute("href")).toBe("https://example.org")
    expect(links[1].getAttribute("href")).not.toContain("javascript:")
  })
})
