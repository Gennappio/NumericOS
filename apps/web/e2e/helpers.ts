import { execFileSync } from "node:child_process"
import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test"
import { API_URL } from "./urls"

export interface ProjectRecord {
  id: string
  name: string
  version: number
}

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
): Promise<ProjectRecord> {
  const response = await request.post(`${API_URL}/v1/projects`, {
    data: { name: uniqueName("Project"), ...fields },
  })
  expect(response.status()).toBe(201)
  return (await response.json()) as ProjectRecord
}

export async function addCard(
  request: APIRequestContext,
  projectId: string,
  fields: Record<string, unknown>,
): Promise<CardRecord> {
  const response = await request.post(`${API_URL}/v1/projects/${projectId}/cards`, {
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
