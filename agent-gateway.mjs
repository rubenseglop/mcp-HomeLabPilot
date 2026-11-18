import http from "node:http";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";

const PORT = Number(process.env.AGENT_GATEWAY_PORT || 8766);

const STATE = process.env.AGENT_STATE_DIR || "/state";
const CODEX_HOME = process.env.CODEX_HOME || "/home/node/.codex";
const STORE = path.join(STATE, "conversations.json");
const jobs = new Map();
let store = { conversations: [] };
const now = () => new Date().toISOString();

async function loadStore() {
  try { store = JSON.parse(await fs.readFile(STORE, "utf8")); }
  catch { store = { conversations: [] }; }
}
async function saveStore() {
  await fs.mkdir(STATE, { recursive: true });
  const tmp = STORE + ".tmp";
  await fs.writeFile(tmp, JSON.stringify(store, null, 2), { mode: 0o600 });
  await fs.rename(tmp, STORE);
}
function send(res, status, data) {
  const body = Buffer.from(JSON.stringify(data));
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "content-length": body.length, "cache-control": "no-store" });
  res.end(body);
}
async function readBody(req) {
  const chunks = []; let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 65536) throw new Error("Request body too large");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}
function conversationView(c) {
  return { id: c.id, title: c.title, created_at: c.created_at, updated_at: c.updated_at, messages: c.messages || [] };
}
function runCodex(conversation, prompt, job) {
  const args = conversation.thread_id
    ? ["exec", "resume", conversation.thread_id, "--json", "--sandbox", "read-only", "--skip-git-repo-check", "-"]
    : ["exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check", "-"];
  const child = spawn("codex", args, {
    cwd: "/workspace",
    env: (() => { const clean = { ...process.env, CODEX_HOME, HOME: "/home/node", NO_COLOR: "1" }; delete clean.HOMELABPILOT_AGENT_GATEWAY_TOKEN; return clean; })(),
    stdio: ["pipe", "pipe", "pipe"]
  });
  job.pid = child.pid;
  let pending = "";
  let stderrTail = "";
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", chunk => {
    pending += chunk;
    const lines = pending.split("\n"); pending = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      let event;
      try { event = JSON.parse(line); } catch { continue; }
      if (event.type === "thread.started" && event.thread_id) conversation.thread_id = event.thread_id;
      if (event.type === "item.completed" || event.type === "item.updated") {
        const item = event.item || {};
        if (item.type === "agent_message" && typeof item.text === "string") job.answer = item.text;
        if (item.type === "mcp_tool_call") job.activities.push({ type: "mcp", name: item.server || "MCP", tool: item.tool || item.name || "tool", status: item.status || "running" });
        else if (item.type === "command_execution") job.activities.push({ type: "command", name: "Comando", status: item.status || "completed" });
      }
      if (event.type === "turn.failed" || event.type === "error") job.error = String(event.message || event.error || "Codex ha encontrado un error");
      job.events.push({ type: event.type, item_type: event.item?.type || null, text: event.item?.type === "agent_message" ? String(event.item.text || "").slice(0, 12000) : undefined, status: event.item?.status || undefined });
      if (job.events.length > 250) job.events.shift();
      job.updated_at = now();
    }
  });
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", chunk => { stderrTail = (stderrTail + chunk).slice(-4000); });
  child.on("error", err => {
    job.status = "failed"; job.error = "No se pudo iniciar Codex: " + err.message; job.updated_at = now();
  });
  child.on("close", async code => {
    if (pending.trim()) {
      try {
        const event = JSON.parse(pending);
        if (event.type === "thread.started" && event.thread_id) conversation.thread_id = event.thread_id;
        if (event.item?.type === "agent_message") job.answer = event.item.text || job.answer;
      } catch {}
    }
    job.status = code === 0 && !job.error ? "completed" : "failed";
    if (job.status === "failed" && !job.error) job.error = stderrTail.trim().slice(-1200) || "Codex terminó con código " + code;
    conversation.updated_at = now();
    conversation.messages.push({ role: "assistant", content: job.answer || job.error || "Codex no ha devuelto texto.", created_at: now() });
    job.updated_at = now();
    await saveStore();
  });
  const guardedPrompt = [
    "Eres el agente Codex integrado en HomeLabPilot. Responde en el idioma del usuario.",
    "Puedes consultar los servicios usando las herramientas MCP de HomeLabPilot.",
    "MODO DE SEGURIDAD DE ESTA VERSION: SOLO LECTURA. Utiliza únicamente herramientas de consulta.",
    "No invoques herramientas que creen, cambien, descarguen, importen, graben, borren, muevan, pausen, reanuden, reinicien o modifiquen recursos o configuración.",
    "No invoques herramientas de confirmación, aunque el usuario pida realizar una acción. Explica qué operación sería necesaria y deja claro que esta versión del chat todavía no permite ejecutarla.",
    "No afirmes haber realizado cambios. Nunca reveles tokens, contraseñas ni datos de autenticación.",
    "",
    "SOLICITUD DEL USUARIO:",
    prompt
  ].join("\n");
  child.stdin.end(guardedPrompt);
}

