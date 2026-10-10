import { API_URL } from "@/api/client"
import { useConnectionState } from "@/api/queries"
import { cn } from "@/lib/utils"

export function ConnectionStatus() {
  const { state, version, degraded } = useConnectionState()
  const label =
    state === "connected"
      ? `Connected · API v${version}${degraded ? " · database needs migration" : ""}`
      : state === "unreachable"
        ? `Backend unreachable (${API_URL})`
        : "Checking backend…"

  return (
    <div
      role="status"
      aria-label="Backend connection"
      data-state={state}
      className="flex items-center gap-2 text-sm text-muted-foreground"
    >
      <span
        aria-hidden="true"
        className={cn(
          "inline-block size-2 rounded-full",
          state === "connected" && "bg-emerald-500",
          state === "unreachable" && "bg-red-500",
          state === "checking" && "animate-pulse bg-amber-400",
        )}
      />
      <span>{label}</span>
    </div>
  )
}
