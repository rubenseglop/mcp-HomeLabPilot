"""Small built-in web dashboard for StackARR.

The dashboard is served by the same process as the MCP endpoint. It uses a
separate HttpOnly browser session cookie; the MCP endpoint continues to require
its Bearer token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
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
  <p>Sign in with your StackARR dashboard account. Your browser session is stored in an HttpOnly cookie.</p>
  <form id="login-form"><input id="username" autocomplete="username" placeholder="Username" required><input id="password" type="password" autocomplete="current-password" placeholder="Password" required><button>Sign in</button></form>
  <div id="login-error" class="error"></div>
</div>
<main id="app" class="shell hidden">
  <header>
    <div class="brand"><div class="logo">S</div><div><h1>StackARR</h1><div class="sub">Media stack control center</div></div></div>
    <div class="actions"><button id="refresh">Refresh</button><button id="logout">Sign out</button></div>
  </header>
  <div class="hero"><div><h2>Overview</h2><div class="muted">Live connectivity of your configured services</div></div><div class="summary"><span class="pill" id="healthy">Checking…</span><span class="pill" id="updated">Not updated yet</span></div></div>
  <div class="grid" id="services"></div>
  <section class="section">
    <div class="sectionhead">Media management</div>
    <div class="actions" style="flex-wrap:wrap;margin-bottom:14px">
      <button data-view="movies">Movies · Radarr</button><button data-view="series">Series · Sonarr</button>
      <button data-view="radarr-queue">Radarr queue</button><button data-view="sonarr-queue">Sonarr queue</button>
      <button data-view="downloads">Downloads · qBittorrent</button>
      <button data-view="search-movies">Search movies</button><button data-view="search-series">Search series</button><button data-view="scryer">Scryer</button><button data-view="settings">Settings</button><button data-view="api-explorer">Advanced API</button>
    </div>
    <div class="info" id="workspace"><strong>Select a section</strong><br>Browse your library, inspect import queues and manage active downloads.</div>
  </section>
  <div class="foot">StackARR · Web dashboard and MCP endpoint in one application</div>
</main>
<script>
const $=id=>document.getElementById(id);
function showLogin(){ $('login').classList.remove('hidden');$('app').classList.add('hidden'); }
function showApp(){ $('login').classList.add('hidden');$('app').classList.remove('hidden'); }
async function request(path,options={}){const r=await fetch(path,{credentials:'same-origin',...options});if(r.status===401)throw new Error('unauthorized');const type=r.headers.get('content-type')||'';let data=null;try{data=type.includes('application/json')?await r.json():await r.text();}catch(_){data=null;}if(!r.ok){const detail=data&&typeof data==='object'?(data.error||data.detail||data.message):data;throw new Error(detail?String(detail):'Request failed ('+r.status+')');}return data;}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function render(data){
 const entries=Object.entries(data.services||{});const good=entries.filter(([,v])=>v.ok).length;
 $('healthy').textContent=good+' / '+entries.length+' services online';
 $('updated').textContent='Updated '+new Date().toLocaleTimeString();
 $('services').innerHTML=entries.map(([name,v])=>'<article class="card"><div class="cardtop"><div class="name">'+esc(name[0].toUpperCase()+name.slice(1))+'</div><span class="status '+(v.ok?'ok':'bad')+'">'+(v.ok?'Online':'Attention')+'</span></div><div class="version">'+(v.version?'Version '+esc(v.version):v.app_name?esc(v.app_name):v.ok?'Connected':'Not connected')+'</div>'+(v.error?'<div class="error">'+esc(v.error)+'</div>':'')+'</article>').join('');
}
async function refresh(){ $('refresh').disabled=true;$('refresh').textContent='Loading…';try{render(await request('/web-api/status'));}catch(e){if(e.message==='unauthorized')showLogin();else $('healthy').textContent=e.message;}finally{$('refresh').disabled=false;$('refresh').textContent='Refresh';}}
$('login-form').addEventListener('submit',async e=>{e.preventDefault();$('login-error').textContent='';try{await request('/web-login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('username').value,password:$('password').value})});$('password').value='';showApp();await refresh();}catch(e){$('login-error').textContent='Login failed. Check your username and password.';}});
$('refresh').addEventListener('click',refresh);
$('logout').addEventListener('click',async()=>{await fetch('/web-logout',{method:'POST',credentials:'same-origin'});showLogin();});
function cell(v){return esc(v===null||v===undefined?'—':v);}
function fieldLabel(key){return String(key).replace(/([a-z0-9])([A-Z])/g,'$1 $2').replace(/[_-]+/g,' ').replace(/^./,c=>c.toUpperCase());}
function configFields(value,path=[]){
 if(!value||typeof value!=='object'||Array.isArray(value))return '';
 return Object.entries(value).map(([key,v])=>{
  if(/password|apikey|api_key|token|secret|credential/i.test(key))return '';
  const p=esc(JSON.stringify([...path,key])),label=esc(fieldLabel(key));
  const style='width:100%;background:#0b1322;color:#e8edf5;border:1px solid #34435d;border-radius:8px;padding:9px;margin-top:5px';
  if(typeof v==='boolean')return '<label style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #25344d"><input data-config-path="'+p+'" type="checkbox" '+(v?'checked':'')+' style="width:auto;margin:0"><span>'+label+'</span></label>';
  if(typeof v==='number')return '<label style="display:block;padding:7px 0"><span class="muted">'+label+'</span><input data-config-path="'+p+'" type="number" step="any" value="'+esc(v)+'" style="'+style+'"></label>';
  if(typeof v==='string')return '<label style="display:block;padding:7px 0"><span class="muted">'+label+'</span><input data-config-path="'+p+'" type="text" value="'+esc(v)+'" style="'+style+'"></label>';
  if(Array.isArray(v))return '<label style="display:block;padding:7px 0"><span class="muted">'+label+' · list / advanced values (JSON)</span><textarea data-config-path="'+p+'" rows="5" style="'+style+';font:12px ui-monospace,monospace">'+esc(JSON.stringify(v,null,2))+'</textarea></label>';
  if(v&&typeof v==='object')return '<details open style="margin:8px 0 8px 12px;padding:8px 12px;border-left:2px solid #34435d"><summary style="cursor:pointer;color:#b8c5d8">'+label+'</summary>'+configFields(v,[...path,key])+'</details>';
  return '<label style="display:block;padding:7px 0"><span class="muted">'+label+'</span><input data-config-path="'+p+'" type="text" value="'+esc(v??'')+'" style="'+style+'"></label>';
 }).join('');
}
function setConfigPath(object,path,value){let target=object;for(let i=0;i<path.length-1;i++){if(!target[path[i]]||typeof target[path[i]]!=='object')target[path[i]]={};target=target[path[i]];}target[path[path.length-1]]=value;}
function table(headers,rows){return '<div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr>'+headers.map(h=>'<th style="text-align:left;padding:10px;border-bottom:1px solid #34435d;color:#91a0b8">'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.join('')+'</tbody></table></div>';}
async function openView(view){const target=$('workspace');target.textContent='Loading…';try{
 let data,html='';

 if(view==='scryer'){
   html='<h3>Scryer · Control center</h3><p class="muted">Live status and a schema-driven view of the GraphQL API. The available fields are read from your installed Scryer version; no operation names are assumed.</p><div class="grid" id="scryer-summary" style="margin:12px 0"><article class="card"><div class="muted">Connection</div><div class="name" id="scryer-connection">Checking…</div></article><article class="card"><div class="muted">GraphQL queries</div><div class="name" id="scryer-query-count">—</div></article><article class="card"><div class="muted">GraphQL mutations</div><div class="name" id="scryer-mutation-count">—</div></article></div><div class="actions" style="flex-wrap:wrap;margin:12px 0"><button id="scryer-refresh">Refresh schema</button><input id="scryer-filter" placeholder="Filter operations…" style="max-width:280px;margin:0"></div><div id="scryer-schema" class="info">Loading Scryer schema…</div><details class="card" open style="margin-top:14px"><summary style="cursor:pointer;font-weight:650">GraphQL console</summary><div style="margin-top:12px"><label class="muted">GraphQL operation</label><textarea id="scryer-query" rows="7" spellcheck="false" placeholder="Write a query using an operation shown in the schema above." style="width:100%;background:#0b1322;color:#dce7f8;border:1px solid #34435d;border-radius:9px;padding:12px;font:13px ui-monospace,monospace"></textarea><label class="muted">Variables · JSON object (optional)</label><textarea id="scryer-variables" rows="3" spellcheck="false" style="width:100%;background:#0b1322;color:#dce7f8;border:1px solid #34435d;border-radius:9px;padding:12px;font:12px ui-monospace,monospace">{}</textarea><div class="actions" style="margin-top:10px"><button id="scryer-run">Execute query</button></div><pre id="scryer-result" class="info" style="white-space:pre-wrap;overflow-wrap:anywhere;margin-top:12px">Ready.</pre></div></details>';
   target.innerHTML=html;
   const typeName=t=>{if(!t)return 'Unknown';if(t.name)return t.name;return (t.kind==='NON_NULL'?'':'')+(typeName(t.ofType)||'Unknown')+(t.kind==='NON_NULL'?'!':t.kind==='LIST'?'[]':'');};
   const schemaBox=$('scryer-schema');
   let schemaData=null;
   const renderSchema=()=>{
    if(!schemaData)return;
    const filter=$('scryer-filter').value.trim().toLowerCase();
    const groups=[['Queries',schemaData.queryType],['Mutations',schemaData.mutationType]];
    schemaBox.innerHTML=groups.map(([label,root])=>{
     const fields=root?.fields||[];
     const filtered=fields.filter(f=>(f.name+' '+(f.description||'')+' '+(f.args||[]).map(a=>a.name).join(' ')).toLowerCase().includes(filter));
     return '<section style="margin:8px 0 18px"><div class="cardtop"><strong>'+label+'</strong><span class="pill">'+filtered.length+' / '+fields.length+'</span></div>'+(filtered.length?filtered.map(f=>{
      const args=(f.args||[]).map(a=>'<div class="muted" style="margin:4px 0 0 12px"><code>'+esc(a.name)+'</code>: '+esc(typeName(a.type))+(a.defaultValue!==null&&a.defaultValue!==undefined?' · default '+esc(a.defaultValue):'')+'</div>').join('');
      return '<details style="padding:10px 0;border-bottom:1px solid #293750"><summary style="cursor:pointer"><strong>'+esc(f.name)+'</strong> <span class="muted">→ '+esc(typeName(f.type))+'</span></summary>'+(f.description?'<p class="muted">'+esc(f.description)+'</p>':'')+(args||'<p class="muted">No arguments</p>')+'</details>';
     }).join(''):'<p class="muted">No matching operations.</p>')+'</section>';
    }).join('');
   };
   async function loadScryerSchema(){
    $('scryer-refresh').disabled=true;$('scryer-connection').textContent='Connecting…';schemaBox.textContent='Reading GraphQL schema…';
    const introspection='query StackARRSchema { __schema { queryType { name fields(includeDeprecated:true) { name description args { name description defaultValue type { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } } type { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } } } mutationType { name fields(includeDeprecated:true) { name description args { name description defaultValue type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } } } }';
    try{
     const result=await request('/web-api/scryer/graphql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:introspection})});
     if(result.errors?.length)throw new Error(result.errors.map(x=>x.message).join('; '));
     schemaData=result.data?.__schema;
     if(!schemaData)throw new Error('Scryer did not return a GraphQL schema.');
     $('scryer-connection').textContent='Connected';
     $('scryer-query-count').textContent=(schemaData.queryType?.fields||[]).length;
     $('scryer-mutation-count').textContent=(schemaData.mutationType?.fields||[]).length;
     renderSchema();
    }catch(err){$('scryer-connection').textContent='Unavailable';schemaBox.innerHTML='<div class="error">'+esc(err.message)+'</div>';}
    finally{$('scryer-refresh').disabled=false;}
   }
   $('scryer-filter').addEventListener('input',renderSchema);
   $('scryer-refresh').addEventListener('click',loadScryerSchema);
   $('scryer-run').addEventListener('click',async()=>{
    const out=$('scryer-result');out.textContent='Executing…';
    try{
     const variables=JSON.parse($('scryer-variables').value||'{}');
     if(!variables||typeof variables!=='object'||Array.isArray(variables))throw new Error('Variables must be a JSON object');
     const queryText=$('scryer-query').value;
     if(!queryText.trim())throw new Error('GraphQL operation cannot be empty');
     const result=await request('/web-api/scryer/graphql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:queryText,variables})});
     out.textContent=JSON.stringify(result,null,2);
    }catch(err){out.textContent='Error: '+err.message;}
   });
   await loadScryerSchema();
   return;
 }
 if(view==='api-explorer'){
   html='<h3>Advanced API explorer</h3><p class="muted">Access the native REST APIs of Radarr, Sonarr, Prowlarr and Bazarr. This exposes endpoints that do not yet have dedicated forms. API keys remain server-side. Permission checks are enforced by StackARR for every request.</p><div class="card" style="margin:12px 0"><div class="grid"><label><span class="muted">Service</span><select id="api-service" style="width:100%;background:#0e1728;color:#e8edf5;padding:10px;border:1px solid #34435d;border-radius:8px"><option value="radarr">Radarr</option><option value="sonarr">Sonarr</option><option value="prowlarr">Prowlarr</option><option value="bazarr">Bazarr</option></select></label><label><span class="muted">HTTP method</span><select id="api-method" style="width:100%;background:#0e1728;color:#e8edf5;padding:10px;border:1px solid #34435d;border-radius:8px"><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></label></div><label style="display:block;margin-top:12px"><span class="muted">API path</span><input id="api-path" value="/api/v3/system/status" spellcheck="false" style="width:100%;background:#0b1322;color:#e8edf5;border:1px solid #34435d;border-radius:8px;padding:10px"></label><label style="display:block;margin-top:12px"><span class="muted">Query parameters · JSON object (optional)</span><textarea id="api-params" rows="3" spellcheck="false" style="width:100%;background:#0b1322;color:#dce7f8;border:1px solid #34435d;border-radius:9px;padding:10px;font:12px ui-monospace,monospace">{}</textarea></label><label style="display:block;margin-top:12px"><span class="muted">Request body · JSON (optional)</span><textarea id="api-body" rows="7" spellcheck="false" style="width:100%;background:#0b1322;color:#dce7f8;border:1px solid #34435d;border-radius:9px;padding:10px;font:12px ui-monospace,monospace">{}</textarea></label><div class="actions" style="margin-top:12px"><button id="api-run">Send request</button><button id="api-clear">Clear response</button></div><pre id="api-result" class="info" style="white-space:pre-wrap;overflow-wrap:anywhere;margin-top:12px">Ready.</pre></div><p class="muted">Examples: Radarr/Sonarr <code>/api/v3/movie</code>, Prowlarr <code>/api/v1/indexer</code>, Bazarr <code>/api/system/status</code>. GET requests require read access; normal writes require operations; configuration, system and destructive operations require admin. Check the target application API documentation before changing unfamiliar endpoints.</p>';
   target.innerHTML=html;
   $('api-service').addEventListener('change',()=>{
    const service=$('api-service').value;
    $('api-path').value=service==='prowlarr'?'/api/v1/system/status':service==='bazarr'?'/api/system/status':'/api/v3/system/status';
   });
   $('api-clear').addEventListener('click',()=>{$('api-result').textContent='Ready.';});
   $('api-run').addEventListener('click',async()=>{
    const out=$('api-result'),button=$('api-run');out.textContent='Sending request…';button.disabled=true;
    try{
     const params=JSON.parse($('api-params').value||'{}');
     if(!params||typeof params!=='object'||Array.isArray(params))throw new Error('Query parameters must be a JSON object.');
     const method=$('api-method').value,rawBody=$('api-body').value.trim();
     const body=rawBody?JSON.parse(rawBody):null;
     const path=$('api-path').value.trim();
     if(!path.startsWith('/')||path.startsWith('//')||path.includes('://')||path.includes('\\'))throw new Error('Enter a safe API path beginning with one /.');
     const result=await request('/web-api/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service:$('api-service').value,method,path,params,body})});
     out.textContent=JSON.stringify(result,null,2);
    }catch(err){out.textContent='Error: '+err.message;}
    finally{button.disabled=false;}
   });
   return;
 }
 if(view==='settings'){
   html='<h3>Configuration</h3><p class="muted">Edit Radarr/Sonarr profiles and integrations, Prowlarr indexers and download clients, or selected qBittorrent preferences. Review each JSON object before saving.</p><div class="actions" style="flex-wrap:wrap;margin:12px 0"><select id="settings-service" style="background:#0e1728;color:#e8edf5;padding:9px;border:1px solid #34435d;border-radius:8px"><option value="radarr">Radarr</option><option value="sonarr">Sonarr</option><option value="prowlarr">Prowlarr</option><option value="qbittorrent">qBittorrent</option></select><select id="settings-resource" style="background:#0e1728;color:#e8edf5;padding:9px;border:1px solid #34435d;border-radius:8px"><option value="qualityprofile">Quality profiles</option><option value="delayprofile">Delay profiles</option><option value="indexer">Indexers</option><option value="downloadclient">Download clients</option><option value="notification">Notifications</option><option value="qualitydefinition">Quality definitions</option><option value="customformat">Custom formats</option><option value="importlist">Import lists</option><option value="metadata">Metadata</option><option value="tag">Tags</option><option value="languageprofile">Language profiles (Sonarr)</option><option value="releaseprofile">Release profiles (Sonarr)</option></select><button id="load-settings">Load settings</button></div><div id="settings-records" class="muted">Choose an application and load its configuration.</div>';
   target.innerHTML=html;
   const svc=$('settings-service'),res=$('settings-resource'),records=$('settings-records');
   const updateResource=()=>{
    const service=svc.value;
    res.disabled=service==='qbittorrent';
    const prowlarrResources=new Set(['indexer','downloadclient','notification']);
    const radarrOnlyExcluded=new Set(['languageprofile','releaseprofile']);
    Array.from(res.options).forEach(option=>{
     option.disabled=(service==='prowlarr'&&!prowlarrResources.has(option.value))||(service==='radarr'&&radarrOnlyExcluded.has(option.value));
    });
    if(service==='prowlarr'&&!prowlarrResources.has(res.value))res.value='indexer';
    if(service==='radarr'&&radarrOnlyExcluded.has(res.value))res.value='qualityprofile';
   };
   svc.addEventListener('change',updateResource);updateResource();
   $('load-settings').addEventListener('click',async()=>{
    records.textContent='Loading configuration…';
    try{
     const service=svc.value,resource=res.value;
     const data=await request('/web-api/settings?service='+service+'&resource='+resource);
     if(service==='qbittorrent'){
      const labels={save_path:'Default save path',temp_path:'Temporary files path',temp_path_enabled:'Use a separate path for incomplete torrents',scan_dirs:'Watched folders',max_active_downloads:'Maximum active downloads',max_active_uploads:'Maximum active uploads',max_active_torrents:'Maximum active torrents',max_connections:'Global maximum connections',max_connections_per_torrent:'Maximum connections per torrent',max_uploads:'Global maximum upload slots',max_uploads_per_torrent:'Upload slots per torrent',dl_limit:'Download limit (bytes/s)',up_limit:'Upload limit (bytes/s)',alt_speed_enabled:'Alternative speed limits enabled'};
      const numeric=new Set(['max_active_downloads','max_active_uploads','max_active_torrents','max_connections','max_connections_per_torrent','max_uploads','max_uploads_per_torrent','dl_limit','up_limit']);
      const fields=Object.entries(data||{}).map(([key,value])=>{
       const title=labels[key]||key;
       if(typeof value==='boolean')return '<label style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #25344d"><input data-qbit-key="'+esc(key)+'" type="checkbox" '+(value?'checked':'')+' style="width:auto;margin:0"><span>'+esc(title)+'</span></label>';
       if(numeric.has(key))return '<label style="display:block;padding:9px 0;border-bottom:1px solid #25344d"><span class="muted">'+esc(title)+'</span><input data-qbit-key="'+esc(key)+'" type="number" min="0" step="1" value="'+esc(value)+'" style="width:100%;background:#0b1322;color:#e8edf5;border:1px solid #34435d;border-radius:8px;padding:10px;margin-top:5px"></label>';
       if(key==='scan_dirs')return '<label style="display:block;padding:9px 0"><span class="muted">'+esc(title)+' (JSON)</span><textarea data-qbit-key="'+esc(key)+'" rows="5" style="width:100%;background:#0b1322;color:#dce7f8;border:1px solid #34435d;border-radius:9px;padding:10px;font:12px ui-monospace,monospace">'+esc(JSON.stringify(value,null,2))+'</textarea></label>';
       return '<label style="display:block;padding:9px 0"><span class="muted">'+esc(title)+'</span><input data-qbit-key="'+esc(key)+'" type="text" value="'+esc(value)+'" style="width:100%;background:#0b1322;color:#e8edf5;border:1px solid #34435d;border-radius:8px;padding:10px;margin-top:5px"></label>';
      }).join('');
      records.innerHTML='<div class="card"><div class="name">qBittorrent preferences</div><p class="muted">Formulario visual para rutas, límites y colas. Los límites de velocidad se expresan en bytes por segundo. Las credenciales y opciones de seguridad web no se muestran.</p>'+fields+'<div class="actions" style="margin-top:14px"><button id="save-qbit-settings">Save preferences</button><button id="reload-qbit-settings">Discard changes</button></div><div id="qbit-save-status" class="muted" style="margin-top:10px"></div></div>';
      $('reload-qbit-settings').addEventListener('click',()=> $('load-settings').click());
      $('save-qbit-settings').addEventListener('click',async()=>{
       try{
        const preferences={};
        records.querySelectorAll('[data-qbit-key]').forEach(input=>{
         const key=input.dataset.qbitKey;
         if(input.type==='checkbox')preferences[key]=input.checked;
         else if(input.type==='number'){const value=Number(input.value);if(!Number.isFinite(value)||value<0)throw new Error('Enter a valid non-negative number for '+(labels[key]||key));preferences[key]=value;}
         else if(key==='scan_dirs'){try{preferences[key]=JSON.parse(input.value);}catch(_){throw new Error('Watched folders must contain valid JSON.');}}
         else preferences[key]=input.value;
        });
        if(!confirm('Apply these qBittorrent preferences?'))return;
        $('save-qbit-settings').disabled=true;
        await request('/web-api/settings/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service:'qbittorrent',preferences})});
        $('qbit-save-status').textContent='Preferences saved. Reload to verify the values.';
       }catch(err){$('qbit-save-status').textContent='Could not save: '+err.message;}
       finally{$('save-qbit-settings').disabled=false;}
      });
      return;
     }
     const items=Array.isArray(data)?data:[];
     if(!items.length){records.textContent='No configuration records found.';return;}
     records.innerHTML=items.map((item,i)=>'<details class="card" style="margin:10px 0"><summary style="cursor:pointer"><strong>'+esc(item.name||item.host||item.path||resource+' #'+(item.id??i))+'</strong> <span class="muted">ID '+esc(item.id??'—')+'</span></summary><div data-config-form="'+i+'" style="margin-top:12px">'+configFields(item)+'</div><div class="actions" style="margin-top:10px"><button data-save-config='+i+'" data-id="'+esc(item.id)+'">Save changes</button></div></details>').join('');
     records.querySelectorAll('[data-save-config]').forEach(button=>button.addEventListener('click',async()=>{
      try{
       const index=Number(button.dataset.saveConfig),item=JSON.parse(JSON.stringify(items[index]));
       records.querySelectorAll('[data-config-form="'+index+'"] [data-config-path]').forEach(input=>{
        const path=JSON.parse(input.dataset.configPath);let value;
        if(input.type==='checkbox')value=input.checked;
        else if(input.type==='number'){value=Number(input.value);if(!Number.isFinite(value))throw new Error('Invalid number in '+fieldLabel(path[path.length-1]));}
        else if(input.tagName==='TEXTAREA'){try{value=JSON.parse(input.value);}catch(_){throw new Error('Invalid JSON in '+fieldLabel(path[path.length-1]));}}
        else value=input.value;
        setConfigPath(item,path,value);
       });
       if(!confirm('Save changes to '+(item.name||resource+' #'+button.dataset.id)+'?'))return;
       button.disabled=true;
       await request('/web-api/settings/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service,resource,id:Number(button.dataset.id),item})});
       button.textContent='Saved';button.disabled=false;
      }catch(err){alert('Could not save: '+err.message);button.disabled=false;}
     }));
    }catch(err){records.innerHTML='<div class="error">'+esc(err.message)+'</div>';}
   });
   return;
 }
 if(view==='search-movies'||view==='search-series'){
   const service=view==='search-movies'?'radarr':'sonarr';
   html='<h3>Search '+(service==='radarr'?'movies':'series')+'</h3><form id="catalog-search" class="actions" style="flex-wrap:wrap"><input id="catalog-term" placeholder="Enter a title…" required style="min-width:240px;flex:1;background:#0e1728;border:1px solid #34435d;border-radius:9px;padding:10px;color:#e8edf5"><button>Search</button></form><div id="catalog-results" style="margin-top:14px" class="muted">Search the metadata catalogue to add a title.</div>';
   target.innerHTML=html;target.dataset.catalogService=service;return;
 }
 if(view==='movies'||view==='series'){
 const service=view==='movies'?'radarr':'sonarr';
 const [library,setup]=await Promise.all([
  request('/web-api/library?service='+service),
  request('/web-api/setup?service='+service)
 ]);
 const profiles=setup.quality_profiles||[];
 const rows=(library||[]).map(x=>{
  const options=profiles.map(p=>'<option value="'+esc(p.id)+'"'+(Number(p.id)===Number(x.qualityProfileId)?' selected':'')+'>'+esc(p.name)+'</option>').join('');
  return '<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.title||x.titleSlug)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.year||x.yearStart)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d"><input type="checkbox" data-library-monitored style="width:auto;margin:0" '+(x.monitored?'checked':'')+'></td><td style="padding:10px;border-bottom:1px solid #25344d"><select data-library-profile style="max-width:190px;background:#0e1728;color:#e8edf5;padding:7px;border:1px solid #34435d;border-radius:8px">'+options+'</select></td><td style="padding:10px;border-bottom:1px solid #25344d"><button data-library-save data-service="'+service+'" data-id="'+esc(x.id)+'">Save</button> <button data-library-releases data-service="'+service+'" data-id="'+esc(x.id)+'">Search releases</button></td></tr>';
 });
 html='<h3>'+ (view==='movies'?'Movies':'Series') +' <span class="muted">('+((library||[]).length)+')</span></h3><p class="muted">Change monitoring and quality profile per title, or search and grab a release.</p>'+table(['Title','Year','Status','Monitored','Quality profile','Actions'],rows)+'<div id="release-results" style="margin-top:16px"></div>';
}
 else if(view==='radarr-queue'||view==='sonarr-queue'){const service=view==='radarr-queue'?'radarr':'sonarr';data=await request('/web-api/queue?service='+service);const records=data.records||[];const rows=records.map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.title)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.trackedDownloadStatus)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.errorMessage)+'</td></tr>');html='<h3>'+service+' queue <span class="muted">('+records.length+')</span></h3>'+table(['Title','Status','Import state','Message'],rows);}
 else if(view==='downloads'){data=await request('/web-api/torrents');const rows=(data||[]).map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.name)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.state)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.progress===undefined?'—':Math.round(x.progress*100)+'%')+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.category)+'</td><td style="padding:10px;border-bottom:1px solid #25344d"><input data-torrent-category value="'+esc(x.category||'')+'" aria-label="Torrent category" style="width:110px;margin:0;padding:6px"><button data-torrent-set-category data-hash="'+esc(x.hash)+'">Set</button></td><td style="padding:10px;border-bottom:1px solid #25344d"><button data-torrent-action="pause" data-hash="'+esc(x.hash)+'">Pause</button> <button data-torrent-action="resume" data-hash="'+esc(x.hash)+'">Resume</button> <button data-torrent-delete data-hash="'+esc(x.hash)+'">Remove</button></td></tr>');html='<h3>Active downloads <span class="muted">('+rows.length+')</span></h3><p class="muted">Remove deletes the torrent from qBittorrent but keeps downloaded files.</p>'+table(['Name','State','Progress','Category','Set category','Controls'],rows);}
 target.innerHTML=html||'<div class="muted">No records found.</div>';
 }catch(e){target.innerHTML='<div class="error">'+esc(e.message)+'</div>';}}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>openView(b.dataset.view)));
$('workspace').addEventListener('submit',async e=>{
 if(e.target.id!=='catalog-search')return;e.preventDefault();
 const service=$('workspace').dataset.catalogService,term=$('catalog-term').value.trim(),out=$('catalog-results');
 if(!term)return;out.textContent='Searching catalogue…';
 try{
  const [items,setup]=await Promise.all([
   request('/web-api/catalog?service='+service+'&term='+encodeURIComponent(term)),
   request('/web-api/setup?service='+service)
  ]);
  if(!Array.isArray(items)||!items.length){out.textContent='No matches found.';return;}
  const roots=setup.root_folders||[],profiles=setup.quality_profiles||[];
  if(!roots.length||!profiles.length){out.innerHTML='<div class="error">Configure at least one root folder and quality profile in '+esc(service)+'.</div>';return;}
  out.innerHTML=items.map(item=>{
   const id=service==='radarr'?item.tmdbId:item.tvdbId;
   const name=esc(item.title||item.titleSlug||'Untitled'),year=esc(item.year||item.yearStart||'');
   const rootOptions=roots.map(x=>'<option value="'+esc(x.path)+'">'+esc(x.path)+'</option>').join('');
   const profileOptions=profiles.map(x=>'<option value="'+esc(x.id)+'">'+esc(x.name)+'</option>').join('');
   return '<article class="card" style="margin:10px 0"><div class="cardtop"><div class="name">'+name+' <span class="muted">'+year+'</span></div><span class="muted">'+(id?'ID '+esc(id):'No external ID')+'</span></div><div class="version">'+esc(item.overview||'')+'</div>'+(id?'<div class="actions" style="flex-wrap:wrap;margin-top:12px"><select data-root style="max-width:250px;background:#0e1728;color:#e8edf5;padding:8px;border:1px solid #34435d;border-radius:8px">'+rootOptions+'</select><select data-profile style="max-width:220px;background:#0e1728;color:#e8edf5;padding:8px;border:1px solid #34435d;border-radius:8px">'+profileOptions+'</select><label class="muted"><input type="checkbox" data-search-now> Search immediately</label><button data-add-title data-service="'+service+'" data-id="'+esc(id)+'">Add to '+service+'</button></div>':'')+'</article>';
  }).join('');
 }catch(err){out.innerHTML='<div class="error">'+esc(err.message)+'</div>';}
});
$('workspace').addEventListener('click',async e=>{const add=e.target.closest('[data-add-title]');if(add){const card=add.closest('.card');const service=add.dataset.service,id=Number(add.dataset.id);if(!confirm('Add this title to '+service+'?'))return;add.disabled=true;try{const body={service,root_folder_path:card.querySelector('[data-root]').value,quality_profile_id:Number(card.querySelector('[data-profile]').value),monitored:true,search_now:card.querySelector('[data-search-now]').checked};body[service==='radarr'?'tmdb_id':'tvdb_id']=id;await request('/web-api/catalog/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});add.textContent='Added';}catch(err){alert(err.message);add.disabled=false;}return;}const category=e.target.closest('[data-torrent-set-category]');if(category){const row=category.closest('tr'),value=row.querySelector('[data-torrent-category]').value.trim();if(!value){alert('Enter a category name.');return;}category.disabled=true;try{await request('/web-api/torrents/category',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hashes:category.dataset.hash,category:value})});category.textContent='Saved';}catch(err){alert(err.message);category.disabled=false;}return;}const remove=e.target.closest('[data-torrent-delete]');if(remove){if(!confirm('Remove this torrent from qBittorrent? Downloaded files will be kept.'))return;remove.disabled=true;try{await request('/web-api/torrents/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hashes:remove.dataset.hash,delete_files:false})});await openView('downloads');}catch(err){alert(err.message);remove.disabled=false;}return;}const b=e.target.closest('[data-torrent-action]');if(!b)return;const action=b.dataset.torrentAction;const verb=action==='pause'?'pause':'resume';if(!confirm('Are you sure you want to '+verb+' this torrent?'))return;b.disabled=true;try{await request('/web-api/torrents/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,hashes:b.dataset.hash})});await openView('downloads');}catch(err){alert(err.message);b.disabled=false;}});
$('workspace').addEventListener('click',async e=>{
 const search=e.target.closest('[data-library-releases]');
 if(search){
  const out=$('release-results');
  out.innerHTML='<div class="muted">Searching releases…</div>';
  search.disabled=true;
  try{
   const releases=await request('/web-api/releases?service='+search.dataset.service+'&id='+search.dataset.id);
   if(!Array.isArray(releases)||!releases.length){out.innerHTML='<div class="muted">No releases found.</div>';return;}
   out.innerHTML='<h3>Available releases</h3>'+releases.map(release=>{
    const quality=release.quality?.quality?.name||release.quality?.name||'—';
    const size=Number(release.size||0);
    const sizeText=size>0?(size/1073741824).toFixed(2)+' GB':'—';
    const indexer=release.indexer||release.indexerName||'Indexer';
    return '<article class="card" style="margin:9px 0"><div class="name">'+esc(release.title||'Untitled release')+'</div><div class="muted" style="margin:7px 0">'+esc(indexer)+' · '+esc(quality)+' · '+esc(sizeText)+'</div>'+(release.rejections?.length?'<div class="error">'+esc(release.rejections.map(x=>x.reason).join('; '))+'</div>':'')+'<button data-grab-release data-service="'+esc(search.dataset.service)+'" data-guid="'+esc(release.guid||'')+'" data-indexer-id="'+esc(release.indexerId||0)+'" '+(!release.guid||!release.indexerId?'disabled':'')+'>Grab release</button></article>';
   }).join('');
  }catch(err){out.innerHTML='<div class="error">'+esc(err.message)+'</div>';}
  finally{search.disabled=false;}
  return;
 }
 const grab=e.target.closest('[data-grab-release]');
 if(grab){
  if(!confirm('Send this release to the download client?'))return;
  grab.disabled=true;
  try{
   await request('/web-api/releases/grab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service:grab.dataset.service,guid:grab.dataset.guid,indexer_id:Number(grab.dataset.indexerId)})});
   grab.textContent='Sent to download client';
  }catch(err){alert('Could not grab release: '+err.message);grab.disabled=false;}
  return;
 }
 const button=e.target.closest('[data-library-save]');
 if(!button)return;
 const row=button.closest('tr');
 const profile=row.querySelector('[data-library-profile]');
 const body={service:button.dataset.service,id:Number(button.dataset.id),monitored:row.querySelector('[data-library-monitored]').checked};
 if(profile&&profile.value)body.quality_profile_id=Number(profile.value);
 if(!confirm('Save monitoring and quality profile for this title?'))return;
 button.disabled=true;
 try{
  await request('/web-api/library/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  button.textContent='Saved';
 }catch(err){alert('Could not update title: '+err.message);button.disabled=false;}
});
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
        api_callback: Callable[[str, str, dict[str, list[str]], dict[str, Any]], Awaitable[Any]] | None = None,
        web_username: str = "admin",
        web_password: str | None = None,
    ):
        self.app = app
        self.token = token
        self.web_username = web_username
        self.web_password = web_password or token
        # Stable signing key: sessions survive container restarts without storing
        # the MCP token or requiring a server-side session database.
        self.session_signing_key = hmac.new(
            token.encode("utf-8"), b"stackarr-web-session-v1", hashlib.sha256
        ).digest()
        self.status_callback = status_callback
        self.api_callback = api_callback

    def _create_session(self) -> str:
        expires = int(time.time()) + 30 * 24 * 60 * 60
        payload = f"{expires}.{secrets.token_urlsafe(24)}"
        signature = hmac.new(
            self.session_signing_key, payload.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return base64.urlsafe_b64encode(f"{payload}.{signature}".encode("ascii")).decode("ascii").rstrip("=")

    def _verify_session(self, session: str) -> bool:
        if not session or len(session) > 512:
            return False
        try:
            padded = session + "=" * (-len(session) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
            expires_text, nonce, signature = decoded.split(".", 2)
            payload = f"{expires_text}.{nonce}"
            expected = hmac.new(
                self.session_signing_key, payload.encode("ascii"), hashlib.sha256
            ).hexdigest()
            return (
                expires_text.isdigit()
                and int(expires_text) > int(time.time())
                and hmac.compare_digest(signature, expected)
            )
        except (ValueError, UnicodeError):
            return False

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
        authenticated = self._verify_session(session)

        if path == "/" and method == "GET":
            await self._respond(send, 200, DASHBOARD.encode(), b"text/html; charset=utf-8")
            return

        if path == "/web-login" and method == "POST":
            try:
                payload = json.loads(await self._body(receive))
                supplied_user = str(payload.get("username", ""))
                supplied_password = str(payload.get("password", ""))
            except (ValueError, AttributeError):
                supplied_user = supplied_password = ""
            valid_user = hmac.compare_digest(supplied_user.encode(), self.web_username.encode())
            valid_password = hmac.compare_digest(supplied_password.encode(), self.web_password.encode())
            if not (valid_user and valid_password):
                await self._respond(send, 401, b'{"error":"Unauthorized"}')
                return
            session_id = self._create_session()
            secure = b"; Secure" if headers.get(b"x-forwarded-proto", b"").lower() == b"https" else b""
            cookie_value = b"stackarr_session=" + session_id.encode() + b"; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000" + secure
            await self._respond(send, 200, b'{"ok":true}', extra_headers=[(b"set-cookie", cookie_value)])
            return

        if path == "/web-logout" and method == "POST":
            await self._respond(send, 200, b'{"ok":true}', extra_headers=[(b"set-cookie", b"stackarr_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")])
            return

        if path.startswith("/web-api/"):
            if not authenticated:
                await self._respond(send, 401, b'{"error":"Unauthorized"}')
                return
            try:
                if path == "/web-api/status" and method == "GET":
                    result = await self.status_callback()
                elif self.api_callback is not None and method in {"GET", "POST"}:
                    query = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace"))
                    raw = await self._body(receive) if method == "POST" else b"{}"
                    payload = json.loads(raw or b"{}")
                    if not isinstance(payload, dict):
                        raise ValueError("Request body must be a JSON object")
                    result = await self.api_callback(path, method, query, payload)
                else:
                    await self._respond(send, 404, b'{"error":"Not found"}')
                    return
                await self._respond(send, 200, json.dumps(result, default=str).encode())
            except ValueError as exc:
                await self._respond(send, 400, json.dumps({"error": str(exc)}).encode())
            except Exception as exc:
                await self._respond(send, 502, json.dumps({"error": str(exc)}).encode())
            return

        await self.app(scope, receive, send)
