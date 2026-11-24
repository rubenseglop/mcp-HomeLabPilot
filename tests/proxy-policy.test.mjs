import test from "node:test";
import assert from "node:assert/strict";
import {
  READ_ONLY_TOOLS,
  isReadOnlyTool,
  filterToolsListPayload,
} from "../mcp-readonly-policy.mjs";

test("read-only policy is an explicit, bounded inventory", () => {
  assert.equal(READ_ONLY_TOOLS.size, 148);
  assert.equal(isReadOnlyTool("stack_status"), true);
  assert.equal(isReadOnlyTool("frigate_list_events"), true);
  assert.equal(isReadOnlyTool("questarr_get_library"), true);
  assert.equal(isReadOnlyTool("recyclarr_get_status"), true);
  assert.equal(isReadOnlyTool("seanime_audit_library"), true);
  assert.equal(isReadOnlyTool("seanime_get_settings"), true);
  assert.equal(isReadOnlyTool("seanime_confirm_update_setting"), false);
  assert.equal(isReadOnlyTool("seanime_preview_update_setting"), false);
  assert.equal(isReadOnlyTool("seanime_preview_add_to_anilist"), false);
  assert.equal(isReadOnlyTool("seanime_add_to_anilist"), false);
  assert.equal(isReadOnlyTool("seanime_preview_reassignment"), false);
  assert.equal(isReadOnlyTool("seanime_reassign_files"), false);
  assert.equal(isReadOnlyTool("tdarr_preview_requeue_files"), false);
  assert.equal(isReadOnlyTool("tdarr_confirm_requeue_files"), false);
  assert.equal(isReadOnlyTool("tdarr_preview_rescan_file"), false);
  assert.equal(isReadOnlyTool("tdarr_confirm_rescan_file"), false);
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


test("read-only proxy stays unpublished on a private agent control network", async () => {
  const { readFile } = await import("node:fs/promises");
  const compose = await readFile(new URL("../compose.yaml", import.meta.url), "utf8");
  const proxy = compose.match(/  homelabpilot-mcp-proxy:\n([\s\S]*?)\n  homelabpilot-agents:/);
  const agents = compose.match(/  homelabpilot-agents:\n([\s\S]*?)\n  homelabpilot-docker-gateway:/);
  assert.ok(proxy, "proxy service must exist");
  assert.ok(agents, "agent gateway service must exist");
  assert.doesNotMatch(proxy[1], /\n\s+ports:/, "proxy must not publish a host port");
  assert.match(proxy[1], /\n\s+- agent_control\s*$/, "proxy must use the private control network");
  assert.match(agents[1], /\n\s+- default\s*\n\s+- agent_control\s*$/, "agent gateway needs private proxy access and default egress");
  assert.match(compose, /  agent_control:\n\s+name: homelabpilot_agent_control\n\s+internal: true/, "agent control network must be internal");
});
