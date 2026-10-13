import "@xyflow/react/dist/style.css"
import {
  applyNodeChanges,
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  getSmoothStepPath,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useStoreApi,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react"
import {
  createContext,
  useContext,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type Ref,
} from "react"
import type { PipelineEdge, PipelineNodeKind } from "@/api/client"
import {
  layoutPipeline,
  READABLE_ZOOM,
  startViewport,
  type Positions,
  type Sized,
} from "@/components/pipeline/layout"
import { DRAG_HANDLE } from "@/components/pipeline/PipelineBox"
import { forgetPositions, readPositions, writePositions } from "@/components/pipeline/positions"
import { KIND_COLORS } from "@/lib/pipeline"
import { cn } from "@/lib/utils"

export interface CanvasNode {
  id: string
  kind: PipelineNodeKind
  title: string
}

export interface CanvasHandle {
  /** Bring a box to the middle of the board. */
  show: (id: string) => void
  /** Put every box back where the order of a run puts it, and forget where they were put. */
  tidy: () => void
}

export interface PipelineCanvasProps {
  /** The pipeline and its version: the name under which this browser remembers positions. */
  documentId: string
  version: number
  nodes: CanvasNode[]
  edges: PipelineEdge[]
  /** What a box shows; it is drawn inside the board, where it can be moved. */
  renderBox: (id: string) => ReactNode
  ref?: Ref<CanvasHandle>
}

const ARROW = "#94a3b8"

/** The boxes are drawn by the page, not kept in the board's own state: a comment or an
 * answer of the agent changes what a box shows without touching where it is. */
const Boxes = createContext<(id: string) => ReactNode>(() => null)

function BoxNode({ id }: NodeProps) {
  const render = useContext(Boxes)
  return (
    <>
      <Handle type="target" position={Position.Left} isConnectable={false} className="pipeline-handle" />
      {render(id)}
      <Handle type="source" position={Position.Right} isConnectable={false} className="pipeline-handle" />
    </>
  )
}

const NODE_TYPES = { box: BoxNode }

/**
 * An arrow with what passes along it written at its middle. The words are text of the page,
 * not of the drawing: they wrap, so that a long label does not run over the boxes.
 */
function ArrowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  label,
}: EdgeProps) {
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 12,
  })
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
      {label && (
        <EdgeLabelRenderer>
          <div
            className="pipeline-arrow-label"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

const EDGE_TYPES = { arrow: ArrowEdge }

const sizesOf = (nodes: Node[]): (Sized & { x: number; y: number })[] =>
  nodes.map((node) => ({
    id: node.id,
    width: node.measured?.width ?? 0,
    height: node.measured?.height ?? 0,
    ...node.position,
  }))

/**
 * The board of a pipeline: its boxes where the order of a run puts them (or where the
 * researcher dragged them), the arrows between them, and a surface that is moved and zoomed
 * like a whiteboard. The board only places things: what a box says is the page's.
 */
export function PipelineCanvas(props: PipelineCanvasProps) {
  return (
    <ReactFlowProvider>
      <Flow {...props} />
    </ReactFlowProvider>
  )
}

function Flow({ documentId, version, nodes: boxes, edges: arrows, renderBox, ref }: PipelineCanvasProps) {
  const flow = useReactFlow()
  const store = useStoreApi()
  const [remembered] = useState(() =>
    readPositions(
      documentId,
      version,
      boxes.map((box) => box.id),
    ),
  )
  const [nodes, setNodes] = useState<Node[]>(() =>
    boxes.map((box) => ({
      id: box.id,
      type: "box",
      position: remembered?.[box.id] ?? { x: 0, y: 0 },
      data: {},
      dragHandle: `.${DRAG_HANDLE}`,
    })),
  )
  // Nothing is shown before the boxes were measured and placed: no jump from a heap.
  const [shown, setShown] = useState(false)
  // What the handlers below work on: several changes can arrive before the next render.
  const latest = useRef(nodes)
  const arranged = useRef(remembered !== null)
  const viewed = useRef(false)

  function keep(next: Node[]) {
    latest.current = next
    setNodes(next)
  }

  function place(current: Node[]): Node[] {
    const positions = layoutPipeline(sizesOf(current), arrows)
    return current.map((node) => ({ ...node, position: positions[node.id] ?? node.position }))
  }

  function view(current: Node[], duration = 0) {
    const state = store.getState()
    const frame = state.domNode?.getBoundingClientRect()
    const width = state.width || frame?.width || 0
    const height = state.height || frame?.height || 0
    void flow.setViewport(startViewport(sizesOf(current), width, height), { duration })
  }

  function changed(changes: NodeChange[]) {
    let next = applyNodeChanges(changes, latest.current)
    const measured = next.every((node) => node.measured?.width && node.measured?.height)
    if (measured && changes.some((change) => change.type === "dimensions")) {
      // A box that grew (a clarification inside it) moves the others, unless the researcher
      // placed them: then they stay where they were put.
      if (!arranged.current) next = place(next)
      if (!viewed.current) {
        viewed.current = true
        view(next)
        setShown(true)
      }
    }
    keep(next)
  }

  function dragged(moved: Node[]) {
    const dropped = new Map(moved.map((node) => [node.id, node.position]))
    const positions: Positions = Object.fromEntries(
      latest.current.map((node) => [node.id, dropped.get(node.id) ?? node.position]),
    )
    arranged.current = true
    writePositions(documentId, version, positions)
  }

  useImperativeHandle(ref, () => ({
    show: (id) =>
      void flow.fitView({
        nodes: [{ id }],
        duration: 300,
        padding: 0.3,
        minZoom: READABLE_ZOOM,
        maxZoom: 1,
      }),
    tidy: () => {
      arranged.current = false
      forgetPositions(documentId)
      const next = place(latest.current)
      keep(next)
      view(next, 300)
    },
  }))

  const kinds = useMemo(() => new Map(boxes.map((box) => [box.id, box.kind])), [boxes])
  const titles = useMemo(() => new Map(boxes.map((box) => [box.id, box.title])), [boxes])
  const edges: Edge[] = useMemo(() => {
    const left = new Map(nodes.map((node) => [node.id, node.position.x]))
    return arrows.map((arrow) => {
      // An arrow that points back closes a loop: it is drawn dashed.
      const back = (left.get(arrow.target) ?? 0) < (left.get(arrow.source) ?? 0)
      const said = arrow.label ? `: ${arrow.label}` : ""
      return {
        id: `${arrow.source}->${arrow.target}`,
        source: arrow.source,
        target: arrow.target,
        type: "arrow",
        label: arrow.label || undefined,
        ariaLabel: `${titles.get(arrow.source)} to ${titles.get(arrow.target)}${said}`,
        markerEnd: { type: MarkerType.ArrowClosed, color: ARROW, width: 18, height: 18 },
        style: { stroke: ARROW, strokeWidth: 1.75, strokeDasharray: back ? "6 4" : undefined },
      }
    })
  }, [arrows, nodes, titles])

  return (
    <Boxes value={renderBox}>
      <ReactFlow
        className={cn("transition-opacity duration-200", shown ? "opacity-100" : "opacity-0")}
        aria-label="Pipeline board"
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onNodesChange={changed}
        onNodeDragStop={(_event, _node, moved) => dragged(moved)}
        // A whiteboard: two fingers (or the wheel) move it, a pinch or Ctrl/Cmd + wheel zooms.
        panOnScroll
        zoomOnScroll={false}
        zoomOnDoubleClick={false}
        minZoom={0.2}
        maxZoom={2}
        // Read and arranged, never edited: no connecting, no selecting, no deleting.
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        deleteKeyCode={null}
        selectionKeyCode={null}
        multiSelectionKeyCode={null}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1.5} color="#cbd5e1" />
        <Controls showInteractive={false} position="bottom-left" />
        <MiniMap
          pannable
          zoomable
          position="bottom-right"
          ariaLabel="Map of the board"
          style={{ width: 150, height: 96 }}
          nodeColor={(node) => KIND_COLORS[kinds.get(node.id) ?? "process"]}
          nodeStrokeColor="#94a3b8"
        />
      </ReactFlow>
    </Boxes>
  )
}
