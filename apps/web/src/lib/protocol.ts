import type { ExperimentProtocol } from "@/api/client"
import { formatNumber } from "@/lib/format"

type Rule = NonNullable<NonNullable<ExperimentProtocol["guardrails"]>["rules"]>[number]

/** The explicit bounds a contract states for one metric. */
export function rulesFor(protocol: ExperimentProtocol, metric: string): Rule[] {
  return (protocol.guardrails?.rules ?? []).filter((rule) => rule.metric === metric)
}

export function ruleBound(rule: Rule): { side: "above" | "below"; value: number } | undefined {
  if (typeof rule.above === "number") return { side: "above", value: rule.above }
  if (typeof rule.below === "number") return { side: "below", value: rule.below }
  return undefined
}

/** A rule in words: what is watched, for how long, and what happens then. */
export function describeRule(rule: Rule): string {
  const bound = ruleBound(rule)
  const patience = rule.patience ?? 1
  const samples = patience === 1 ? "one sample" : `${patience} consecutive samples`
  const consequence = (rule.action ?? "halt") === "halt" ? "the program is stopped" : "a warning is recorded"
  return `${rule.metric} ${bound?.side ?? "beyond"} ${bound ? formatNumber(bound.value) : "its bound"} for ${samples}: ${consequence}`
}

/** The command of the contract uses the run's seed, so a run must be given one. */
export function needsSeed(protocol: ExperimentProtocol): boolean {
  const commands = [protocol.execution.command, ...(protocol.execution.build ?? [])]
  return commands.some((command) => command.some((argument) => argument.includes("{seed}")))
}
