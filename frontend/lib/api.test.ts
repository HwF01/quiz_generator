import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ApiError, generationIdsFromError, messageFromResponse } from "./api.ts";

describe("messageFromResponse", () => {
  it("prefers JSON envelope message", () => {
    assert.equal(
      messageFromResponse(503, JSON.stringify({ code: 503, data: null, message: "模型服务暂不可用，请稍后重试" })),
      "模型服务暂不可用，请稍后重试",
    );
  });

  it("maps 504 to timeout copy", () => {
    assert.equal(messageFromResponse(504, "Gateway Timeout"), "请求超时，请稍后重试");
  });

  it("maps 502 to unreachable copy", () => {
    assert.equal(messageFromResponse(502, "Bad Gateway"), "服务暂不可达，请稍后重试");
  });

  it("maps HTML and Internal Server Error to unavailable copy", () => {
    assert.equal(messageFromResponse(500, "<html>Internal Server Error</html>"), "服务暂时不可用，请稍后重试");
    assert.equal(messageFromResponse(500, "Internal Server Error"), "服务暂时不可用，请稍后重试");
  });
});

describe("generationIdsFromError", () => {
  it("reads job_id and quiz_id from a 503 envelope error", () => {
    const error = new ApiError("任务队列暂不可用，请稍后重试", 503, {
      job_id: "job-1",
      quiz_id: "quiz-1",
    });
    assert.deepEqual(generationIdsFromError(error), { job_id: "job-1", quiz_id: "quiz-1" });
  });

  it("ignores ordinary errors and envelopes without ids", () => {
    assert.equal(generationIdsFromError(new Error("任务队列暂不可用，请稍后重试")), null);
    assert.equal(generationIdsFromError(new ApiError("失败", 503, null)), null);
    assert.equal(generationIdsFromError(new ApiError("失败", 503, { quiz_id: "quiz-1" })), null);
  });
});
