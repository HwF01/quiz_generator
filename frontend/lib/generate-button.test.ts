import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { generateSubmitLabel, isGenerateSubmitLocked, isJobInFlight } from "./generate-button.ts";

describe("generate button lock", () => {
  it("stays locked after generate request returns while the job is queued or running", () => {
    assert.equal(isGenerateSubmitLocked(false, "queued"), true);
    assert.equal(isGenerateSubmitLocked(false, "running"), true);
    assert.equal(generateSubmitLabel({ busy: false, jobStatus: "queued", hasPreview: true }), "生成中…");
  });

  it("is clickable again after the job fails, and idle with preview says 开始生成", () => {
    assert.equal(isGenerateSubmitLocked(false, "failed"), false);
    assert.equal(isJobInFlight("failed"), false);
    assert.equal(generateSubmitLabel({ busy: false, jobStatus: null, hasPreview: true }), "开始生成");
  });

  it("shows 提交中… only while the HTTP submit is in flight", () => {
    assert.equal(isGenerateSubmitLocked(true, null), true);
    assert.equal(generateSubmitLabel({ busy: true, jobStatus: null, hasPreview: true }), "提交中…");
  });

  it("unlocks back to 解析并配置 after the in-flight job is cleared", () => {
    assert.equal(isGenerateSubmitLocked(false, "running"), true);
    assert.equal(isGenerateSubmitLocked(false, null), false);
    assert.equal(generateSubmitLabel({ busy: false, jobStatus: null, hasPreview: false }), "解析并配置");
  });
});
