import test from "node:test";
import assert from "node:assert/strict";
import {
  READ_ONLY_TOOLS,
  isReadOnlyTool,
  filterToolsListPayload,
} from "../mcp-readonly-policy.mjs";

test("read-only policy is an explicit, bounded inventory", () => {
  assert.equal(READ_ONLY_TOOLS.size, 140);
  assert.equal(isReadOnlyTool("stack_status"), true);
  assert.equal(isReadOnlyTool("seanime_audit_library"), true);
  assert.equal(isReadOnlyTool("flaresolverr_request_get"), false);
  assert.equal(isReadOnlyTool("arr_add_movie"), false);
  assert.equal(isReadOnlyTool("a_new_tool_get"), false);
  assert.equal(isReadOnlyTool(undefined), false);
});

test("tools/list filters unapproved tools in a single response", () => {
  const input = {
    jsonrpc: "2.0",
    id: 1,
    result: { tools: [{ name: "stack_status" }, { name: "arr_add_movie" }] },
  };
  const output = filterToolsListPayload(input);
  assert.deepEqual(output.result.tools.map((tool) => tool.name), ["stack_status"]);
  assert.equal(input.result.tools.length, 2, "filter must not mutate upstream payload");
});

test("tools/list filters each response in a JSON-RPC batch", () => {
  const input = [
    { jsonrpc: "2.0", id: 1, result: { tools: [{ name: "seanime_search_anime" }, { name: "seanime_reassign_files" }] } },
    { jsonrpc: "2.0", id: 2, result: { tools: [{ name: "stack_status" }, { name: "scryer_graphql" }] } },
  ];
  const output = filterToolsListPayload(input);
  assert.deepEqual(output.map((item) => item.result.tools.map((tool) => tool.name)), [
    ["seanime_search_anime"],
    ["stack_status"],
  ]);
});
