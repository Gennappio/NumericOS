import { CheckIcon, CircleDashedIcon, XIcon } from "lucide-react"
import type { ActivityItem } from "@/api/client"
import { cn } from "@/lib/utils"

/**
 * What the agent did, in order: the text it wrote between actions and every tool it used,
 * with whether the tool succeeded. Compact lines, never the tool's whole input or output.
 */
export function ActivityList({ items, dropped }: { items: ActivityItem[]; dropped: number }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing recorded yet.</p>
  }
  return (
    <div className="space-y-1">
      <ol className="space-y-1 text-sm" aria-label="Actions of the agent">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2">
            {item.kind === "tool" && item.tool ? (
              <>
                <ToolMark ok={item.tool.ok ?? null} />
                <span className="min-w-0">
                  <span className="font-medium">{item.tool.name}</span>{" "}
                  <span className="font-mono text-xs break-all text-muted-foreground">
                    {item.tool.summary}
                  </span>
                </span>
              </>
            ) : (
              <>
                <span aria-hidden="true" className="w-4 shrink-0 text-center text-muted-foreground">
                  ·
                </span>
                <span className="min-w-0 text-muted-foreground" title={item.text ?? undefined}>
                  {firstLine(item.text ?? "")}
                </span>
              </>
            )}
          </li>
        ))}
      </ol>
      {dropped > 0 && (
        <p className="text-xs text-muted-foreground">
          {dropped} more actions are kept only in the file of the turn.
        </p>
      )}
    </div>
  )
}

function ToolMark({ ok }: { ok: boolean | null }) {
  const label = ok === null ? "in progress" : ok ? "succeeded" : "failed"
  const Icon = ok === null ? CircleDashedIcon : ok ? CheckIcon : XIcon
  return (
    <span
      role="img"
      aria-label={`Tool ${label}`}
      className={cn(
        "mt-0.5 flex size-4 shrink-0 items-center justify-center",
        ok === null ? "text-muted-foreground" : ok ? "text-sky-700" : "text-red-700",
      )}
    >
      <Icon className="size-3.5" />
    </span>
  )
}

function firstLine(text: string): string {
  const line = text.split("\n").find((part) => part.trim()) ?? ""
  return line.length > 200 ? `${line.slice(0, 199)}…` : line
}
