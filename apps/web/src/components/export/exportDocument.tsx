import type { ReactNode } from "react"
import { flushSync } from "react-dom"
import { createRoot } from "react-dom/client"
import { fileContentUrl, type DocumentOut, type Pipeline, type Project } from "@/api/client"
import { ExportPipeline } from "@/components/export/ExportPipeline"
import { ExportShell } from "@/components/export/ExportShell"
import { ExportTheory } from "@/components/export/ExportTheory"
import { layoutPipeline, type Sized } from "@/components/pipeline/layout"
import { readPositions } from "@/components/pipeline/positions"
import { drawBoard } from "@/lib/export/board"
import { embeddedFonts, loadedFaces, pageStyles } from "@/lib/export/css"
import { fileName, inlineImages, readAsDataUrl, standalonePage } from "@/lib/export/html"

/** A document ready to be handed over: the whole file, and a name for it. */
export interface SharedFile {
  name: string
  html: string
  /** Images that could not be put into the file and are still fetched from where they were. */
  imagesLeftOutside: number
}

type Render = (node: ReactNode) => void

/**
 * Render something where the reader does not see it but the browser lays it out: the
 * application's styles apply to it and it can be measured. What is rendered there is then
 * read back as markup; nothing of it stays on the page.
 */
async function offscreen<T>(work: (host: HTMLElement, render: Render) => Promise<T>): Promise<T> {
  const host = document.createElement("div")
  host.setAttribute("aria-hidden", "true")
  host.style.cssText =
    "position:fixed;left:-100000px;top:0;width:1200px;visibility:hidden;pointer-events:none"
  document.body.append(host)
  const root = createRoot(host)
  try {
    return await work(host, (node) => flushSync(() => root.render(node)))
  } finally {
    root.unmount()
    host.remove()
  }
}

/** Until the fonts the new content asked for are in, and the browser has laid it out. */
async function settled(): Promise<void> {
  await document.fonts?.ready
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
}

/** What was rendered in `host`, as a file that stands on its own. */
async function fileOf(host: HTMLElement, title: string, name: string): Promise<SharedFile> {
  await settled()
  const imagesLeftOutside = await inlineImages(host)
  const styles = pageStyles()
  const fonts = await embeddedFonts(styles.faces, loadedFaces(), readAsDataUrl)
  return {
    name,
    html: standalonePage({ title, css: styles.css, fonts, body: host.innerHTML }),
    imagesLeftOutside,
  }
}

/** The theory of a project as one file: the paper, its formulas, its figures. */
export function shareTheory(project: Project, document: DocumentOut): Promise<SharedFile> {
  const resolveImage = (path: string) => fileContentUrl(project.id, path)
  const title = document.title || `Theory of ${project.name}`
  return offscreen(async (host, render) => {
    render(
      <ExportShell
        project={project.name}
        what="Theory"
        document={document}
        exportedAt={new Date().toISOString()}
      >
        <ExportTheory markdown={document.markdown} resolveImage={resolveImage} />
      </ExportShell>,
    )
    return fileOf(host, title, fileName(project.name, "theory"))
  })
}

/**
 * The pipeline of a project as one file: the board with its boxes where the researcher put
 * them (or where the order of a run puts them), the arrows, and the same in words. The boxes
 * are rendered once to be measured, then placed: the page in the file is still.
 */
export function sharePipeline(
  project: Project,
  document: DocumentOut,
  pipeline: Pipeline,
): Promise<SharedFile> {
  const resolveImage = (path: string) => fileContentUrl(project.id, path)
  const title = document.title || `Pipeline of ${project.name}`
  const page = (board: Parameters<typeof ExportPipeline>[0]["board"]) => (
    <ExportShell
      project={project.name}
      what="Pipeline"
      document={document}
      exportedAt={new Date().toISOString()}
      wide
    >
      <ExportPipeline
        document={document}
        pipeline={pipeline}
        resolveImage={resolveImage}
        board={board}
      />
    </ExportShell>
  )
  return offscreen(async (host, render) => {
    render(page(null))
    await settled()
    const drawn = new Map(
      [...host.querySelectorAll<HTMLElement>("article[data-node]")].map((box) => [
        box.dataset.node,
        box,
      ]),
    )
    const sizes: Sized[] = pipeline.nodes.map((node) => ({
      id: node.id,
      width: drawn.get(node.id)?.offsetWidth ?? 0,
      height: drawn.get(node.id)?.offsetHeight ?? 0,
    }))
    const ids = pipeline.nodes.map((node) => node.id)
    const positions =
      readPositions(document.id, document.version, ids) ?? layoutPipeline(sizes, pipeline.edges)
    render(page(drawBoard(sizes, positions, pipeline.edges)))
    return fileOf(host, title, fileName(project.name, "pipeline"))
  })
}
