import { useState, type PointerEvent } from "react"
import {
  bandPath,
  linearAxis,
  linePath,
  logAxis,
  nearestIndex,
  segments,
  type ChartPoint,
} from "@/lib/chart"
import { formatNumber } from "@/lib/format"
import type { Mark } from "@/lib/metricChart"

export interface Threshold {
  value: number
  label: string
}

interface LineChartProps {
  /** Accessible name of the chart, e.g. "l2_error over step". */
  label: string
  /** Ordered by x. */
  points: ChartPoint[]
  xLabel: string
  scale?: "linear" | "log"
  /** Bounds stated by the contract, drawn as dashed lines. */
  thresholds?: Threshold[]
  /** Positions of samples that are not finite: they cannot be drawn, so they are marked. */
  marks?: Mark[]
  /**
   * A value the vertical axis always includes, e.g. 0 for a quantity whose size matters more
   * than its wobble. Without it the axis spans just the data.
   */
  baseline?: number
}

const WIDTH = 640
const HEIGHT = 220
const PLOT = { left: 64, right: WIDTH - 12, top: 14, bottom: HEIGHT - 32 }

/**
 * A line over x with the extremes of each stretch as a band behind it.
 *
 * It draws only what was measured. Where a sample is not finite the line breaks and a mark
 * says so; on a logarithmic axis a value that has no logarithm is left out and counted below
 * the chart. Nothing is interpolated across a gap.
 */
