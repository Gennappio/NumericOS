import { mkdtempSync, readFileSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { expect, test, type Page } from "@playwright/test"
import { trustedExampleProject } from "./helpers"

/**
 * A document handed over as one HTML file, end to end: the file is downloaded from the page,
 * read, and opened on its own, away from the application and its servers. What must hold is
 * that it shows the same thing and needs nothing that is not in it.
 */

const SOLVER = "examples/heat2d-python/heat2d.py"

/** Press the button, keep the file under its own name, and return where it is and its text. */
async function downloadFrom(page: Page): Promise<{ path: string; name: string; html: string }> {
  const downloading = page.waitForEvent("download")
  await page.getByRole("button", { name: "Download as HTML" }).click()
  const download = await downloading
  const name = download.suggestedFilename()
  const path = join(mkdtempSync(join(tmpdir(), "numericos-e2e-share-")), name)
  await download.saveAs(path)
  return { path, name, html: readFileSync(path, "utf8") }
}

/** Open a file by itself and note every address its page asks for beyond itself. */
async function openAlone(page: Page, path: string): Promise<{ shared: Page; asked: string[] }> {
  const shared = await page.context().newPage()
  const asked: string[] = []
  shared.on("request", (request) => {
    const address = request.url()
    if (!address.startsWith("file:") && !address.startsWith("data:")) asked.push(address)
  })
  await shared.goto(`file://${path}`)
  return { shared, asked }
}

/**
 * What in a file matches a pattern, each match cut short: a file is hundreds of kilobytes,
 * and a failed check must say what it found, not print the file.
 */
function found(html: string, pattern: RegExp): string[] {
  const global = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`)
  return [...html.matchAll(global)].map((match) => match[0].slice(0, 120))
}

/** What a file that stands on its own never has: a script, or an address outside itself. */
function expectSelfContained(html: string) {
  expect(html.startsWith("<!doctype html>")).toBe(true)
  expect(found(html, /<script/i)).toEqual([])
  // Every file a rule names is in the rule, and every image is in the page.
  expect(found(html, /url\(\s*["']?(?!data:|#)[^)]{0,100}/)).toEqual([])
  expect(found(html, /\b(src|href)="(?!data:|#)[^"]{0,100}/)).toEqual([])
  expect(found(html, /127\.0\.0\.1.{0,60}/)).toEqual([])
}

test("the pipeline is shared as one file that shows the board without the application", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}/pipeline`)
  await page.getByRole("button", { name: "Draw the pipeline" }).click()
  const board = page.getByRole("application", { name: "Pipeline board" })
  await expect(board.getByRole("article")).toHaveCount(4)

  // The researcher puts a box somewhere else: the file shows the board as it was left.
  const grip = await board.getByRole("article", { name: "Build the grid" }).locator("header").boundingBox()
  const from = { x: Math.round(grip!.x + 40), y: Math.round(grip!.y + grip!.height / 2) }
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(from.x - 30, from.y + 260, { steps: 10 })
  await page.mouse.up()

  const file = await downloadFrom(page)
  expect(file.name).toBe(`${project.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-pipeline.html`)
  expectSelfContained(file.html)
  // The fonts the page used travel in the file: the text's and the formulas'.
  const fonts = [
    ...file.html.matchAll(/@font-face \{ font-family: "([^"]+)";[^}]*?src: url\((data:[a-z0-9/-]+)/g),
  ]
    .map((rule) => `${rule[1]} ${rule[2]}`)
    .sort()
  // Only what the page used: the text's font and the two the formulas needed.
  expect(fonts).toEqual([
    "Geist Variable data:font/woff2",
    "KaTeX_Main data:font/woff2",
    "KaTeX_Math data:font/woff2",
  ])
  expect(file.html.length).toBeLessThan(700_000)
  // Nothing stays behind on the page it was made from.
  await expect(page.locator("body > div[aria-hidden=true]")).toHaveCount(0)

  const { shared, asked } = await openAlone(page, file.path)
  await expect(shared).toHaveTitle("Pipeline of the 2D heat solver")
  await expect(
    shared.getByRole("heading", { level: 1, name: "Pipeline of the 2D heat solver" }),
  ).toBeVisible()
  await expect(shared.getByText(`${project.name} · Pipeline`)).toBeVisible()
  await expect(shared.getByText(/One run reads its parameters, builds the grid/)).toBeVisible()
  // Every box with its kind, its text, its formula and its files; nothing to drag.
  const boxes = shared.locator(".export-board article")
  await expect(boxes).toHaveCount(4)
  const loop = shared.getByRole("article", { name: "Advance in time" })
  await expect(loop).toContainText("The explicit scheme updates every interior point")
  await expect(loop.locator(".katex-display")).toBeVisible()
  await expect(loop.getByText("every time step, until the final time")).toBeVisible()
  await expect(loop.getByRole("list", { name: "Files of Advance in time" })).toHaveText("heat2d.py")
  await expect(loop.locator("header")).not.toHaveAttribute("title", /Drag/)
  await expect(shared.locator("[data-leaf]")).toHaveCount(0) // no marks for commenting
  // The arrows are drawn, with what passes, and said in words.
  await expect(shared.locator(".export-board svg path[marker-end]")).toHaveCount(3)
  await expect(shared.locator(".export-board .pipeline-arrow-label")).toHaveText([
    "n, alpha, dt",
    "initial field",
    "final field",
  ])
  await expect(shared.getByRole("list", { name: "Arrows of the pipeline" }).getByRole("listitem")).toHaveCount(3)

  // The boxes stand where they stood: in a row, but for the one that was dragged down.
  const place = async (title: string) => (await shared.getByRole("article", { name: title }).boundingBox())!
  const [first, second, third, fourth] = await Promise.all(
    ["Read the parameters", "Build the grid", "Advance in time", "Write the results"].map(place),
  )
  expect(first.x).toBeLessThan(second.x)
  expect(second.x).toBeLessThan(third.x)
  expect(second.x - (first.x + first.width)).toBeGreaterThan(100) // room for the arrow
  expect(third.x).toBeLessThan(fourth.x)
  expect(second.y).toBeGreaterThan(first.y + 150) // moved down, not back in the row
  expect(Math.abs(third.y + third.height / 2 - (first.y + first.height / 2))).toBeLessThan(2)
  // An arrow ends at the left edge of the box it points to, at mid height.
  const tip = await shared.locator(".export-board svg path[marker-end]").first().evaluate((path) => {
    const line = path as SVGPathElement
    const end = line.getPointAtLength(line.getTotalLength())
    const origin = line.ownerSVGElement!.getBoundingClientRect()
    return { x: origin.x + end.x, y: origin.y + end.y }
  })
  expect(Math.abs(tip.x - second.x)).toBeLessThan(2)
  expect(Math.abs(tip.y - (second.y + second.height / 2))).toBeLessThan(2)

  // It looks as in the application because it carries the same fonts, and asks for nothing.
  expect(await shared.evaluate(() => document.fonts.check('16px "KaTeX_Main"'))).toBe(true)
  expect(await shared.evaluate(() => document.fonts.check('16px "Geist Variable"'))).toBe(true)
  expect(asked).toEqual([])
  await shared.screenshot({ path: "test-results/screens/share-pipeline.png", fullPage: true })

  // On paper the board would be cut: a printed copy lists the parts in the order of a run.
  await shared.emulateMedia({ media: "print" })
  await expect(shared.locator(".export-board")).toBeHidden()
  const parts = shared.getByRole("list", { name: "The parts, in the order of a run" })
  await expect(parts.getByRole("heading", { level: 2 })).toHaveText([
    "Read the parameters",
    "Build the grid",
    "Advance in time",
    "Write the results",
  ])
  await expect(parts.getByText(`Stage · repeats: every time step, until the final time`)).toBeVisible()
  await shared.screenshot({ path: "test-results/screens/share-pipeline-print.png", fullPage: true })
})

