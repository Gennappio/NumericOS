import {
  closestCorners,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core"
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { PlusIcon } from "lucide-react"
import { useState, type ReactNode } from "react"
import type { Board as BoardData, Card, WorkflowStatus } from "@/api/client"
import { useUpdateCard } from "@/api/queries"
import { CardDialog, type CardDialogTarget } from "@/components/board/CardDialog"
import { CardItem, type Placement } from "@/components/board/CardItem"
import { Button } from "@/components/ui/button"
import { COLUMN_PREFIX, placementOfDrop } from "@/lib/boardDrop"
import { STATUS_LABELS } from "@/lib/labels"
import { cn } from "@/lib/utils"

interface BoardProps {
  projectId: string
  board: BoardData
  /** True while the backend is unreachable: the board stays readable, changes are off. */
  disabled: boolean
  onError: (error: unknown) => void
}

/** The scientific board: one column per workflow status, cards in the order the backend stores. */
export function Board({ projectId, board, disabled, onError }: BoardProps) {
  const updateCard = useUpdateCard(projectId)
  // The target is kept after closing so the dialog can finish its exit animation with content.
  const [target, setTarget] = useState<CardDialogTarget>({ mode: "create", status: "backlog" })
  const [dialogOpen, setDialogOpen] = useState(false)
  const busy = disabled || updateCard.isPending
  // A press that does not travel is a click on the handle, not a drag.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function dropped(event: DragEndEvent) {
    if (!event.over) return
    const card = board.cards.find((item) => item.id === event.active.id)
    const placement = placementOfDrop(board.cards, String(event.active.id), String(event.over.id))
    if (card && placement) move(card, placement)
  }

  function openDialog(next: CardDialogTarget) {
    setTarget(next)
    setDialogOpen(true)
  }

  function move(card: Card, placement: Placement) {
    updateCard.mutate(
      { cardId: card.id, patch: { version: card.version, ...placement } },
      { onError },
    )
  }

  return (
    <section aria-label="Scientific board" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-prose text-xs text-muted-foreground">
          Columns show how far the work is. They say nothing about scientific validity: a card in
          Completed is finished work, not a confirmed result.
        </p>
        <Button onClick={() => openDialog({ mode: "create", status: "backlog" })} disabled={disabled}>
          <PlusIcon data-icon="inline-start" />
          New card
        </Button>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCorners} onDragEnd={dropped}>
      <div className="flex flex-col gap-3 md:flex-row md:overflow-x-auto md:pb-3">
        {board.workflow_statuses.map((status) => {
          const cards = board.cards.filter((card) => card.workflow_status === status)
          return (
            <Column key={status} status={status}>
              <header className="flex items-center justify-between gap-2 px-1 pb-2">
                <h3 className="text-sm font-medium">
                  {STATUS_LABELS[status]}{" "}
                  <span className="font-normal text-muted-foreground">{cards.length}</span>
                </h3>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Add card to ${STATUS_LABELS[status]}`}
                  disabled={disabled}
                  onClick={() => openDialog({ mode: "create", status })}
                >
                  <PlusIcon />
                </Button>
              </header>
              <SortableContext
                items={cards.map((card) => card.id)}
                strategy={verticalListSortingStrategy}
              >
                {cards.length === 0 ? (
                  <p className="px-1 py-4 text-center text-xs text-muted-foreground">No cards</p>
                ) : (
                  <ol className="space-y-2">
                    {cards.map((card, index) => (
                      <li key={card.id}>
                        <CardItem
                          card={card}
                          index={index}
                          count={cards.length}
                          statuses={board.workflow_statuses}
                          disabled={busy}
                          onOpen={() => openDialog({ mode: "edit", card })}
                          onMove={(placement) => move(card, placement)}
                        />
                      </li>
                    ))}
                  </ol>
                )}
              </SortableContext>
            </Column>
          )
        })}
      </div>
      </DndContext>

      <CardDialog
        projectId={projectId}
        statuses={board.workflow_statuses}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        target={target}
      />
    </section>
  )
}

/** A column of the board, and a place to drop a card at its end. */
function Column({ status, children }: { status: WorkflowStatus; children: ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: `${COLUMN_PREFIX}${status}` })
  return (
    <section
      ref={setNodeRef}
      aria-label={`${STATUS_LABELS[status]} column`}
      className={cn(
        "rounded-lg bg-muted/60 p-2 md:min-w-60 md:flex-1 md:basis-0",
        isOver && "ring-2 ring-ring/40",
      )}
    >
      {children}
    </section>
  )
}
