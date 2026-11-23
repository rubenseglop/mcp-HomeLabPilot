import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createProxyHandler } from "../mcp-readonly-proxy.mjs";

const TOKEN = "test-token-that-is-long-enough-for-the-proxy";

async function withProxy(fetchImpl, run) {
  const server = http.createServer(createProxyHandler({
    target: "http://upstream.invalid/mcp",
    token: TOKEN,
    fetchImpl,
  }));
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  try {
    await run(`http://127.0.0.1:${address.port}`);
  } finally {
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
}

function rpc(method, id, params = {}) {
  return { jsonrpc: "2.0", id, method, params };
}

test("blocked Seanime mutation is rejected before any upstream request", async () => {
  let upstreamCalls = 0;
  await withProxy(async () => {
    upstreamCalls += 1;
    return new Response("{}", { status: 200 });
  }, async (base) => {
    const response = await fetch(base + "/mcp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(rpc("tools/call", 7, {
        name: "seanime_reassign_files",
        arguments: { folder_path: "/media/anime", source_media_id: 1, target_media_id: 2 },
      })),
    });
    const payload = await response.json();
    assert.equal(response.status, 200);
    assert.equal(payload.error.code, -32003);
    assert.match(payload.error.message, /read-only/);
    assert.equal(upstreamCalls, 0);
  });
});

test("blocked Tdarr mutation is rejected before any upstream request", async () => {
  let upstreamCalls = 0;
  await withProxy(async () => {
    upstreamCalls += 1;
    return new Response("{}", { status: 200 });
  }, async (base) => {
    const response = await fetch(base + "/mcp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(rpc("tools/call", 8, {
        name: "tdarr_confirm_requeue_files",
        arguments: { file_ids: ["file-1"] },
      })),
    });
    assert.equal((await response.json()).error.code, -32003);
    assert.equal(upstreamCalls, 0);
  });
});

test("an allowed read call reaches upstream with the server bearer token", async () => {
  let captured;
  await withProxy(async (url, options) => {
    captured = { url, options };
    return new Response(JSON.stringify({
      jsonrpc: "2.0", id: 9, result: { content: [{ type: "text", text: "ok" }] },
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }, async (base) => {
    const request = rpc("tools/call", 9, {
      name: "tdarr_search_files",
      arguments: { search_term: "film" },
    });
    const response = await fetch(base + "/mcp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    });
    assert.equal(response.status, 200);
    assert.equal(captured.url, "http://upstream.invalid/mcp");
    assert.equal(captured.options.headers.authorization, "Bearer " + TOKEN);
    assert.deepEqual(JSON.parse(captured.options.body), request);
  });
});

test("a batch containing one blocked write is rejected atomically", async () => {
  let upstreamCalls = 0;
  await withProxy(async () => {
    upstreamCalls += 1;
    return new Response("[]", { status: 200 });
  }, async (base) => {
    const batch = [
      rpc("tools/call", 1, { name: "stack_status", arguments: {} }),
      rpc("tools/call", 2, { name: "seanime_confirm_update_setting", arguments: {} }),
    ];
    const response = await fetch(base + "/mcp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(batch),
    });
    const payload = await response.json();
    assert.equal(payload.length, 2);
    assert.ok(payload.every((item) => item.error.code === -32003));
    assert.equal(upstreamCalls, 0);
  });
});

test("tools/list is filtered by the exact read-only allowlist", async () => {
  await withProxy(async () => new Response(JSON.stringify({
    jsonrpc: "2.0", id: 10, result: { tools: [
      { name: "seanime_get_settings" },
      { name: "seanime_add_to_anilist" },
      { name: "tdarr_get_nodes" },
      { name: "tdarr_preview_rescan_file" },
    ] },
  }), {
    status: 200,
    headers: { "content-type": "application/json" },
  }), async (base) => {
    const response = await fetch(base + "/mcp", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(rpc("tools/list", 10)),
    });
    const payload = await response.json();
    assert.deepEqual(payload.result.tools.map((item) => item.name), [
      "seanime_get_settings", "tdarr_get_nodes",
    ]);
  });
});
