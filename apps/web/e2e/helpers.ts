import { execFileSync } from "node:child_process"
import { cpSync, mkdirSync, mkdtempSync, realpathSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test"
import { API_URL } from "./urls"

export interface ProjectRecord {
  id: string
  name: string
  version: number
  root_path: string | null
}

/** A 16 by 16 grey square: a real image for the pages that show the figures of a project. */
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR4nGNsaGhgIAUwkaR6VMPQ0QAAVW4BoCQvvEYAAAAASUVORK5CYII=",
  "base64",
)

export interface CardRecord {
  id: string
  title: string
  version: number
  workflow_status: string
}

/** Create a project through the real API (never through mocked fetch). */
export async function createProject(
  request: APIRequestContext,
  fields: Record<string, unknown> = {},
  apiUrl: string = API_URL,
): Promise<ProjectRecord> {
  const response = await request.post(`${apiUrl}/v1/projects`, {
    data: { name: uniqueName("Project"), ...fields },
  })
  expect(response.status()).toBe(201)
  return (await response.json()) as ProjectRecord
}

export async function addCard(
  request: APIRequestContext,
  projectId: string,
  fields: Record<string, unknown>,
  apiUrl: string = API_URL,
): Promise<CardRecord> {
  const response = await request.post(`${apiUrl}/v1/projects/${projectId}/cards`, {
    data: { type: "task", ...fields },
  })
  expect(response.status()).toBe(201)
  return (await response.json()) as CardRecord
}

export function uniqueName(prefix: string): string {
  return `${prefix} ${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function column(page: Page, name: string): Locator {
  return page.getByRole("region", { name: `${name} column` })
}

/** Titles of the cards in a column, top to bottom. */
export async function cardTitles(columnLocator: Locator): Promise<(string | null)[]> {
  return columnLocator
    .getByRole("article")
    .evaluateAll((cards) => cards.map((card) => card.getAttribute("aria-label")))
}

/** Run the real `numericos` CLI against the API under test and parse its JSON output. */
export function cli<T>(...args: string[]): T {
  const stdout = execFileSync("uv", ["run", "numericos", ...args, "--json", "--api-url", API_URL], {
    cwd: "../..",
    env: { ...process.env, UV_PROJECT_ENVIRONMENT: ".venv" },
    encoding: "utf8",
  })
  return JSON.parse(stdout) as T
}

/**
 * A Git repository holding this repository's examples at the path they have here: the code
 * of a research project, as far as an experiment is concerned.
 */
export function exampleRepository(): string {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "numericos-e2e-repo-")))
  cpSync("../../examples", join(root, "examples"), { recursive: true })
  mkdirSync(join(root, "docs"))
  writeFileSync(join(root, "docs", "grid.png"), PNG)
  const git = (...args: string[]) =>
    execFileSync("git", ["-C", root, ...args], {
      env: { ...process.env, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_SYSTEM: "/dev/null" },
    })
  git("init", "-q", "-b", "main")
  git("add", "-A")
  git("-c", "user.name=Ada Lovelace", "-c", "user.email=ada@example.invalid", "commit", "-q", "-m", "examples")
  return root
}

/** A project whose code path is a repository with the examples, allowed to execute. */
export async function trustedExampleProject(request: APIRequestContext): Promise<ProjectRecord> {
  const root = exampleRepository()
  const project = await createProject(request, { root_path: root })
  const response = await request.post(`${API_URL}/v1/projects/${project.id}:trust-execution`, {
    data: { version: project.version, root_path: root },
  })
  expect(response.status()).toBe(200)
  return (await response.json()) as ProjectRecord
}

/**
 * Start a conversation the way a person does: with the + next to the project's name in the
 * sidebar. The page of the project then shows the new, empty conversation.
 */
export async function startConversation(page: Page, project: ProjectRecord): Promise<void> {
  await page.goto(`/projects/${project.id}`)
  await page
    .getByRole("navigation", { name: "Projects" })
    .getByRole("button", { name: `New conversation in ${project.name}` })
    .click()
  await expect(page.getByRole("heading", { name: "New conversation" })).toBeVisible()
}

export interface RunRecord {
  id: string
  status: string
}

/** Register a contract file of the project and queue one run of it, through the real API. */
export async function queueRun(
  request: APIRequestContext,
  projectId: string,
  contract: string,
  parameters: Record<string, unknown>,
): Promise<RunRecord> {
  const registered = await request.post(`${API_URL}/v1/projects/${projectId}/experiments:import`, {
    data: { path: contract },
  })
  expect([200, 201]).toContain(registered.status())
  const experiment = (await registered.json()) as { id: string }
  const queued = await request.post(`${API_URL}/v1/experiments/${experiment.id}/runs`, {
    data: { parameters },
  })
  expect(queued.status()).toBe(201)
  return (await queued.json()) as RunRecord
}

/**
 * Select a passage of a commentable text as a person would with the pointer: the selection
 * is made on the text as shown, and the release of the button is what the page listens to.
 */
export async function selectPassage(text: Locator, passage: string): Promise<void> {
  await text.evaluate((root, wanted) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const at = node.textContent!.indexOf(wanted)
      if (at < 0) continue
      const range = document.createRange()
      range.setStart(node, at)
      range.setEnd(node, at + wanted.length)
      const selection = window.getSelection()!
      selection.removeAllRanges()
      selection.addRange(range)
      root.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }))
      return
    }
    throw new Error(`passage not found on the page: ${wanted}`)
  }, passage)
}
