"""Small built-in web dashboard for StackARR.

The dashboard is served by the same process as the MCP endpoint. It uses a
separate HttpOnly browser session cookie; the MCP endpoint continues to require
its Bearer token.
"""
from __future__ import annotations

import hmac
import json
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs


DASHBOARD = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>StackARR</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#e8edf5;background:#0b1020}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse at 15% 0%,#1b2c4b 0,transparent 42%),#0b1020}
button,input{font:inherit}.shell{max-width:1120px;margin:auto;padding:32px 22px}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:30px}
.brand{display:flex;align-items:center;gap:13px}.logo{width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,#647cf6,#19b6a5);display:grid;place-items:center;font-weight:900;font-size:19px;color:white}
h1{font-size:23px;margin:0;letter-spacing:-.5px} .sub{color:#91a0b8;font-size:13px;margin-top:4px}
.actions{display:flex;gap:9px;align-items:center}button{border:1px solid #34435d;background:#18243a;color:#e8edf5;padding:9px 13px;border-radius:10px;cursor:pointer}button:hover{background:#243550}
.hero{display:flex;align-items:end;justify-content:space-between;gap:20px;margin:24px 0}
h2{font-size:20px;margin:0 0 6px}.muted{color:#91a0b8;font-size:13px}.summary{display:flex;gap:10px;flex-wrap:wrap}
.pill{border:1px solid #293750;background:#121d31;border-radius:999px;padding:7px 11px;font-size:12px;color:#b8c5d8}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:13px}
.card{border:1px solid #25344d;background:linear-gradient(145deg,#151f32,#101827);border-radius:15px;padding:17px;min-height:128px}
.cardtop{display:flex;align-items:center;justify-content:space-between;gap:10px}.name{font-weight:650;font-size:15px}
.status{font-size:11px;border-radius:999px;padding:5px 8px;background:#263246;color:#b8c5d8}
.status.ok{background:#10382f;color:#70e0bb}.status.bad{background:#44232c;color:#ff9ca8}
.version{font-size:13px;color:#a8b6cb;margin-top:13px}.error{font-size:12px;color:#ffabb3;margin-top:10px;overflow-wrap:anywhere}
.section{margin-top:30px}.sectionhead{font-size:14px;font-weight:650;margin-bottom:12px}
.info{border:1px solid #25344d;background:#111a2a;border-radius:14px;padding:17px;color:#aebbd0;font-size:13px;line-height:1.6}
#login{max-width:390px;margin:12vh auto;padding:26px;border:1px solid #2b3a53;background:#121c2e;border-radius:18px}
#login h1{margin-bottom:8px}#login p{color:#9cabc1;font-size:13px;line-height:1.5}
input{width:100%;padding:12px;border:1px solid #34435d;border-radius:10px;background:#0b1322;color:white;margin:10px 0}
#login button{width:100%;background:#536ce7;border:0;font-weight:650}.hidden{display:none!important}
.foot{margin-top:28px;color:#71819a;font-size:11px;text-align:center}
@media(max-width:600px){.shell{padding:20px 14px}header{align-items:flex-start}.hero{align-items:flex-start;flex-direction:column}.actions button{padding:8px}}
</style>
</head>
<body>
<div id="login" class="hidden">
  <div class="brand"><div class="logo">S</div><div><h1>StackARR</h1><div class="sub">Media stack control center</div></div></div>
  <p>Sign in with your StackARR access token. Your browser session is stored in an HttpOnly cookie.</p>
  <form id="login-form"><input id="password" type="password" autocomplete="current-password" placeholder="StackARR access token" required><button>Sign in</button></form>
  <div id="login-error" class="error"></div>
</div>
<main id="app" class="shell hidden">
  <header>
    <div class="brand"><div class="logo">S</div><div><h1>StackARR</h1><div class="sub">Media stack control center</div></div></div>
    <div class="actions"><button id="refresh">Refresh</button><button id="logout">Sign out</button></div>
  </header>
  <div class="hero"><div><h2>Overview</h2><div class="muted">Live connectivity of your configured services</div></div><div class="summary"><span class="pill" id="healthy">Checking…</span><span class="pill" id="updated">Not updated yet</span></div></div>
  <div class="grid" id="services"></div>
  <section class="section"><div class="sectionhead">About this dashboard</div><div class="info">This is the first built-in StackARR web view. It shares the same service configuration and API layer as the MCP server. More library, queue, release and download-management views can be added without creating a second backend.</div></section>
  <div class="foot">StackARR · Web dashboard and MCP endpoint in one application</div>
</main>
<script>
const $=id=>document.getElementById(id);
function showLogin(){ $('login').classList.remove('hidden');$('app').classList.add('hidden'); }
function showApp(){ $('login').classList.add('hidden');$('app').classList.remove('hidden'); }
async function request(path,options={}){const r=await fetch(path,{credentials:'same-origin',...options});if(r.status===401)throw new Error('unauthorized');if(!r.ok)throw new Error('Request failed ('+r.status+')');return r.json();}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function render(data){
 const entries=Object.entries(data.services||{});const good=entries.filter(([,v])=>v.ok).length;
 $('healthy').textContent=good+' / '+entries.length+' services online';
 $('updated').textContent='Updated '+new Date().toLocaleTimeString();
 $('services').innerHTML=entries.map(([name,v])=>'<article class="card"><div class="cardtop"><div class="name">'+esc(name[0].toUpperCase()+name.slice(1))+'</div><span class="status '+(v.ok?'ok':'bad')+'">'+(v.ok?'Online':'Attention')+'</span></div><div class="version">'+(v.version?'Version '+esc(v.version):v.app_name?esc(v.app_name):v.ok?'Connected':'Not connected')+'</div>'+(v.error?'<div class="error">'+esc(v.error)+'</div>':'')+'</article>').join('');
}
async function refresh(){ $('refresh').disabled=true;$('refresh').textContent='Loading…';try{render(await request('/web-api/status'));}catch(e){if(e.message==='unauthorized')showLogin();else $('healthy').textContent=e.message;}finally{$('refresh').disabled=false;$('refresh').textContent='Refresh';}}
$('login-form').addEventListener('submit',async e=>{e.preventDefault();$('login-error').textContent='';try{await request('/web-login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('password').value})});$('password').value='';showApp();await refresh();}catch(e){$('login-error').textContent='Login failed. Check the token and try again.';}});
$('refresh').addEventListener('click',refresh);
$('logout').addEventListener('click',async()=>{await fetch('/web-logout',{method:'POST',credentials:'same-origin'});showLogin();});
(async()=>{try{render(await request('/web-api/status'));showApp();}catch(e){showLogin();}})();
setInterval(()=>{if(!$('app').classList.contains('hidden'))refresh();},30000);
</script>
</body>
</html>"""


class StackARRWebMiddleware:
    """Serve the browser dashboard and its read-only status API."""

    def __init__(
        self,
        app: Any,
        token: str,
        status_callback: Callable[[], Awaitable[dict[str, Any]]],
    ):
        self.app = app
        self.token = token
        self.status_callback = status_callback

    @staticmethod
    async def _respond(send: Any, status: int, body: bytes, content_type: bytes = b"application/json", extra_headers: list[tuple[bytes, bytes]] | None = None) -> None:
        headers = [(b"content-type", content_type), (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]
        headers.extend(extra_headers or [])
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _body(receive: Any) -> bytes:
        chunks = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                return b"".join(chunks)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "/")
        method = scope.get("method", "GET").upper()
        headers = dict(scope.get("headers", []))
        cookie = headers.get(b"cookie", b"").decode("latin1")
        session = next((part.strip()[len("stackarr_session="):] for part in cookie.split(";") if part.strip().startswith("stackarr_session=")), "")
        authenticated = bool(session) and hmac.compare_digest(session, self.token)

        if path == "/" and method == "GET":
            await self._respond(send, 200, DASHBOARD.encode(), b"text/html; charset=utf-8")
            return

        if path == "/web-login" and method == "POST":
            try:
                payload = json.loads(await self._body(receive))
                supplied = str(payload.get("password", ""))
            except (ValueError, AttributeError):
                supplied = ""
            if not hmac.compare_digest(supplied, self.token):
                await self._respond(send, 401, b'{"error":"Unauthorized"}')
                return
            secure = b"; Secure" if headers.get(b"x-forwarded-proto", b"").lower() == b"https" else b""
            cookie_value = b"stackarr_session=" + self.token.encode() + b"; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200" + secure
            await self._respond(send, 200, b'{"ok":true}', extra_headers=[(b"set-cookie", cookie_value)])
            return

        if path == "/web-logout" and method == "POST":
            await self._respond(send, 200, b'{"ok":true}', extra_headers=[(b"set-cookie", b"stackarr_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")])
            return

        if path == "/web-api/status" and method == "GET":
            if not authenticated:
                await self._respond(send, 401, b'{"error":"Unauthorized"}')
                return
            try:
                result = await self.status_callback()
                await self._respond(send, 200, json.dumps(result, default=str).encode())
            except Exception as exc:
                await self._respond(send, 502, json.dumps({"error": str(exc)}).encode())
            return

        await self.app(scope, receive, send)
