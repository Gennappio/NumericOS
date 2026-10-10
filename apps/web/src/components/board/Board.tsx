import { PlusIcon } from "lucide-react"
import { useState } from "react"
import type { Board as BoardData, Card } from "@/api/client"
import { useUpdateCard } from "@/api/queries"
import { CardDialog, type CardDialogTarget } from "@/components/board/CardDialog"
import { CardItem, type Placement } from "@/components/board/CardItem"
import { Button } from "@/components/ui/button"
import { STATUS_LABELS } from "@/lib/labels"

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

      <div className="flex flex-col gap-3 md:flex-row md:overflow-x-auto md:pb-3">
        {board.workflow_statuses.map((status) => {
          const cards = board.cards.filter((card) => card.workflow_status === status)
          return (
            <section
              key={status}
              aria-label={`${STATUS_LABELS[status]} column`}
              className="rounded-lg bg-muted/60 p-2 md:min-w-60 md:flex-1 md:basis-0"
            >
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
            </section>
          )
        })}
      </div>

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
