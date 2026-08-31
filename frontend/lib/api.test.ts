import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { messageFromResponse } from "./api.ts";

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
