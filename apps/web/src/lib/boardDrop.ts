import type { Card, WorkflowStatus } from "@/api/client"
import type { Placement } from "@/components/board/CardItem"

export const COLUMN_PREFIX = "column:"

/**
 * Where a dragged card should go, from what it was dropped on: another card (it takes that
 * card's place) or a column (it goes to the end). Nothing when it was dropped where it is.
 */
export function placementOfDrop(cards: Card[], draggedId: string, overId: string): Placement | null {
  const dragged = cards.find((card) => card.id === draggedId)
  if (!dragged || draggedId === overId) return null
  const column = (status: WorkflowStatus) => cards.filter((card) => card.workflow_status === status)

  if (overId.startsWith(COLUMN_PREFIX)) {
    const status = overId.slice(COLUMN_PREFIX.length) as WorkflowStatus
    if (status !== dragged.workflow_status) return { workflow_status: status }
    const own = column(status)
    return own[own.length - 1]?.id === dragged.id ? null : { position: own.length - 1 }
  }

  const over = cards.find((card) => card.id === overId)
  if (!over) return null
  const position = column(over.workflow_status).findIndex((card) => card.id === over.id)
  return over.workflow_status === dragged.workflow_status
    ? { position }
    : { workflow_status: over.workflow_status, position }
}
