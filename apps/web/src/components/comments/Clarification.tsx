import type { Annotation } from "@/api/client"
import { Markdown } from "@/components/markdown/Markdown"
import { excerpt } from "@/lib/comments"

/** What the agent answered about a passage, right after the paragraph the passage is in. */
export function Clarification({ item, onFocus }: { item: Annotation; onFocus: () => void }) {
  return (
    <aside className="clarification" aria-label={`Clarification of: ${excerpt(item.quote, 60)}`}>
      <details open>
        <summary className="cursor-pointer text-xs font-medium text-sky-900" onClick={onFocus}>
          Clarification <span className="font-normal text-sky-900/80">· {item.body}</span>
        </summary>
        <div className="mt-1.5">
          <Markdown source={item.response_markdown ?? ""} />
        </div>
      </details>
    </aside>
  )
}
