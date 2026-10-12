import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { answerRecord, userMessage } from "@/test/agent"
import { MessageCard } from "./MessageCard"

describe("MessageCard", () => {
  it("shows a prompt as written", () => {
    render(<MessageCard message={userMessage()} supervisorAlive />)

    expect(screen.getByRole("article", { name: "Your message" })).toHaveTextContent(
      "Why is the explicit scheme unstable?",
    )
  })

  it("renders an answer with its mathematics, cost, model and what the agent did", () => {
    const { container } = render(<MessageCard message={answerRecord()} supervisorAlive />)

    const card = screen.getByRole("article", { name: "Agent answer" })
    expect(within(card).getByText("Answered")).toHaveAttribute("data-status", "final")
    expect(within(card).getByText("model claude-fable-5-1")).toBeVisible()
    expect(within(card).getByText("0.012 USD")).toBeVisible()
    expect(within(card).getByText("3 s")).toBeVisible()
    expect(container.querySelector(".katex-display")).not.toBeNull()
    const summary = within(card).getByText(/What the agent did \(2 actions, read 1 file/)
    expect(summary).toBeVisible()
    fireEvent.click(summary) // closed until asked for: the answer comes first
    const actions = within(card).getByRole("list", { name: "Actions of the agent" })
    expect(within(actions).getByText("Read")).toBeVisible()
    expect(within(actions).getByText("/work/heat2d/heat2d.py")).toBeVisible()
    expect(within(actions).getByRole("img", { name: "Tool succeeded" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Stop the agent/ })).toBeNull()
  })

  it("shows a working turn live, with a way to stop it", () => {
    const onStop = vi.fn()
    render(
      <MessageCard
        message={answerRecord({
          status: "running",
          markdown: "",
          cost_usd: null,
          finished_at: null,
          activity: [
            {
              kind: "tool",
              at: 1,
              text: null,
              tool: { id: "t", name: "Grep", summary: "dt in src", ok: null },
            },
          ],
        })}
        supervisorAlive
        onStop={onStop}
      />,
    )

    expect(screen.getByText("Working")).toHaveAttribute("data-status", "running")
    expect(screen.getByRole("img", { name: "Tool in progress" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Stop the agent…" }))
    const dialog = screen.getByRole("dialog")
    fireEvent.change(within(dialog).getByLabelText("Why (recorded with the turn)"), {
      target: { value: "wrong question" },
    })
    fireEvent.click(within(dialog).getByRole("button", { name: "Stop the agent" }))
    expect(onStop).toHaveBeenCalledWith("wrong question")
  })

  it("says that a queued turn waits, and for what", () => {
    render(
      <MessageCard
        message={answerRecord({ status: "queued", markdown: "", cost_usd: null, activity: [] })}
        supervisorAlive={false}
      />,
    )

    expect(screen.getByText(/Waiting for a supervisor/)).toBeVisible()
    expect(screen.getByText("No supervisor is running.")).toBeVisible()
  })

  it("shows an error, a stop or an interruption with its reason", () => {
    const { rerender } = render(
      <MessageCard
        message={answerRecord({ status: "failed", status_reason: "error_max_budget: too costly" })}
        supervisorAlive
      />,
    )
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The agent ended with an error: error_max_budget: too costly",
    )

    rerender(
      <MessageCard
        message={answerRecord({ status: "interrupted", status_reason: "the agent process ended" })}
        supervisorAlive
      />,
    )
    expect(screen.getByRole("alert")).toHaveTextContent("No answer: the agent process ended")
  })

  it("lists what the permission mode refused, never hiding it", () => {
    render(
      <MessageCard
        message={answerRecord({
          permission_denials: [{ tool_name: "Bash", summary: "pytest -q" }],
        })}
        supervisorAlive
      />,
    )

    const refused = screen.getByRole("region", { name: "Refused by the permission mode" })
    expect(within(refused).getByText("pytest -q")).toBeVisible()
  })
})