await fs.mkdir(CODEX_HOME, { recursive: true });
await fs.writeFile(path.join(CODEX_HOME, "config.toml"),
  '[mcp_servers.homelabpilot]\nurl = "http://homelabpilot-mcp-proxy:8001/mcp"\nenabled = true\nrequired = true\n',
  { mode: 0o600 });
await loadStore();

const server = http.createServer(async (req, res) => {
  if (!safeEqual((req.headers.authorization || "").replace(/^Bearer\s+/i, ""), TOKEN) || TOKEN.length < 32) {
    send(res, 401, { error: "Unauthorized" }); return;
  }
  const url = new URL(req.url, "http://localhost");
  try {
    if (req.method === "GET" && url.pathname === "/health") {
      let authenticated = false;
      try { await fs.access(path.join(CODEX_HOME, "auth.json")); authenticated = true; } catch {}
      send(res, 200, { ok: true, agent: "codex", authenticated, mcp_configured: true }); return;
    }
    if (req.method === "GET" && url.pathname === "/conversations") {
      send(res, 200, store.conversations.slice().sort((a,b) => b.updated_at.localeCompare(a.updated_at)).map(c => ({ id:c.id, title:c.title, created_at:c.created_at, updated_at:c.updated_at }))); return;
    }
    if (req.method === "GET" && url.pathname.startsWith("/conversations/")) {
      const id = url.pathname.split("/")[2];
      const c = store.conversations.find(x => x.id === id);
      if (!c) { send(res, 404, { error:"Conversation not found" }); return; }
      send(res, 200, conversationView(c)); return;
    }
    if (req.method === "DELETE" && url.pathname.startsWith("/conversations/")) {
      const id = url.pathname.split("/")[2];
      store.conversations = store.conversations.filter(x => x.id !== id);
      await saveStore(); send(res, 200, { ok:true }); return;
    }
    if (req.method === "POST" && url.pathname === "/chat") {
      const body = await readBody(req);
      const prompt = String(body.prompt || "").trim();
      if (!prompt || prompt.length > 20000) { send(res, 400, { error:"El mensaje debe tener entre 1 y 20.000 caracteres." }); return; }
      if (jobs.size >= 3 && [...jobs.values()].some(j => j.status === "running")) { send(res, 429, { error:"Ya hay tres tareas de Codex en ejecución." }); return; }
      let conversation = store.conversations.find(x => x.id === body.conversation_id);
      if (body.conversation_id && !conversation) { send(res, 404, { error:"Conversation not found" }); return; }
      if (!conversation) {
        conversation = { id:randomUUID(), title:prompt.slice(0,80), created_at:now(), updated_at:now(), thread_id:null, messages:[] };
        store.conversations.push(conversation);
      }
      conversation.messages.push({ role:"user", content:prompt, created_at:now() });
      const id = randomUUID();
      const job = { id, conversation_id:conversation.id, status:"running", answer:"", error:null, events:[], activities:[], created_at:now(), updated_at:now() };
      jobs.set(id, job); await saveStore(); runCodex(conversation, prompt, job);
      send(res, 202, { job_id:id, conversation_id:conversation.id }); return;
    }
    if (req.method === "GET" && url.pathname.startsWith("/jobs/")) {
      const id = url.pathname.split("/")[2]; const job = jobs.get(id);
      if (!job) { send(res, 404, { error:"Job not found (it may have expired after a gateway restart)." }); return; }
      send(res, 200, { id:job.id, conversation_id:job.conversation_id, status:job.status, answer:job.answer, error:job.error, events:job.events.slice(-80), activities:job.activities.slice(-30), updated_at:job.updated_at }); return;
    }
    send(res, 404, { error:"Not found" });
  } catch (err) { send(res, 400, { error:err.message || "Bad request" }); }
});
server.listen(PORT, "0.0.0.0", () => process.stdout.write("HomeLabPilot Codex gateway listening on " + PORT + "\n"));