test("the theory is shared as one file with its formulas and its figures inside", async ({
  page,
  request,
}) => {
  const project = await trustedExampleProject(request)
  await page.goto(`/projects/${project.id}/theory`)
  await page.getByLabel("Instructions for the agent").fill(`READ ${SOLVER}`)
  await page.getByRole("button", { name: "Write the theory" }).click()
  await expect(
    page.getByRole("article", { name: "Explicit scheme for the 2D heat equation" }),
  ).toBeVisible()

  const file = await downloadFrom(page)
  expect(file.name).toMatch(/-theory\.html$/)
  expectSelfContained(file.html)
  // The figure of the repository is in the file, not an address of the application.
  expect(found(file.html, /<img [^>]*?src="[^"]{0,30}/)).toEqual([
    '<img alt="The grid of the solver" src="data:image/png;base64,iVBORw0K',
  ])

  const { shared, asked } = await openAlone(page, file.path)
  await expect(shared).toHaveTitle("Explicit scheme for the 2D heat equation")
  await expect(
    shared.getByRole("heading", { level: 1, name: "Explicit scheme for the 2D heat equation" }),
  ).toBeVisible()
  await expect(shared.locator(".paper .katex-display")).toBeVisible()
  await expect(shared.getByRole("table")).toContainText("update of (1)")
  const figure = shared.getByRole("img", { name: "The grid of the solver" })
  await expect(figure).toBeVisible()
  expect(await figure.evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBe(16)
  await expect(shared.getByText("The grid of the solver", { exact: true })).toBeVisible() // its caption
  // Where it comes from is said under it.
  await expect(shared.getByText(/Version 1 · written by .* from 1 file of the project/)).toBeVisible()
  await expect(shared.getByText(/exported from NumericOS on/)).toBeVisible()
  expect(asked).toEqual([])
  await shared.screenshot({ path: "test-results/screens/share-theory.png", fullPage: true })

  // The code changes after the theory was written: a copy made then says so to its reader.
  writeFileSync(join(project.root_path!, SOLVER), "print('implicit now')\n")
  await page.reload()
  await expect(page.getByRole("alert")).toContainText("has changed since")
  const later = await downloadFrom(page)
  const again = await openAlone(page, later.path)
  const warning = again.shared.locator("p").filter({ hasText: "has changed since" })
  await expect(warning).toContainText(`A file this was written from has changed since: ${SOLVER}.`)
  await expect(warning).toContainText("What follows describes the project as it was.")
})
