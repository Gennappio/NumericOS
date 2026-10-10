import { ChevronDownIcon, ChevronUpIcon } from "lucide-react"
import type { Card, WorkflowStatus } from "@/api/client"
import { TypeBadge } from "@/components/TypeBadge"
import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { STATUS_LABELS } from "@/lib/labels"

/** Where a card should go: another column (appended), or another index in its column. */
export interface Placement {
  workflow_status?: WorkflowStatus
  position?: number
}

interface CardItemProps {
  card: Card
  /** Index of the card inside its column and the size of that column. */
  index: number
  count: number
  statuses: WorkflowStatus[]
  disabled: boolean
  onOpen: () => void
  onMove: (placement: Placement) => void
}

/**
 * One typed card. It shows the card's type and workflow status and nothing about validity:
 * a card in "Completed" is finished work, not a supported claim.
 */
export function CardItem({
  card,
  index,
  count,
  statuses,
  disabled,
  onOpen,
  onMove,
}: CardItemProps) {
  return (
    <article
      aria-label={card.title}
      className="space-y-2 rounded-md border border-border bg-card p-3 shadow-xs"
    >
      <TypeBadge type={card.type} />
      <button
        type="button"
        onClick={onOpen}
        className="block w-full rounded-sm text-left text-sm font-medium break-words hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        {card.title}
      </button>
      {card.description && (
        <p className="line-clamp-3 text-xs break-words whitespace-pre-line text-muted-foreground">
          {card.description}
        </p>
      )}
      <div className="flex items-center gap-1">
        <NativeSelect
          className="min-w-0 flex-1"
          aria-label={`Workflow status of ${card.title}`}
          value={card.workflow_status}
          disabled={disabled}
          onChange={(event) => onMove({ workflow_status: event.target.value as WorkflowStatus })}
        >
          {statuses.map((status) => (
            <NativeSelectOption key={status} value={status}>
              {STATUS_LABELS[status]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <Button
          variant="outline"
          size="icon"
          aria-label={`Move ${card.title} up`}
          disabled={disabled || index === 0}
          onClick={() => onMove({ position: index - 1 })}
        >
          <ChevronUpIcon />
        </Button>
        <Button
          variant="outline"
          size="icon"
          aria-label={`Move ${card.title} down`}
          disabled={disabled || index === count - 1}
          onClick={() => onMove({ position: index + 1 })}
        >
          <ChevronDownIcon />
        </Button>
      </div>
    </article>
  )
}