export function LineChart({
  label,
  points,
  xLabel,
  scale = "linear",
  thresholds = [],
  marks = [],
  baseline,
}: LineChartProps) {
  const [hovered, setHovered] = useState<number | null>(null)
  const log = scale === "log"
  const onAxis = (value: number | null | undefined): value is number =>
    typeof value === "number" && Number.isFinite(value) && (!log || value > 0)

  const drawable = points.filter((point) => onAxis(point.y))
  const leftOut = points.filter((point) => point.y !== null && !onAxis(point.y)).length
  const shown = thresholds.filter((threshold) => onAxis(threshold.value))
  const values = [
    ...drawable.flatMap((point) => [point.y, point.low, point.high].filter(onAxis)),
    ...shown.map((threshold) => threshold.value),
    ...(onAxis(baseline) ? [baseline] : []),
  ]
  const xs = [...points.map((point) => point.x), ...marks.map((mark) => mark.x)]
  const x = linearAxis(xs, [PLOT.left, PLOT.right], 6)
  const y = (log ? logAxis : linearAxis)(values, [PLOT.bottom, PLOT.top])

  const runs = segments(points, (point) => onAxis(point.y))
  const line = linePath(
    runs.map((run) => run.map((point) => ({ x: x.position(point.x), y: y.position(point.y!) }))),
  )
  const band = bandPath(
    runs
      .map((run) => run.filter((point) => onAxis(point.low) && onAxis(point.high)))
      .filter((run) => run.length > 1)
      .map((run) =>
        run.map((point) => ({
          x: x.position(point.x),
          low: y.position(point.low!),
          high: y.position(point.high!),
        })),
      ),
  )
  const single = drawable.length === 1 ? drawable[0] : undefined
  const focus = hovered !== null && hovered < drawable.length ? drawable[hovered] : undefined

  function onPointerMove(event: PointerEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect()
    if (box.width === 0 || drawable.length === 0) return
    const ratio = (event.clientX - box.left) / box.width
    const position = x.domain[0] + ratio * (x.domain[1] - x.domain[0])
    setHovered(nearestIndex(drawable, position))
  }

  const range =
    drawable.length > 0
      ? `${drawable.length} points, ${xLabel} ${formatNumber(drawable[0].x)} to ${formatNumber(drawable.at(-1)!.x)}`
      : "no finite sample to draw"

  return (
    <figure className="min-w-0">
      <svg
        role="img"
        aria-label={`${label}: ${range}`}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full"
      >
        {y.ticks.map((tick) => (
          <g key={`y${tick}`}>
            <line
              x1={PLOT.left}
              x2={PLOT.right}
              y1={y.position(tick)}
              y2={y.position(tick)}
              className="stroke-border"
              strokeWidth={1}
            />
            <text
              x={PLOT.left - 6}
              y={y.position(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-muted-foreground text-[11px]"
            >
              {y.format(tick)}
            </text>
          </g>
        ))}
        {x.ticks.map((tick) => (
          <text
            key={`x${tick}`}
            x={x.position(tick)}
            y={PLOT.bottom + 14}
            textAnchor="middle"
            className="fill-muted-foreground text-[11px]"
          >
            {x.format(tick)}
          </text>
        ))}
        <text
          x={PLOT.right}
          y={HEIGHT - 4}
          textAnchor="end"
          className="fill-muted-foreground text-[11px]"
        >
          {xLabel}
        </text>
        <line
          x1={PLOT.left}
          x2={PLOT.right}
          y1={PLOT.bottom}
          y2={PLOT.bottom}
          className="stroke-foreground/40"
          strokeWidth={1}
        />

        {band && <path d={band} className="fill-sky-500/20" data-part="band" />}
        {line && (
          <path
            d={line}
            fill="none"
            className="stroke-sky-700"
            strokeWidth={1.5}
            strokeLinejoin="round"
            data-part="line"
          />
        )}
        {single && (
          <circle cx={x.position(single.x)} cy={y.position(single.y!)} r={3} className="fill-sky-700" />
        )}

        {shown.map((threshold) => (
          <g key={threshold.label} data-part="threshold">
            <line
              x1={PLOT.left}
              x2={PLOT.right}
              y1={y.position(threshold.value)}
              y2={y.position(threshold.value)}
              className="stroke-rose-600"
              strokeWidth={1}
              strokeDasharray="5 4"
            />
            <text
              x={PLOT.right - 4}
              y={y.position(threshold.value) - 4}
              textAnchor="end"
              // A halo in the colour of the card keeps the label readable where the line of
              // the data passes behind it.
              paintOrder="stroke"
              stroke="var(--card)"
              strokeWidth={4}
              className="fill-rose-700 text-[11px]"
            >
              {threshold.label}
            </text>
          </g>
        ))}

        {marks.map((mark) => (
          <g key={`${mark.x}-${mark.label}`} data-part="non-finite">
            <title>{mark.label}</title>
            <line
              x1={x.position(mark.x)}
              x2={x.position(mark.x)}
              y1={PLOT.top}
              y2={PLOT.bottom}
              className="stroke-red-600/50"
              strokeWidth={1}
            />
            <path
              d={`M${x.position(mark.x) - 5},${PLOT.top - 9}h10l-5,9z`}
              className="fill-red-600"
            />
          </g>
        ))}

        {focus && (
          <g pointerEvents="none">
            <line
              x1={x.position(focus.x)}
              x2={x.position(focus.x)}
              y1={PLOT.top}
              y2={PLOT.bottom}
              className="stroke-foreground/30"
              strokeWidth={1}
            />
            <circle cx={x.position(focus.x)} cy={y.position(focus.y!)} r={3.5} className="fill-sky-700" />
          </g>
        )}
        <rect
          x={PLOT.left}
          y={PLOT.top}
          width={PLOT.right - PLOT.left}
          height={PLOT.bottom - PLOT.top}
          fill="transparent"
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHovered(null)}
        />
      </svg>
      <figcaption className="min-h-5 text-xs text-muted-foreground" aria-live="off">
        {focus ? (
          <span className="font-mono">
            {xLabel} {formatNumber(focus.x)}: {formatNumber(focus.y!, 8)}
            {onAxis(focus.low) && onAxis(focus.high) && focus.low !== focus.high && (
              <>
                {" "}
                (within {formatNumber(focus.low, 8)} .. {formatNumber(focus.high, 8)})
              </>
            )}
          </span>
        ) : (
          <>
            {log && "Logarithmic axis. "}
            {leftOut > 0 &&
              `${leftOut} ${leftOut === 1 ? "value that is" : "values that are"} not positive cannot be shown on it. `}
            {marks.length > 0 && "A red mark is a sample that is not finite."}
          </>
        )}
      </figcaption>
    </figure>
  )
}
