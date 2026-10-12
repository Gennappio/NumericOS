import { describe, expect, it } from "vitest"
import { experimentRecord } from "@/test/runs"
import { describeRule, needsSeed, ruleBound, rulesFor } from "./protocol"

const protocol = experimentRecord().protocol

describe("guardrail rules", () => {
  it("are found by the metric they watch", () => {
    expect(rulesFor(protocol, "max_abs_u")).toHaveLength(1)
    expect(rulesFor(protocol, "l2_error")).toEqual([])
  })

  it("read as what is watched, for how long, and what happens", () => {
    const [rule] = rulesFor(protocol, "max_abs_u")

    expect(ruleBound(rule)).toEqual({ side: "above", value: 1 })
    expect(describeRule(rule)).toBe(
      "max_abs_u above 1 for 3 consecutive samples: the program is stopped",
    )
    expect(describeRule({ metric: "mass", below: 0.99, action: "record" })).toBe(
      "mass below 0.99 for one sample: a warning is recorded",
    )
  })
})

describe("needsSeed", () => {
  it("is true when the command or a build command uses the run's seed", () => {
    expect(needsSeed(protocol)).toBe(false)
    expect(
      needsSeed({ ...protocol, execution: { command: ["abm", "--seed", "{seed}"] } }),
    ).toBe(true)
    expect(
      needsSeed({ ...protocol, execution: { command: ["abm"], build: [["gen", "{seed}"]] } }),
    ).toBe(true)
  })
})
