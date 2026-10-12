import type { CardType } from "@/api/client"
import { Badge } from "@/components/ui/badge"
import { CARD_TYPE_LABELS, CARD_TYPE_STYLES } from "@/lib/labels"

/** The kind of research object a card stands for. It says nothing about validity. */
export function TypeBadge({ type }: { type: CardType }) {
  return (
    <Badge variant="outline" data-card-type={type} className={CARD_TYPE_STYLES[type]}>
      {CARD_TYPE_LABELS[type]}
    </Badge>
  )
}
