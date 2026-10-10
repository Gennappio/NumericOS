import { describe, expect, it } from "vitest"
import { ApiError, ApiUnreachableError } from "@/api/client"
import { describeError, fieldErrors } from "./errors"

const validation = new ApiError(422, {
  code: "VALIDATION_ERROR",
  message: "Request validation failed",
  details: {
    errors: [
      { loc: ["body", "title"], msg: "String should have at least 1 character", type: "x" },
      { loc: ["body", "root_path"], msg: "Value error, root_path must be an absolute path" },
    ],
  },
})

describe("fieldErrors", () => {
  it("maps a 422 envelope to messages per request field", () => {
    expect(fieldErrors(validation)).toEqual({
      title: "String should have at least 1 character",
      root_path: "Value error, root_path must be an absolute path",
    })
  })

  it("returns nothing for other errors", () => {
    const stale = new ApiError(409, { code: "STALE_REVISION", message: "stale", details: {} })

    expect(fieldErrors(stale)).toEqual({})
    expect(fieldErrors(new Error("boom"))).toEqual({})
  })
})

describe("describeError", () => {
  it("explains a stale version in terms of what to do next", () => {
    const stale = new ApiError(409, { code: "STALE_REVISION", message: "stale", details: {} })

    expect(describeError(stale)).toMatch(/changed elsewhere/)
  })

  it("never claims a save when the backend is unreachable", () => {
    const unreachable = new ApiUnreachableError("http://127.0.0.1:8765", new TypeError("x"))

    expect(describeError(unreachable)).toMatch(/not reachable.*Nothing was saved/)
  })

  it("keeps the API message and code for other API errors", () => {
    const mismatch = new ApiError(409, {
      code: "PROJECT_MISMATCH",
      message: "card does not belong to project",
      details: {},
    })

    expect(describeError(mismatch)).toBe("card does not belong to project (PROJECT_MISMATCH)")
  })
})
