import { describe, expect, it } from "vitest"
import { formatBytes, formatNumber, formatSeconds, formatValue } from "./format"

describe("formatNumber", () => {
  it("keeps enough digits to tell two runs apart", () => {
    expect(formatNumber(0.000129857451)).toBe("0.000129857")
    expect(formatNumber(0.0000129857451)).toBe("1.29857e-5")
    expect(formatNumber(0.09334214207)).toBe("0.0933421")
    expect(formatNumber(4776.120262943853)).toBe("4776.12")
    expect(formatNumber(339)).toBe("339")
    expect(formatNumber(18366464)).toBe("18366464") // whole numbers keep all their digits
    expect(formatNumber(1234567.891)).toBe("1.23457e6")
  })

  it("uses an exponent for very small and very large magnitudes", () => {
    expect(formatNumber(9.159235169e-11)).toBe("9.15924e-11")
    expect(formatNumber(2.995930797456034e18)).toBe("2.99593e18")
    expect(formatNumber(-1.5e-7)).toBe("-1.5e-7")
  })

  it("never shows a small value as zero", () => {
    expect(formatNumber(1e-300)).toBe("1e-300")
    expect(formatNumber(0)).toBe("0")
  })
})

describe("formatValue", () => {
  it("names a non-finite value instead of showing a number", () => {
    expect(formatValue(null, "nan")).toBe("NaN")
    expect(formatValue(null, "inf")).toBe("+∞")
    expect(formatValue(null, "-inf")).toBe("−∞")
  })

  it("shows a missing value as missing", () => {
    expect(formatValue(null)).toBe("–")
    expect(formatValue(undefined, null)).toBe("–")
    expect(formatValue(0.5)).toBe("0.5")
  })
})

describe("formatBytes and formatSeconds", () => {
  it("uses binary units for memory", () => {
    expect(formatBytes(512)).toBe("512 B")
    expect(formatBytes(17891328)).toBe("17.1 MiB")
    expect(formatBytes(3 * 1024 ** 3)).toBe("3.0 GiB")
  })

  it("reads durations at the scale they have", () => {
    expect(formatSeconds(0.054)).toBe("54 ms")
    expect(formatSeconds(11.625)).toBe("11.6 s")
    expect(formatSeconds(125)).toBe("2 min 5 s")
    expect(formatSeconds(3780)).toBe("1 h 3 min")
  })
})
