import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { ChevronDownIcon, ChevronUpIcon, GripVerticalIcon } from "lucide-react"
import type { Card, WorkflowStatus } from "@/api/client"
import { TypeBadge } from "@/components/TypeBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { CARD_TYPE_ACCENTS, STATUS_LABELS } from "@/lib/labels"
import { cn } from "@/lib/utils"

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
 * a card in "Completed" is finished work, not a supported claim. It is moved by dragging its
 * handle, or without a pointer by its status select and its up and down buttons.
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
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id: card.id, disabled })
  return (
    <article
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      aria-label={card.title}
      data-origin={card.origin}
      data-type={card.type}
      className={cn(
        "space-y-2 rounded-md border border-l-4 border-border p-3 shadow-xs",
        CARD_TYPE_ACCENTS[card.type],
        isDragging && "relative z-10 opacity-80 shadow-md",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-1.5">
          <TypeBadge type={card.type} />
          {card.origin === "agent" && (
            <Badge
              variant="outline"
              className="border-fuchsia-300 bg-fuchsia-100 text-fuchsia-900"
              title="Put on the board by the agent when it was asked to plan"
            >
              agent
            </Badge>
          )}
        </span>
        <button
          type="button"
          ref={setActivatorNodeRef}
          {...attributes}
          {...listeners}
          aria-label={`Drag ${card.title}`}
          disabled={disabled}
          className="cursor-grab touch-none rounded-sm p-0.5 text-muted-foreground hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none active:cursor-grabbing disabled:cursor-not-allowed disabled:opacity-50"
        >
          <GripVerticalIcon className="size-4" />
        </button>
      </div>
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
          className="min-w-0 flex-1 rounded-lg bg-white/70"
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
