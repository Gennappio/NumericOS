import { DownloadIcon } from "lucide-react"
import { useState } from "react"
import type { SharedFile } from "@/components/export/exportDocument"
import { Button } from "@/components/ui/button"
import { download } from "@/lib/export/html"
import { cn } from "@/lib/utils"

interface ShareButtonProps {
  /** Makes the file from the document as it is now; called at every press. */
  build: () => Promise<SharedFile>
  onNotice: (message: string) => void
  onError: (error: unknown) => void
  className?: string
}

/**
 * Hands a document over as one HTML file: it opens in any browser without NumericOS, can be
 * sent as it is, and printed from there to get a PDF.
 */
export function ShareButton({ build, onNotice, onError, className }: ShareButtonProps) {
  const [pending, setPending] = useState(false)

  async function share() {
    setPending(true)
    try {
      const file = await build()
      download(file.name, file.html)
      if (file.imagesLeftOutside > 0) {
        onNotice(
          `${file.imagesLeftOutside} image(s) could not be put into the file: whoever opens it ` +
            "needs to reach their address to see them.",
        )
      }
    } catch (error) {
      onError(error)
    } finally {
      setPending(false)
    }
  }

  return (
    <Button
      size="sm"
      variant="outline"
      className={cn("bg-background", className)}
      disabled={pending}
      title="One file that opens in any browser: send it as it is, or print it to get a PDF"
      onClick={() => void share()}
    >
      <DownloadIcon data-icon="inline-start" />
      {pending ? "Preparing…" : "Download as HTML"}
    </Button>
  )
}
