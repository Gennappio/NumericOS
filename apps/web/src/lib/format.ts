/**
 * Numbers as someone who compares runs reads them: enough digits to tell two runs apart, an
 * exponent when the magnitude calls for one, never a rounded "0" for a small non-zero value.
 */
export function formatNumber(value: number, digits = 6): string {
  if (value === 0) return "0"
  const magnitude = Math.abs(value)
  // A count or a size in bytes is exact: it keeps all its digits.
  if (Number.isInteger(value) && magnitude < 1e15) return String(value)
  const rounded = Number(value.toPrecision(digits))
  if (magnitude >= 1e6 || magnitude < 1e-4) return rounded.toExponential().replace("e+", "e")
  return String(rounded)
}

const NON_FINITE_LABELS: Record<string, string> = { nan: "NaN", inf: "+∞", "-inf": "−∞" }

/** A metric value that may be non-finite. The API sends those as a word, never as a number. */
export function formatValue(
  value: number | null | undefined,
  nonFinite?: string | null,
  digits = 6,
): string {
  if (value === null || value === undefined) {
    return nonFinite ? (NON_FINITE_LABELS[nonFinite] ?? nonFinite) : "–"
  }
  return formatNumber(value, digits)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ["KiB", "MiB", "GiB", "TiB"]
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(1)} ${units[unit]}`
}

export function formatSeconds(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`
  if (seconds < 60) return `${Number(seconds.toPrecision(3))} s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ${Math.round(seconds - minutes * 60)} s`
  const hours = Math.floor(minutes / 60)
  return `${hours} h ${minutes - hours * 60} min`
}

/** The first characters of a digest or commit: enough to recognise it, with the rest a hover away. */
export function shortHash(hash: string, length = 12): string {
  return hash.slice(0, length)
}
