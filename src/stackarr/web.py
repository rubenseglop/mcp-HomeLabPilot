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
  <section class="section">
    <div class="sectionhead">Media management</div>
    <div class="actions" style="flex-wrap:wrap;margin-bottom:14px">
      <button data-view="movies">Movies · Radarr</button><button data-view="series">Series · Sonarr</button>
      <button data-view="radarr-queue">Radarr queue</button><button data-view="sonarr-queue">Sonarr queue</button>
      <button data-view="downloads">Downloads · qBittorrent</button>
      <button data-view="search-movies">Search movies</button><button data-view="search-series">Search series</button><button data-view="settings">Settings</button>
    </div>
    <div class="info" id="workspace"><strong>Select a section</strong><br>Browse your library, inspect import queues and manage active downloads.</div>
  </section>
  <div class="foot">StackARR · Web dashboard and MCP endpoint in one application</div>
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

 if(view==='settings'){
   html='<h3>Configuration</h3><p class="muted">Edit existing Radarr/Sonarr profiles, indexers and download clients, or selected qBittorrent preferences. Review each JSON object before saving.</p><div class="actions" style="flex-wrap:wrap;margin:12px 0"><select id="settings-service" style="background:#0e1728;color:#e8edf5;padding:9px;border:1px solid #34435d;border-radius:8px"><option value="radarr">Radarr</option><option value="sonarr">Sonarr</option><option value="qbittorrent">qBittorrent</option></select><select id="settings-resource" style="background:#0e1728;color:#e8edf5;padding:9px;border:1px solid #34435d;border-radius:8px"><option value="qualityprofile">Quality profiles</option><option value="delayprofile">Delay profiles</option><option value="indexer">Indexers</option><option value="downloadclient">Download clients</option><option value="notification">Notifications</option></select><button id="load-settings">Load settings</button></div><div id="settings-records" class="muted">Choose an application and load its configuration.</div>';
   target.innerHTML=html;
   const svc=$('settings-service'),res=$('settings-resource'),records=$('settings-records');
   const updateResource=()=>{res.disabled=svc.value==='qbittorrent';};
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
 if(view==='movies'||view==='series'){const service=view==='movies'?'radarr':'sonarr';data=await request('/web-api/library?service='+service);const rows=(data||[]).map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.title||x.titleSlug)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.year||x.yearStart)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+(x.monitored?'Yes':'No')+'</td></tr>');html='<h3>'+ (view==='movies'?'Movies':'Series') +' <span class="muted">('+rows.length+')</span></h3>'+table(['Title','Year','Status','Monitored'],rows);}
 else if(view==='radarr-queue'||view==='sonarr-queue'){const service=view==='radarr-queue'?'radarr':'sonarr';data=await request('/web-api/queue?service='+service);const records=data.records||[];const rows=records.map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.title)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.trackedDownloadStatus)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.errorMessage)+'</td></tr>');html='<h3>'+service+' queue <span class="muted">('+records.length+')</span></h3>'+table(['Title','Status','Import state','Message'],rows);}
 else if(view==='downloads'){data=await request('/web-api/torrents');const rows=(data||[]).map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.name)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.state)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.progress===undefined?'—':Math.round(x.progress*100)+'%')+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.category)+'</td><td style="padding:10px;border-bottom:1px solid #25344d"><button data-torrent-action="pause" data-hash="'+esc(x.hash)+'">Pause</button> <button data-torrent-action="resume" data-hash="'+esc(x.hash)+'">Resume</button></td></tr>');html='<h3>Active downloads <span class="muted">('+rows.length+')</span></h3>'+table(['Name','State','Progress','Category','Controls'],rows);}
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
$('workspace').addEventListener('click',async e=>{const add=e.target.closest('[data-add-title]');if(add){const card=add.closest('.card');const service=add.dataset.service,id=Number(add.dataset.id);if(!confirm('Add this title to '+service+'?'))return;add.disabled=true;try{const body={service,root_folder_path:card.querySelector('[data-root]').value,quality_profile_id:Number(card.querySelector('[data-profile]').value),monitored:true,search_now:card.querySelector('[data-search-now]').checked};body[service==='radarr'?'tmdb_id':'tvdb_id']=id;await request('/web-api/catalog/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});add.textContent='Added';}catch(err){alert(err.message);add.disabled=false;}return;}const b=e.target.closest('[data-torrent-action]');if(!b)return;const action=b.dataset.torrentAction;const verb=action==='pause'?'pause':'resume';if(!confirm('Are you sure you want to '+verb+' this torrent?'))return;b.disabled=true;try{await request('/web-api/torrents/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,hashes:b.dataset.hash})});await openView('downloads');}catch(err){alert(err.message);b.disabled=false;}});
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
    ):
        self.app = app
        self.token = token
        self.status_callback = status_callback
        self.api_callback = api_callback

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
