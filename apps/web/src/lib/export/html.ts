/**
 * A document as one file that opens in any browser: its text, its styles, its fonts and its
 * images in the file itself, and no script.
 */

const ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }
const escaped = (text: string) => text.replace(/[&<>"]/g, (character) => ESCAPES[character])

interface PageParts {
  title: string
  /** The rules of the application's style sheets, and the fonts in use with their files. */
  css: string
  fonts: string
  /** The document, as the browser serialized it. */
  body: string
}

/** The whole file. Nothing in it points outside it, except links the document itself makes. */
export function standalonePage({ title, css, fonts, body }: PageParts): string {
  return [
    "<!doctype html>",
    '<html lang="en">',
    "<head>",
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<meta name="generator" content="NumericOS">',
    `<title>${escaped(title)}</title>`,
    // A closing tag inside a rule would end the element early; no rule of ours has one.
    `<style>${css.replace(/<\/style/gi, "<\\/style")}</style>`,
    `<style>${fonts}</style>`,
    "</head>",
    "<body>",
    body,
    "</body>",
    "</html>",
    "",
  ].join("\n")
}

/** A name for the file from what it holds: `heat-2d-pipeline.html`. */
export function fileName(project: string, what: string): string {
  const slug = (text: string) =>
    text
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
  return `${[slug(project), slug(what)].filter(Boolean).join("-") || "document"}.html`
}

/** Bytes as base64, a piece at a time: a figure can be larger than one call takes. */
function base64(bytes: Uint8Array): string {
  let binary = ""
  for (let at = 0; at < bytes.length; at += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(at, at + 0x8000))
  }
  return btoa(binary)
}

/** A file read as a `data:` address, or null if it cannot be read. */
export async function readAsDataUrl(url: string): Promise<string | null> {
  try {
    const response = await fetch(url)
    if (!response.ok) return null
    // The kind of file as its server names it, without what it adds after it.
    const type = (response.headers.get("Content-Type") ?? "").split(";")[0].trim()
    const bytes = new Uint8Array(await response.arrayBuffer())
    return `data:${type || "application/octet-stream"};base64,${base64(bytes)}`
  } catch {
    // Not reachable from here (another site that does not allow it, or no network).
    return null
  }
}

/**
 * Put every image of a rendered document into the document itself. An image that cannot be
 * read stays as it was: an address the reader's browser will try. Returns how many were left.
 */
export async function inlineImages(
  root: HTMLElement,
  read: (url: string) => Promise<string | null> = readAsDataUrl,
): Promise<number> {
  const images = [...root.querySelectorAll("img")].filter((image) => {
    const address = image.getAttribute("src") ?? ""
    return address !== "" && !address.startsWith("data:")
  })
  const contents = await Promise.all(images.map((image) => read(image.src)))
  let left = 0
  images.forEach((image, index) => {
    const data = contents[index]
    if (data) image.setAttribute("src", data)
    else left += 1
    // In a file nothing is fetched later: the image is there or it is not.
    image.removeAttribute("loading")
  })
  return left
}

/** Hand a text to the browser as a file to save. */
export function download(name: string, content: string, type = "text/html"): void {
  const address = URL.createObjectURL(new Blob([content], { type: `${type};charset=utf-8` }))
  const link = document.createElement("a")
  link.href = address
  link.download = name
  link.style.display = "none"
  document.body.append(link)
  link.click()
  link.remove()
  // The browser has taken the file by the time the click returns; the address is let go
  // a moment later for the ones that start the download asynchronously.
  setTimeout(() => URL.revokeObjectURL(address), 10_000)
}
