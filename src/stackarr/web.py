"""Small built-in web dashboard for HomeLabPilot.

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
from urllib.parse import parse_qs, urlsplit


DASHBOARD = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>HomeLabPilot</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#e8edf5;background:#0b1020}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse at 15% 0%,#1b2c4b 0,transparent 42%),#0b1020}
button,input{font:inherit}.shell{max-width:1120px;margin:auto;padding:32px 22px}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:30px}
.brand{display:flex;align-items:center;gap:13px}.logo{width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,#647cf6,#19b6a5);display:grid;place-items:center;font-weight:900;font-size:19px;color:white}
h1{font-size:23px;margin:0;letter-spacing:-.5px} .sub{color:#91a0b8;font-size:13px;margin-top:4px}
.actions{display:flex;gap:9px;align-items:center}button{border:1px solid #34435d;background:#18243a;color:#e8edf5;padding:9px 13px;border-radius:10px;cursor:pointer}button:hover{background:#243550}
.language-switch{position:fixed;z-index:20;top:12px;right:14px;display:flex;gap:4px;padding:4px;border:1px solid #34435d;border-radius:12px;background:#111a2a;box-shadow:0 6px 20px #0005}.language-switch button{padding:5px 8px;border-color:transparent;background:transparent;font-size:17px;line-height:1}.language-switch button[aria-pressed="true"]{background:#293750;border-color:#465a79}
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
@media(max-width:600px){.shell{padding:52px 14px 20px}header{align-items:flex-start}.hero{align-items:flex-start;flex-direction:column}.actions button{padding:8px}.language-switch{top:8px;right:8px}}
</style>
</head>
<body>
<div class="language-switch" role="group" aria-label="Language">
  <button type="button" data-language="en" aria-label="English" title="English">🇬🇧</button>
  <button type="button" data-language="es" aria-label="Español" title="Español">🇪🇸</button>
</div>
<div id="login" class="hidden">
  <div class="brand"><div class="logo">S</div><div><h1>HomeLabPilot</h1><div class="sub">Media stack control center</div></div></div>
  <p>Sign in with your HomeLabPilot dashboard account. Your browser session is stored in an HttpOnly cookie.</p>
  <form id="login-form"><input id="username" autocomplete="username" placeholder="Username" required><input id="password" type="password" autocomplete="current-password" placeholder="Password" required><button>Sign in</button></form>
  <div id="login-error" class="error"></div>
</div>
<main id="app" class="shell hidden">
  <header>
    <div class="brand"><div class="logo">S</div><div><h1>HomeLabPilot</h1><div class="sub">Media stack control center</div></div></div>
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
      <button data-view="artists">Music · Lidarr</button><button data-view="lidarr-queue">Lidarr queue</button><button data-view="lidarr-history">Lidarr history</button><button data-view="lidarr-missing">Missing albums</button>
      <button data-view="search-movies">Search movies</button><button data-view="search-series">Search series</button><button data-view="search-artists">Search artists</button><button data-view="scryer">Scryer schema</button><button data-view="scryer-titles">Scryer library</button><button data-view="scryer-requests">Scryer requests</button><button data-view="scryer-audit">Scryer audit</button><button data-view="scryer-recycle-bin">Scryer recycle bin</button><button data-view="operation-history">Operation history</button><button data-view="apps">Apps</button><button data-view="docker">Docker</button><button data-view="settings">Settings</button><button data-view="api-explorer">Advanced API</button>
    </div>
    <div class="info" id="workspace"><strong>Select a section</strong><br>Browse your library, inspect import queues and manage active downloads.</div>
  </section>
  <div class="foot">HomeLabPilot · Web dashboard and MCP endpoint in one application</div>
</main>
<script>
const $=id=>document.getElementById(id);
const UI_LANGUAGE_KEY='stackarr-language';
const UI_TRANSLATIONS={
 'Media stack control center':'Centro de control multimedia','Sign in with your HomeLabPilot dashboard account. Your browser session is stored in an HttpOnly cookie.':'Inicia sesión con tu cuenta del panel HomeLabPilot. La sesión del navegador se guarda en una cookie HttpOnly.',
 'Username':'Usuario','Password':'Contraseña','Sign in':'Iniciar sesión','Sign out':'Cerrar sesión','Refresh':'Actualizar','Loading…':'Cargando…','Overview':'Resumen','Apps':'Aplicaciones','Search apps':'Buscar aplicaciones','All':'Todas','Media':'Multimedia','Downloads':'Descargas','Automation':'Automatización','Infrastructure':'Infraestructura','Smart home':'Hogar inteligente','Configured':'Configurada','Needs attention':'Requiere atención','Not configured':'Sin configurar','Open dashboard':'Abrir panel','Required environment keys':'Variables de entorno necesarias','Connection successful':'Conexión correcta','Configured but not reachable':'Configurada pero sin conexión','Native integration':'Integración nativa','connection settings':'ajustes de conexión','Saved (not displayed)':'Guardada (no se muestra)','Enter credential':'Introduce la credencial','Remove saved credential':'Eliminar credencial guardada','Save connection':'Guardar conexión','Save connection settings for ':'¿Guardar la configuración de conexión de ','Saving encrypted settings…':'Guardando configuración cifrada…','Saved. Connection successful.':'Guardado. Conexión correcta.','Saved. Settings applied, but the connection check failed.':'Guardado. Configuración aplicada, pero falla la comprobación de conexión.','Saved. This integration does not yet have an active health check.':'Guardado. Esta integración aún no tiene comprobación de conexión activa.','Could not save: ':'No se pudo guardar: ','Credentials are encrypted in persistent /data storage and are never returned to this browser. Leave password fields blank to keep existing credentials.':'Las credenciales se cifran en el almacenamiento persistente /data y nunca se devuelven al navegador. Deja las contraseñas vacías para conservar las credenciales actuales.','API integration':'Integración API','Status only':'Solo estado','Planned integration':'Integración prevista','App catalogue':'Catálogo de aplicaciones','Showing configured and available integrations.':'Aplicaciones configuradas e integraciones disponibles.','Dashboard support is planned for this integration.':'La gestión desde el panel está pendiente para esta integración.','Live connectivity of your configured services':'Conectividad en directo de tus servicios configurados','Checking…':'Comprobando…','Not updated yet':'Aún sin actualizar','Updated ':'Actualizado ',' services online':' servicios conectados','Online':'Conectado','Attention':'Atención','Connected':'Conectado','Not connected':'Sin conexión','Version ':'Versión ','Media management':'Gestión multimedia','Select a section':'Selecciona una sección','Browse your library, inspect import queues and manage active downloads.':'Explora tu biblioteca, revisa las colas de importación y administra las descargas activas.','HomeLabPilot · Web dashboard and MCP endpoint in one application':'HomeLabPilot · Panel web y endpoint MCP en una aplicación',
 'Movies · Radarr':'Películas · Radarr','Series · Sonarr':'Series · Sonarr','Radarr queue':'Cola de Radarr','Sonarr queue':'Cola de Sonarr','Downloads · qBittorrent':'Descargas · qBittorrent','Music · Lidarr':'Música · Lidarr','Lidarr queue':'Cola de Lidarr','Lidarr history':'Historial de Lidarr','Missing albums':'Álbumes ausentes','Search movies':'Buscar películas','Search series':'Buscar series','Search artists':'Buscar artistas','Scryer schema':'Esquema de Scryer','Scryer library':'Biblioteca de Scryer','Scryer requests':'Solicitudes de Scryer','Scryer audit':'Auditoría de Scryer','Scryer recycle bin':'Papelera de Scryer','Operation history':'Historial de operaciones','Docker':'Docker','Settings':'Configuración','Advanced API':'API avanzada',
 'Select a section':'Selecciona una sección','Loading…':'Cargando…','No records found.':'No se encontraron registros.','No matching operations.':'No hay operaciones coincidentes.','Unavailable':'No disponible','Search':'Buscar','Clear':'Limpiar','Save':'Guardar','Save changes':'Guardar cambios','Save preferences':'Guardar preferencias','Save Bazarr settings':'Guardar ajustes de Bazarr','Discard changes':'Descartar cambios','Create record':'Crear registro','Create configuration record':'Crear registro de configuración','Paste the JSON object required by the selected application and resource. Use id 0 or omit id. Secret values are not returned to the browser.':'Pega el objeto JSON requerido por la aplicación y el recurso seleccionados. Usa id 0 u omítelo. Los valores secretos no se muestran en el navegador.','Preview delete':'Vista previa del borrado','Confirm title deletion':'Confirmar borrado del título','Preview: ':'Vista previa: ','Type exactly:':'Escribe exactamente:','Type this exact confirmation to delete:':'Escribe exactamente esta confirmación para borrar:','Type this exact confirmation to remove the torrent:':'Escribe exactamente esta confirmación para quitar el torrent:','The confirmation text does not match the preview.':'El texto de confirmación no coincide con la vista previa.','Deletion accepted: ':'Borrado aceptado: ','Deletion was not completed: ':'No se completó el borrado: ','Preparing deletion preview…':'Preparando vista previa del borrado…','Sample paths: ':'Rutas de ejemplo: ','Delete media files from disk too':'Borrar también los archivos multimedia del disco','Recycled files':'Archivos reciclados','Original path':'Ruta original','Scheduled purge':'Eliminación programada','Title / file':'Título / archivo','Items in bin':'Elementos en la papelera','Retention':'Retención','Enabled':'Activado','Disabled':'Desactivado','days':'días','none':'ninguna',
 'HomeLabPilot operation history':'Historial de operaciones de HomeLabPilot','Recent writes initiated through HomeLabPilot. Request bodies, credentials and tokens are not recorded.':'Cambios recientes iniciados desde HomeLabPilot. No se guardan cuerpos de solicitud, credenciales ni tokens.','Time (UTC)':'Hora (UTC)','Source':'Origen','Service':'Servicio','Operation':'Operación','Target':'Destino','Result':'Resultado','Docker · allowlisted containers':'Docker · contenedores permitidos','Only the optional restricted gateway can act on containers named in its allowlist. Start, stop and restart require separate Docker operations permission.':'Solo la pasarela restringida opcional puede actuar sobre los contenedores de su lista permitida. Iniciar, detener y reiniciar requiere permisos de operaciones Docker independientes.','Optional Docker management is disabled':'La gestión opcional de Docker está desactivada','No allowlisted containers found.':'No se encontraron contenedores permitidos.','Container':'Contenedor','Image':'Imagen','State':'Estado','Actions':'Acciones','Start':'Iniciar','Stop':'Detener','Restart':'Reiniciar','Cancel':'Cancelar',
 'Scryer · ':'Scryer · ','Library':'Biblioteca','Requests':'Solicitudes','Audit log':'Registro de auditoría','Title':'Título','Year':'Año','Facet':'Categoría','Status':'Estado','Created':'Creado','Sequence':'Secuencia','Time':'Hora','Actor':'Autor','Event':'Evento','Title ID':'ID del título','All facets':'Todas las categorías','Movies':'Películas','Anime':'Anime','Series':'Series','Search titles…':'Buscar títulos…','Loading titles…':'Cargando títulos…','No releases found.':'No se encontraron lanzamientos.','Available releases':'Lanzamientos disponibles','Searching releases…':'Buscando lanzamientos…','Loading albums…':'Cargando álbumes…','Albums':'Álbumes','Release date':'Fecha de lanzamiento','Monitored':'Monitorizado','Unmonitored':'No monitorizado','Actions':'Acciones','Online':'Conectado','Login failed. Check your username and password.':'No se pudo iniciar sesión. Comprueba el usuario y la contraseña.','Request failed':'La solicitud ha fallado','Access the native REST APIs of Radarr, Sonarr, Prowlarr, Bazarr and Lidarr.':'Accede a las API REST nativas de Radarr, Sonarr, Prowlarr, Bazarr y Lidarr.','Send request':'Enviar solicitud','Clear response':'Borrar respuesta','API path':'Ruta de API','HTTP method':'Método HTTP','Query parameters · JSON object (optional)':'Parámetros de consulta · objeto JSON (opcional)','Request body · JSON (optional)':'Cuerpo de solicitud · JSON (opcional)','Ready.':'Listo.','GET requests require read access; normal writes require operations; configuration, system and destructive operations require admin.':'Las solicitudes GET requieren permiso de lectura; las escrituras normales, operaciones; y la configuración, el sistema y las operaciones destructivas, administración.'
};
const UI_TRANSLATION_ENTRIES=Object.entries(UI_TRANSLATIONS).sort((a,b)=>b[0].length-a[0].length);
function getLanguage(){return localStorage.getItem(UI_LANGUAGE_KEY)==='es'?'es':'en';}
function translateText(value){if(getLanguage()!=='es')return value;let translated=value;for(const [source,target] of UI_TRANSLATION_ENTRIES)translated=translated.replaceAll(source,target);return translated;}
function translateNode(node){if(node.nodeType===Node.TEXT_NODE){if(node.parentElement?.closest('[data-config-form]'))return;const value=translateText(node.nodeValue);if(value!==node.nodeValue)node.nodeValue=value;return;}if(node.nodeType!==Node.ELEMENT_NODE)return;if(node.matches('[data-config-form]')||node.closest('[data-config-form]')||node.tagName==='SCRIPT'||node.tagName==='STYLE')return;for(const attribute of ['placeholder','title','aria-label'])if(node.hasAttribute(attribute))node.setAttribute(attribute,translateText(node.getAttribute(attribute)));for(const child of node.childNodes)translateNode(child);}
function applyLanguage(){const language=getLanguage();document.documentElement.lang=language;document.querySelectorAll('[data-language]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.language===language)));translateNode(document.body);}
document.querySelectorAll('[data-language]').forEach(button=>button.addEventListener('click',()=>{localStorage.setItem(UI_LANGUAGE_KEY,button.dataset.language);location.reload();}));
const nativeAlert=window.alert.bind(window),nativeConfirm=window.confirm.bind(window),nativePrompt=window.prompt.bind(window);
window.alert=message=>nativeAlert(translateText(String(message)));
window.confirm=message=>nativeConfirm(translateText(String(message)));
window.prompt=(message,value)=>nativePrompt(translateText(String(message)),value===undefined?undefined:translateText(String(value)));
applyLanguage();new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(translateNode))).observe(document.body,{childList:true,subtree:true});
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
function renderScryerTitles(result){if(result.errors?.length)throw new Error(result.errors.map(x=>x.message).join('; '));const page=result.data?.titles||{},items=page.items||[];const rows=items.map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.name)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.year)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.facet)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.contentStatus)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.libraryName)+'</td><td style="padding:10px;border-bottom:1px solid #25344d"><button data-scryer-delete-preview data-title-id="'+esc(x.id)+'" data-title-name="'+esc(x.name)+'">Preview delete</button></td></tr>');$('scryer-title-results').innerHTML='<p class="muted">'+(page.totalCount||0)+' titles · showing '+items.length+(page.hasMore?' · more available':'')+'</p>'+table(['Title','Year','Facet','Status','Library','Actions'],rows);}

const APP_CATALOG=[
{id:'radarr',name:'Radarr',category:'Media',mode:'Native integration',desc:'Movie library, monitoring, quality profiles and releases.',support:'Full dashboard'},
{id:'sonarr',name:'Sonarr',category:'Media',mode:'Native integration',desc:'TV series, seasons, episodes, queues and releases.',support:'Full dashboard'},
{id:'lidarr',name:'Lidarr',category:'Media',mode:'Native integration',desc:'Music artists, albums, monitoring and releases.',support:'Full dashboard'},
{id:'prowlarr',name:'Prowlarr',category:'Media',mode:'Native integration',desc:'Indexer management and configuration.',support:'Configuration'},
{id:'bazarr',name:'Bazarr',category:'Media',mode:'Native integration',desc:'Subtitle providers and subtitle settings.',support:'Configuration'},
{id:'scryer',name:'Scryer',category:'Media',mode:'Native integration',desc:'Media catalog, requests, audit and recycle bin.',support:'Full dashboard'},
{id:'plex',name:'Plex',category:'Media',mode:'API integration',desc:'Media server connectivity and native API access.',support:'API explorer'},
{id:'jellyfin',name:'Jellyfin',category:'Media',mode:'API integration',desc:'Media server connectivity and API access.',support:'API explorer'},
{id:'seerr',name:'Seerr',category:'Media',mode:'API integration',desc:'Media requests and discovery.',support:'API explorer'},
{id:'immich',name:'Immich',category:'Media',mode:'API integration',desc:'Photo and video library API.',support:'API explorer'},
{id:'romm',name:'RomM',category:'Media',mode:'API integration',desc:'Retro game library API.',support:'API explorer'},
{id:'bookorbit',name:'BookOrbit',category:'Media',mode:'API integration',desc:'Book library API.',support:'API explorer'},
{id:'tinymediamanager',name:'TinyMediaManager',category:'Media',mode:'API integration',desc:'Media metadata management API.',support:'API explorer'},
{id:'tidarr',name:'Tidarr',category:'Media',mode:'API integration',desc:'Music service API.',support:'API explorer'},
{id:'tdarr',name:'Tdarr',category:'Media',mode:'Planned integration',desc:'Media transcoding and library health.',support:'Dashboard support is planned for this integration.'},
{id:'youtarr',name:'Youtarr',category:'Media',mode:'Planned integration',desc:'YouTube media management.',support:'Dashboard support is planned for this integration.'},
{id:'qbittorrent',name:'qBittorrent',category:'Downloads',mode:'Native integration',desc:'Torrent queue, categories, controls and file moves.',support:'Full dashboard'},
{id:'transmission',name:'Transmission',category:'Downloads',mode:'API integration',desc:'Transmission RPC connectivity and read API.',support:'API explorer'},
{id:'flaresolverr',name:'FlareSolverr',category:'Downloads',mode:'API integration',desc:'Challenge-solving service connectivity.',support:'API explorer'},
{id:'pulsarr',name:'Pulsarr',category:'Automation',mode:'API integration',desc:'Media automation API.',support:'API explorer'},
{id:'cleanuparr',name:'Cleanuparr',category:'Automation',mode:'API integration',desc:'Download cleanup automation API.',support:'API explorer'},
{id:'maintainerr',name:'Maintainerr',category:'Automation',mode:'API integration',desc:'Media library maintenance API.',support:'API explorer'},
{id:'agregarr',name:'Agregarr',category:'Automation',mode:'API integration',desc:'Collection automation API.',support:'API explorer'},
{id:'tracearr',name:'Tracearr',category:'Automation',mode:'API integration',desc:'Media activity tracking API.',support:'API explorer'},
{id:'questarr',name:'Questarr',category:'Automation',mode:'Planned integration',desc:'Media request automation.',support:'Dashboard support is planned for this integration.'},
{id:'recyclarr',name:'Recyclarr',category:'Automation',mode:'Status only',desc:'TRaSH Guides profile synchronization (container/CLI).',support:'Status only'},
{id:'postgres',name:'PostgreSQL',category:'Infrastructure',mode:'Status only',desc:'Database TCP reachability check.',support:'Status only'},
{id:'redis',name:'Redis',category:'Infrastructure',mode:'Status only',desc:'Cache TCP reachability check.',support:'Status only'},
{id:'docker',name:'Docker gateway',category:'Infrastructure',mode:'Status only',desc:'Restricted allowlisted container controls.',support:'Docker view'},
{id:'cloudflare',name:'Cloudflare',category:'Infrastructure',mode:'API integration',desc:'Cloudflare account API connectivity.',support:'API explorer'},
{id:'homeassistant',name:'Home Assistant',category:'Smart home',mode:'Planned integration',desc:'Home automation platform.',support:'Dashboard support is planned for this integration.'},
{id:'frigate',name:'Frigate',category:'Smart home',mode:'Planned integration',desc:'Local NVR and object detection.',support:'Dashboard support is planned for this integration.'}
];
const APP_ENV_KEYS={
radarr:['RADARR_URL','RADARR_API_KEY'],sonarr:['SONARR_URL','SONARR_API_KEY'],lidarr:['LIDARR_URL','LIDARR_API_KEY'],prowlarr:['PROWLARR_URL','PROWLARR_API_KEY'],bazarr:['BAZARR_URL','BAZARR_API_KEY'],scryer:['SCRYER_URL','SCRYER_API_KEY'],qbittorrent:['QBITTORRENT_URL','QBITTORRENT_USERNAME','QBITTORRENT_PASSWORD'],
plex:['PLEX_URL','PLEX_TOKEN'],jellyfin:['JELLYFIN_URL','JELLYFIN_API_KEY'],seerr:['SEERR_URL','SEERR_API_KEY'],transmission:['TRANSMISSION_URL','TRANSMISSION_USERNAME','TRANSMISSION_PASSWORD'],pulsarr:['PULSARR_URL','PULSARR_API_KEY'],cleanuparr:['CLEANUPARR_URL','CLEANUPARR_API_KEY'],maintainerr:['MAINTAINERR_URL'],agregarr:['AGREGARR_URL','AGREGARR_API_KEY'],tracearr:['TRACEARR_URL','TRACEARR_API_KEY'],immich:['IMMICH_URL','IMMICH_API_KEY'],romm:['ROMM_URL','ROMM_API_TOKEN'],bookorbit:['BOOKORBIT_URL','BOOKORBIT_API_KEY'],tinymediamanager:['TINYMEDIAMANAGER_URL','TINYMEDIAMANAGER_API_KEY'],tidarr:['TIDARR_URL','TIDARR_API_KEY'],flaresolverr:['FLARESOLVERR_URL'],cloudflare:['CLOUDFLARE_API_URL','CLOUDFLARE_API_TOKEN'],recyclarr:['RECYCLARR_CONTAINER'],postgres:['POSTGRES_HOST','POSTGRES_PORT'],redis:['REDIS_HOST','REDIS_PORT'],docker:['STACKARR_DOCKER_ENABLED','STACKARR_DOCKER_PERMISSION_LEVEL','STACKARR_DOCKER_ALLOWED_CONTAINERS'],homeassistant:['HOMEASSISTANT_URL','HOMEASSISTANT_TOKEN'],frigate:['FRIGATE_URL','FRIGATE_API_KEY'],tdarr:['TDARR_URL','TDARR_API_KEY'],youtarr:['YOUTARR_URL','YOUTARR_API_KEY'],questarr:['QUESTARR_URL','QUESTARR_API_KEY']
};
APP_CATALOG.forEach(app=>{app.env=APP_ENV_KEYS[app.id]||[];});
const APP_DASHBOARD_VIEWS={radarr:'movies',sonarr:'series',lidarr:'artists',prowlarr:'settings',bazarr:'settings',scryer:'scryer',qbittorrent:'downloads',docker:'docker'};
function appCard(app,status){
 const check=status[app.id],online=!!(check&&check.ok===true);
 const configured=!!(check&&(check.configured===true||online));
 const planned=app.mode==='Planned integration';
 const state=planned?'Planned':!configured?'Not configured':online?'Online':'Needs attention';
 const klass=online?'ok':configured?'bad':'';
 const open=APP_DASHBOARD_VIEWS[app.id];
 return '<article class="card" data-app-card data-category="'+esc(app.category)+'" data-search="'+esc((app.name+' '+app.desc+' '+app.category).toLowerCase())+'"><div class="cardtop"><div class="name">'+esc(app.name)+'</div><span class="status '+klass+'">'+esc(state)+'</span></div><div class="version">'+esc(app.category)+' · '+esc(app.mode)+'</div><p class="muted" style="line-height:1.5">'+esc(app.desc)+'</p><div class="muted">'+esc(app.support)+'</div><div class="actions" style="margin-top:12px">'+(open?'<button type="button" data-app-open="'+esc(app.id)+'">Open dashboard</button>':'')+'<button type="button" data-app-details="'+esc(app.id)+'">Details</button></div><div id="app-detail-'+esc(app.id)+'" class="info" hidden style="margin-top:10px"></div></article>';
}

async function openView(view){const target=$('workspace');target.textContent='Loading…';try{
 let data,html='';

 if(view==='apps'){
  data=await request('/web-api/status');const statuses=data.services||{};const appConfigs=await request('/web-api/apps/config');
  const categories=['All',...new Set(APP_CATALOG.map(app=>app.category))];
  html='<h3>App catalogue</h3><p class="muted">Showing configured and available integrations. Native management is identified separately from generic API access and planned integrations.</p><input id="apps-search" placeholder="Search apps" style="max-width:420px"><div class="actions" id="apps-categories" style="flex-wrap:wrap;margin:10px 0 16px">'+categories.map((c,i)=>'<button type="button" data-app-filter="'+esc(c)+'" style="'+(i===0?'border-color:#647cf6':'')+'">'+esc(c)+'</button>').join('')+'</div><div class="grid" id="apps-grid">'+APP_CATALOG.map(app=>appCard(app,statuses)).join('')+'</div>';
  target.innerHTML=html;let active='All';
  const filterApps=()=>{const term=$('apps-search').value.trim().toLowerCase();document.querySelectorAll('[data-app-card]').forEach(card=>{card.style.display=(active==='All'||card.dataset.category===active)&&card.dataset.search.includes(term)?'':'none';});};
  $('apps-search').addEventListener('input',filterApps);
  $('apps-categories').addEventListener('click',e=>{const b=e.target.closest('[data-app-filter]');if(!b)return;active=b.dataset.appFilter;$('apps-categories').querySelectorAll('button').forEach(x=>x.style.borderColor=x===b?'#647cf6':'#34435d');filterApps();});
  const renderAppDetails=(app,panel)=>{
   const check=statuses[app.id]||{},config=appConfigs[app.id],connection=check.ok===true?'Connection successful':check.configured===true?'Configured but not reachable':'Not configured';
   if(!config){panel.innerHTML='<strong>'+esc(app.name)+' · integration details</strong><p>'+esc(app.desc)+'</p><p class="muted">This service does not expose editable connection settings in HomeLabPilot.</p>';return;}
   const fields=config.fields||[];
   const controls=fields.map(field=>{
    const secret=field.kind==='secret',inputType=secret?'password':field.kind==='port'?'number':'text';
    const placeholder=secret?(field.secret_set?'Saved · enter a new value to replace':'Enter credential'):field.redacted?'Saved URL hidden · enter a new URL to replace':'';
    const input='<input data-app-config-key="'+esc(field.key)+'" type="'+inputType+'" '+(secret?'autocomplete="new-password"':'')+' value="'+esc(field.value||'')+'" placeholder="'+esc(placeholder)+'" '+(field.kind==='port'?'min="1" max="65535" step="1"':'')+' style="width:100%;background:#0b1322;color:#e8edf5;border:1px solid #34435d;border-radius:8px;padding:9px;margin-top:5px">';
    const saved=secret&&field.secret_set?'<span class="muted"> · Saved (not displayed)</span>':'';
    const clear=secret&&field.secret_set?'<label class="muted" style="display:flex;align-items:center;gap:7px;margin-top:5px"><input type="checkbox" data-app-clear-secret="'+esc(field.key)+'" style="width:auto;margin:0">Remove saved credential</label>':'';
    return '<label style="display:block;padding:7px 0"><span class="muted">'+esc(field.label||field.key)+saved+'</span>'+input+clear+'</label>';
   }).join('');
   panel.innerHTML='<strong>'+esc(app.name)+' · connection settings</strong><p class="muted">'+esc(app.mode)+' · '+esc(connection)+'</p><p>'+esc(app.desc)+'</p><form data-app-config-form="'+esc(app.id)+'">'+(fields.length?controls:'<p class="muted">No connection fields are defined.</p>')+'<p class="muted">Credentials are encrypted in persistent /data storage and are never returned to this browser. Leave password fields blank to keep existing credentials.</p><div class="actions"><button type="submit" '+(!fields.length?'disabled':'')+'>Save connection</button></div><div class="muted" data-app-config-status style="margin-top:9px"></div></form>';
  };
  $('apps-grid').addEventListener('click',e=>{
   const open=e.target.closest('[data-app-open]');
   if(open){const view=APP_DASHBOARD_VIEWS[open.dataset.appOpen];if(view)openView(view);return;}
   const b=e.target.closest('[data-app-details]');if(!b)return;
   const app=APP_CATALOG.find(x=>x.id===b.dataset.appDetails);if(!app)return;
   const panel=$('app-detail-'+app.id);panel.hidden=!panel.hidden;if(!panel.hidden)renderAppDetails(app,panel);
  });
  $('apps-grid').addEventListener('submit',async e=>{
   const form=e.target.closest('[data-app-config-form]');if(!form)return;e.preventDefault();
   const appId=form.dataset.appConfigForm,values={},clearSecrets=[];
   form.querySelectorAll('[data-app-config-key]').forEach(input=>{values[input.dataset.appConfigKey]=input.value;});
   form.querySelectorAll('[data-app-clear-secret]:checked').forEach(input=>clearSecrets.push(input.dataset.appClearSecret));
   const button=form.querySelector('button[type="submit"]'),status=form.querySelector('[data-app-config-status]');
   if(!confirm('Save connection settings for '+appId+'?'))return;
   button.disabled=true;status.textContent='Saving encrypted settings…';
   try{
    await request('/web-api/apps/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({app_id:appId,values,clear_secrets:clearSecrets})});
    const refreshed=await request('/web-api/status');Object.assign(statuses,refreshed.services||{});
    const check=statuses[appId]||{},card=form.closest('[data-app-card]'),badge=card.querySelector('.status');
    const online=check.ok===true,configured=check.configured===true||online;
    badge.textContent=online?'Online':configured?'Needs attention':'Not configured';badge.className='status '+(online?'ok':configured?'bad':'');
    status.textContent=online?'Saved. Connection successful.':configured?'Saved. Settings applied, but the connection check failed.':'Saved. This integration does not yet have an active health check.';
    const latest=await request('/web-api/apps/config');Object.assign(appConfigs,latest);renderAppDetails(APP_CATALOG.find(x=>x.id===appId),$('app-detail-'+appId));
    $('app-detail-'+appId).querySelector('[data-app-config-status]').textContent=online?'Saved. Connection successful.':configured?'Saved. Settings applied, but the connection check failed.':'Saved. This integration does not yet have an active health check.';
   }catch(err){status.textContent='Could not save: '+err.message;}
   finally{button.disabled=false;}
  });
  return;
 }
 if(view==='operation-history'){
  data=await request('/web-api/audit?limit=200&offset=0');
  const rows=(data||[]).map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.occurred_at)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.source)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.service)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.operation)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.target)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.outcome)+'</td></tr>');
  html='<h3>HomeLabPilot operation history</h3><p class="muted">Recent writes initiated through HomeLabPilot. Request bodies, credentials and tokens are not recorded.</p>'+table(['Time (UTC)','Source','Service','Operation','Target','Result'],rows);target.innerHTML=html;return;
 }
 if(view==='docker'){
  data=await request('/web-api/docker/containers');
  const rows=(data||[]).map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.name)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.image)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.state+' · '+x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d"><button data-docker-action="start" data-container="'+esc(x.name)+'">Start</button> <button data-docker-action="stop" data-container="'+esc(x.name)+'">Stop</button> <button data-docker-action="restart" data-container="'+esc(x.name)+'">Restart</button></td></tr>');
  html='<h3>Docker · allowlisted containers</h3><p class="muted">Only the optional restricted gateway can act on containers named in its allowlist. Start, stop and restart require separate Docker operations permission.</p>'+table(['Container','Image','State','Actions'],rows);target.innerHTML=html||'<div class="muted">No allowlisted containers found.</div>';return;
 }
 if(view==='scryer-titles'){
  html='<h3>Scryer · Library</h3><form id="scryer-title-search" class="actions" style="flex-wrap:wrap"><input id="scryer-title-query" placeholder="Search titles…" style="min-width:220px;flex:1"><select id="scryer-title-facet" style="background:#0e1728;color:#e8edf5;padding:9px;border:1px solid #34435d;border-radius:8px"><option value="">All facets</option><option value="MOVIE">Movies</option><option value="SERIES">Series</option><option value="ANIME">Anime</option></select><button>Search</button></form><div id="scryer-title-results" class="info" style="margin-top:12px">Loading titles…</div><div id="scryer-delete-preview" style="margin-top:12px"></div>';
  target.innerHTML=html;
  try{const result=await request('/web-api/scryer/titles?limit=50');renderScryerTitles(result);}catch(err){$('scryer-title-results').innerHTML='<div class="error">'+esc(err.message)+'</div>';}
  return;
 }
 if(view==='scryer-requests'||view==='scryer-audit'){
  const requests=view==='scryer-requests';
  data=await request(requests?'/web-api/scryer/requests':'/web-api/scryer/audit?limit=100');
  if(data.errors?.length)throw new Error(data.errors.map(x=>x.message).join('; '));
  const records=requests?(data.data?.mediaRequests||[]):(data.data?.auditLog||[]);
  const rows=requests?records.map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.title)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.year)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.facet)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.createdAt)+'</td></tr>'):records.map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.sequence)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.occurredAt)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.actorDisplayName||x.actorKind)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.eventType)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.titleId)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.facet)+'</td></tr>');
  html='<h3>Scryer · '+(requests?'Requests':'Audit log')+'</h3>'+table(requests?['Title','Year','Facet','Status','Created']:['Sequence','Time','Actor','Event','Title ID','Facet'],rows);target.innerHTML=html;return;
 }

 if(view==='scryer-recycle-bin'){
  html='<h3>Scryer · Recycle bin</h3><p class="muted">Read-only view of recycled files and their scheduled purge dates. Restore and permanent-delete controls remain in Scryer.</p><div id="scryer-recycle-settings" class="grid" style="margin:12px 0"></div><div id="scryer-recycle-items" class="info">Loading recycled items…</div>';
  target.innerHTML=html;
  try{
   const result=await request('/web-api/scryer/recycle-bin?limit=500&offset=0');
   if(result.errors?.length)throw new Error(result.errors.map(x=>x.message).join('; '));
   const settings=result.data?.recycleBinSettings||{},page=result.data?.recycledItems||{},items=page.items||[];
   const settingCard=(label,value)=>'<article class="card"><div class="muted">'+esc(label)+'</div><div class="name" style="margin-top:8px">'+esc(value)+'</div></article>';
   $('scryer-recycle-settings').innerHTML=settingCard('Recycle bin',settings.enabled?'Enabled':'Disabled')+settingCard('Retention',settings.retentionDays+' days')+settingCard('Items in bin',page.totalCount||0);
   let warning=settings.validationError?'<div class="error">'+esc(settings.validationError)+'</div>':'';
   const paths=settings.effectivePaths||[];
   if(paths.length)warning+='<p class="muted">Storage: '+esc(paths.join(' · '))+'</p>';
   const date=value=>value?esc(new Date(value).toLocaleString()):'—';
   const size=value=>{const n=Number(value||0);if(!n)return '0 B';const units=['B','KB','MB','GB','TB'];const i=Math.min(Math.floor(Math.log(n)/Math.log(1024)),units.length-1);return (n/Math.pow(1024,i)).toFixed(i?1:0)+' '+units[i];};
   const rows=items.map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.titleName||x.fileName)+'</td><td style="padding:10px;border-bottom:1px solid #25344d;max-width:320px;overflow-wrap:anywhere">'+cell(x.originalPath)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+esc(size(x.sizeBytes))+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.reason)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+date(x.recycledAt)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+date(x.scheduledDeletionAt)+'</td></tr>');
   $('scryer-recycle-items').innerHTML=warning+'<h4>Recycled files <span class="muted">('+items.length+' shown of '+(page.totalCount||0)+')</span></h4>'+table(['Title / file','Original path','Size','Reason','Recycled','Scheduled purge'],rows);
  }catch(err){$('scryer-recycle-items').innerHTML='<div class="error">'+esc(err.message)+'</div>';}
  return;
 }

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
    const introspection='query HomeLabPilotSchema { __schema { queryType { name fields(includeDeprecated:true) { name description args { name description defaultValue type { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } } type { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } } } mutationType { name fields(includeDeprecated:true) { name description args { name description defaultValue type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } } } }';
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
   html='<h3>Advanced API explorer</h3><p class="muted">Access the native REST APIs of Radarr, Sonarr, Prowlarr, Bazarr and Lidarr. This exposes endpoints that do not yet have dedicated forms. API keys remain server-side. Permission checks are enforced by HomeLabPilot for every request.</p><div class="card" style="margin:12px 0"><div class="grid"><label><span class="muted">Service</span><select id="api-service" style="width:100%;background:#0e1728;color:#e8edf5;padding:10px;border:1px solid #34435d;border-radius:8px"><option value="radarr">Radarr</option><option value="sonarr">Sonarr</option><option value="prowlarr">Prowlarr</option><option value="bazarr">Bazarr</option><option value="lidarr">Lidarr</option></select></label><label><span class="muted">HTTP method</span><select id="api-method" style="width:100%;background:#0e1728;color:#e8edf5;padding:10px;border:1px solid #34435d;border-radius:8px"><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option></select></label></div><label style="display:block;margin-top:12px"><span class="muted">API path</span><input id="api-path" value="/api/v3/system/status" spellcheck="false" style="width:100%;background:#0b1322;color:#e8edf5;border:1px solid #34435d;border-radius:8px;padding:10px"></label><label style="display:block;margin-top:12px"><span class="muted">Query parameters · JSON object (optional)</span><textarea id="api-params" rows="3" spellcheck="false" style="width:100%;background:#0b1322;color:#dce7f8;border:1px solid #34435d;border-radius:9px;padding:10px;font:12px ui-monospace,monospace">{}</textarea></label><label style="display:block;margin-top:12px"><span class="muted">Request body · JSON (optional)</span><textarea id="api-body" rows="7" spellcheck="false" style="width:100%;background:#0b1322;color:#dce7f8;border:1px solid #34435d;border-radius:9px;padding:10px;font:12px ui-monospace,monospace">{}</textarea></label><div class="actions" style="margin-top:12px"><button id="api-run">Send request</button><button id="api-clear">Clear response</button></div><pre id="api-result" class="info" style="white-space:pre-wrap;overflow-wrap:anywhere;margin-top:12px">Ready.</pre></div><p class="muted">Examples: Radarr/Sonarr <code>/api/v3/movie</code>, Prowlarr/Lidarr <code>/api/v1</code>, Bazarr <code>/api/system/status</code>. GET requests require read access; normal writes require operations; configuration, system and destructive operations require admin. Check the target application API documentation before changing unfamiliar endpoints.</p>';
   target.innerHTML=html;
   $('api-service').addEventListener('change',()=>{
    const service=$('api-service').value;
    $('api-path').value=service==='prowlarr'||service==='lidarr'?'/api/v1/system/status':service==='bazarr'?'/api/system/status':'/api/v3/system/status';
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
   html='<h3>Configuration</h3><p class="muted">Edit Radarr/Sonarr/Lidarr profiles and integrations, Prowlarr indexers and download clients, selected Bazarr subtitle settings, or qBittorrent preferences.</p><div class="actions" style="flex-wrap:wrap;margin:12px 0"><select id="settings-service" style="background:#0e1728;color:#e8edf5;padding:9px;border:1px solid #34435d;border-radius:8px"><option value="radarr">Radarr</option><option value="sonarr">Sonarr</option><option value="prowlarr">Prowlarr</option><option value="lidarr">Lidarr</option><option value="bazarr">Bazarr</option><option value="qbittorrent">qBittorrent</option></select><select id="settings-resource" style="background:#0e1728;color:#e8edf5;padding:9px;border:1px solid #34435d;border-radius:8px"><option value="qualityprofile">Quality profiles</option><option value="metadataprofile">Metadata profiles (Lidarr)</option><option value="delayprofile">Delay profiles</option><option value="indexer">Indexers</option><option value="downloadclient">Download clients</option><option value="notification">Notifications</option><option value="qualitydefinition">Quality definitions</option><option value="customformat">Custom formats</option><option value="importlist">Import lists</option><option value="metadata">Metadata</option><option value="tag">Tags</option><option value="languageprofile">Language profiles (Sonarr)</option><option value="releaseprofile">Release profiles (Sonarr)</option></select><button id="load-settings">Load settings</button></div><div id="settings-records" class="muted">Choose an application and load its configuration.</div>';
   target.innerHTML=html;
   const svc=$('settings-service'),res=$('settings-resource'),records=$('settings-records');
   const updateResource=()=>{
    const service=svc.value;
    res.disabled=service==='qbittorrent'||service==='bazarr';
    const prowlarrResources=new Set(['indexer','downloadclient','notification']);
    const lidarrResources=new Set(['qualityprofile','metadataprofile','delayprofile','indexer','downloadclient','notification','qualitydefinition','customformat','importlist','metadata','tag','releaseprofile','autotagging','remotepathmapping']);
    const radarrOnlyExcluded=new Set(['languageprofile','releaseprofile','metadataprofile']);
    Array.from(res.options).forEach(option=>{
     option.disabled=(service==='prowlarr'&&!prowlarrResources.has(option.value))||(service==='radarr'&&radarrOnlyExcluded.has(option.value))||(service==='lidarr'&&!lidarrResources.has(option.value));
    });
    if(service==='prowlarr'&&!prowlarrResources.has(res.value))res.value='indexer';
    if(service==='radarr'&&radarrOnlyExcluded.has(res.value))res.value='qualityprofile';
    if(service==='lidarr'&&!lidarrResources.has(res.value))res.value='qualityprofile';
   };
   svc.addEventListener('change',updateResource);updateResource();
   $('load-settings').addEventListener('click',async()=>{
    records.textContent='Loading configuration…';
    try{
     const service=svc.value,resource=res.value;
     if(service==='bazarr'){
      const data=await request('/web-api/bazarr/settings'),fields=data.fields||[];
      const groups={};fields.forEach(field=>{const group=field.key.split('-')[0];(groups[group]||(groups[group]=[])).push(field);});
      const labels={general:'Sonarr / Radarr and subtitle behaviour',embeddedsubtitles:'Embedded subtitles',analytics:'Privacy'};
      records.innerHTML=Object.entries(groups).map(([group,items])=>'<article class="card" style="margin:10px 0"><div class="name">'+esc(labels[group]||fieldLabel(group))+'</div>'+items.map(field=>{const value=field.value,key=esc(field.key);if(typeof value==='boolean')return '<label style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid #25344d"><input data-bazarr-key="'+key+'" data-original="'+String(value)+'" type="checkbox" '+(value?'checked':'')+' style="width:auto;margin:0"><span>'+esc(field.label)+'</span></label>';if(typeof value==='number')return '<label style="display:block;padding:8px 0"><span class="muted">'+esc(field.label)+'</span><input data-bazarr-key="'+key+'" data-original="'+esc(value)+'" type="number" min="0" step="1" value="'+esc(value)+'" style="width:100%;background:#0b1322;color:#e8edf5;border:1px solid #34435d;border-radius:8px;padding:9px;margin-top:5px"></label>';return '<label style="display:block;padding:8px 0"><span class="muted">'+esc(field.label)+'</span><input data-bazarr-key="'+key+'" data-original="'+esc(value??'')+'" type="text" value="'+esc(value??'')+'" style="width:100%;background:#0b1322;color:#e8edf5;border:1px solid #34435d;border-radius:8px;padding:9px;margin-top:5px"></label>';}).join('')+'</article>').join('')+'<div class="actions"><button id="save-bazarr-settings">Save Bazarr settings</button><button id="reload-bazarr-settings">Discard changes</button></div><div id="bazarr-save-status" class="muted" style="margin-top:9px"></div>';
      $('reload-bazarr-settings').addEventListener('click',()=> $('load-settings').click());
      $('save-bazarr-settings').addEventListener('click',async()=>{const button=$('save-bazarr-settings'),settings={};try{records.querySelectorAll('[data-bazarr-key]').forEach(input=>{let value=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;const original=input.type==='checkbox'?input.dataset.original==='true':input.type==='number'?Number(input.dataset.original):input.dataset.original;if(value!==original){if(input.type==='number'&&(!Number.isInteger(value)||value<0))throw new Error('Enter a non-negative whole number for '+input.dataset.bazarrKey);settings[input.dataset.bazarrKey]=value;}});if(!Object.keys(settings).length){$('bazarr-save-status').textContent='No changes to save.';return;}if(!confirm('Apply the selected Bazarr settings?'))return;button.disabled=true;await request('/web-api/bazarr/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({settings})});$('bazarr-save-status').textContent='Saved '+Object.keys(settings).length+' setting(s).';}catch(err){$('bazarr-save-status').textContent='Could not save: '+err.message;}finally{button.disabled=false;}});
      return;
     }
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
     records.innerHTML='<div class="card" style="margin:10px 0"><strong>Create configuration record</strong><p class="muted">Paste the JSON object required by the selected application and resource. Use id 0 or omit id. Secret values are not returned to the browser.</p><textarea id="new-config-json" rows="7" spellcheck="false" style="width:100%;background:#0b1322;color:#dce7f8;border:1px solid #34435d;border-radius:9px;padding:10px;font:12px ui-monospace,monospace">{}</textarea><div class="actions" style="margin-top:10px"><button id="create-config">Create record</button></div><div id="create-config-status" class="muted" style="margin-top:8px"></div></div>'+items.map((item,i)=>'<details class="card" style="margin:10px 0"><summary style="cursor:pointer"><strong>'+esc(item.name||item.host||item.path||resource+' #'+(item.id??i))+'</strong> <span class="muted">ID '+esc(item.id??'—')+'</span></summary><div data-config-form="'+i+'" style="margin-top:12px">'+configFields(item)+'</div><div class="actions" style="margin-top:10px"><button data-save-config='+i+' data-id="'+esc(item.id)+'">Save changes</button><button data-delete-config data-id="'+esc(item.id)+'" data-label="'+esc(item.name||item.host||item.path||resource+' #'+item.id)+'" style="border-color:#75404a">Preview delete</button></div></details>').join('');
     $('create-config').addEventListener('click',async()=>{
      const status=$('create-config-status'),button=$('create-config');
      try{
       const item=JSON.parse($('new-config-json').value);
       if(!item||typeof item!=='object'||Array.isArray(item))throw new Error('The new record must be a JSON object.');
       if(item.id!==undefined&&item.id!==0&&item.id!==null)throw new Error('For a new record, omit id or set it to 0.');
       if(!confirm('Create this '+resource+' record in '+service+'?'))return;
       button.disabled=true;
       await request('/web-api/settings/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service,resource,item})});
       status.textContent='Record created. Reloading configuration…';
       $('load-settings').click();
      }catch(err){status.textContent='Could not create record: '+err.message;}
      finally{button.disabled=false;}
     });
     records.querySelectorAll('[data-delete-config]').forEach(button=>button.addEventListener('click',async()=>{
      const id=Number(button.dataset.id);
      if(!Number.isInteger(id)||id<1){alert('Invalid record ID.');return;}
      button.disabled=true;
      try{
       const preview=await request('/web-api/settings/preview-delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service,resource,id})});
       if(!confirm('Deletion preview for '+service+' '+resource+' #'+id+' ('+button.dataset.label+'):\n'+JSON.stringify(preview.summary||{},null,2)))return;
       const typed=prompt('Type this exact confirmation to delete:\n'+preview.confirmation_text,'');
       if(typed!==preview.confirmation_text)return;
       await request('/web-api/settings/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service,resource,id,preview_token:preview.preview_token,typed_confirmation:typed})});
       $('load-settings').click();
      }catch(err){alert('Could not delete record: '+err.message);}
      finally{button.disabled=false;}
     }));
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
 if(view==='search-movies'||view==='search-series'||view==='search-artists'){
   const service=view==='search-movies'?'radarr':view==='search-series'?'sonarr':'lidarr';
   const label=service==='radarr'?'movies':service==='sonarr'?'series':'artists';
   html='<h3>Search '+label+'</h3><form id="catalog-search" class="actions" style="flex-wrap:wrap"><input id="catalog-term" placeholder="Enter a '+(service==='lidarr'?'artist':'title')+'…" required style="min-width:240px;flex:1;background:#0e1728;border:1px solid #34435d;border-radius:9px;padding:10px;color:#e8edf5"><button>Search</button></form><div id="catalog-results" style="margin-top:14px" class="muted">Search the metadata catalogue to add '+label+'.</div>';
   target.innerHTML=html;target.dataset.catalogService=service;return;
 }
 if(view==='movies'||view==='series'||view==='artists'){
 const service=view==='movies'?'radarr':view==='series'?'sonarr':'lidarr';
 const [library,setup]=await Promise.all([
  request('/web-api/library?service='+service),
  request('/web-api/setup?service='+service)
 ]);
 const profiles=setup.quality_profiles||[];
 if(service==='lidarr'){
  const metadataProfiles=setup.metadata_profiles||[];
  const rows=(library||[]).map(x=>{
   const qualityOptions=profiles.map(p=>'<option value="'+esc(p.id)+'"'+(Number(p.id)===Number(x.qualityProfileId)?' selected':'')+'>'+esc(p.name)+'</option>').join('');
   const metadataOptions=metadataProfiles.map(p=>'<option value="'+esc(p.id)+'"'+(Number(p.id)===Number(x.metadataProfileId)?' selected':'')+'>'+esc(p.name)+'</option>').join('');
   return '<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.artistName)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d"><input type="checkbox" data-library-monitored style="width:auto;margin:0" '+(x.monitored?'checked':'')+'></td><td style="padding:10px;border-bottom:1px solid #25344d"><select data-library-profile style="max-width:150px;background:#0e1728;color:#e8edf5;padding:7px;border:1px solid #34435d;border-radius:8px">'+qualityOptions+'</select></td><td style="padding:10px;border-bottom:1px solid #25344d"><select data-library-metadata-profile style="max-width:150px;background:#0e1728;color:#e8edf5;padding:7px;border:1px solid #34435d;border-radius:8px">'+metadataOptions+'</select></td><td style="padding:10px;border-bottom:1px solid #25344d"><button data-library-save data-service="lidarr" data-id="'+esc(x.id)+'">Save</button> <button data-artist-albums data-id="'+esc(x.id)+'">Albums</button></td></tr>';
  });
  html='<h3>Music · Artists <span class="muted">('+((library||[]).length)+')</span></h3><p class="muted">Manage artist monitoring and quality/metadata profiles. Open Albums to manage releases and monitoring.</p>'+table(['Artist','Status','Monitored','Quality profile','Metadata profile','Actions'],rows)+'<div id="artist-albums" style="margin-top:16px"></div>';
 }else{
  const rows=(library||[]).map(x=>{
   const options=profiles.map(p=>'<option value="'+esc(p.id)+'"'+(Number(p.id)===Number(x.qualityProfileId)?' selected':'')+'>'+esc(p.name)+'</option>').join('');
   return '<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.title||x.titleSlug)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.year||x.yearStart)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d"><input type="checkbox" data-library-monitored style="width:auto;margin:0" '+(x.monitored?'checked':'')+'></td><td style="padding:10px;border-bottom:1px solid #25344d"><select data-library-profile style="max-width:190px;background:#0e1728;color:#e8edf5;padding:7px;border:1px solid #34435d;border-radius:8px">'+options+'</select></td><td style="padding:10px;border-bottom:1px solid #25344d"><button data-library-save data-service="'+service+'" data-id="'+esc(x.id)+'">Save</button> <button data-library-releases data-service="'+service+'" data-id="'+esc(x.id)+'">Search releases</button></td></tr>';
  });
  html='<h3>'+ (view==='movies'?'Movies':'Series') +' <span class="muted">('+((library||[]).length)+')</span></h3><p class="muted">Change monitoring and quality profile per title, or search and grab a release.</p>'+table(['Title','Year','Status','Monitored','Quality profile','Actions'],rows)+'<div id="release-results" style="margin-top:16px"></div>';
 }
}
 else if(view==='radarr-queue'||view==='sonarr-queue'||view==='lidarr-queue'){
  const service=view==='radarr-queue'?'radarr':view==='sonarr-queue'?'sonarr':'lidarr';
  data=await request('/web-api/queue?service='+service);const records=data.records||[];
  const rows=records.map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.title||x.album?.title)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.artist?.artistName||x.series?.title)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.trackedDownloadStatus)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.errorMessage)+'</td></tr>');
  html='<h3>'+service+' queue <span class="muted">('+records.length+')</span></h3>'+table(['Album / title','Artist','Status','Import state','Message'],rows);
 }else if(view==='lidarr-history'||view==='lidarr-missing'){
  const history=view==='lidarr-history';data=await request(history?'/web-api/history?service=lidarr':'/web-api/missing?service=lidarr');
  const records=data.records||[];const rows=records.map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.album?.title||x.sourceTitle||x.title)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.artist?.artistName)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.eventType||x.status)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.date||x.added)+'</td></tr>');
  html='<h3>'+(history?'Lidarr history':'Missing albums')+' <span class="muted">('+records.length+')</span></h3>'+table(['Album','Artist','Event / status','Date'],rows);
 }
 else if(view==='downloads'){data=await request('/web-api/torrents');const rows=(data||[]).map(x=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.name)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.state)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.progress===undefined?'—':Math.round(x.progress*100)+'%')+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(x.category)+'</td><td style="padding:10px;border-bottom:1px solid #25344d"><input data-torrent-category value="'+esc(x.category||'')+'" aria-label="Torrent category" style="width:110px;margin:0;padding:6px"><button data-torrent-set-category data-hash="'+esc(x.hash)+'">Set</button></td><td style="padding:10px;border-bottom:1px solid #25344d"><button data-torrent-action="pause" data-hash="'+esc(x.hash)+'">Pause</button> <button data-torrent-action="resume" data-hash="'+esc(x.hash)+'">Resume</button> <button data-torrent-delete data-hash="'+esc(x.hash)+'" data-name="'+esc(x.name)+'">Preview remove</button></td></tr>');html='<h3>Active downloads <span class="muted">('+rows.length+')</span></h3><p class="muted">Removing a torrent keeps its downloaded files by default. A preview and exact confirmation are required.</p>'+table(['Name','State','Progress','Category','Set category','Controls'],rows);}
 target.innerHTML=html||'<div class="muted">No records found.</div>';
 }catch(e){target.innerHTML='<div class="error">'+esc(e.message)+'</div>';}}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>openView(b.dataset.view)));
$('workspace').addEventListener('submit',async e=>{
 if(e.target.id==='scryer-title-search'){
  e.preventDefault();const out=$('scryer-title-results'),search=$('scryer-title-query').value.trim(),facet=$('scryer-title-facet').value;
  out.textContent='Searching Scryer…';$('scryer-delete-preview').textContent='';
  try{const result=await request('/web-api/scryer/titles?limit=50&search='+encodeURIComponent(search)+'&facet='+encodeURIComponent(facet));renderScryerTitles(result);}
  catch(err){out.innerHTML='<div class="error">'+esc(err.message)+'</div>';}
  return;
 }
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
   const id=service==='radarr'?item.tmdbId:service==='sonarr'?item.tvdbId:item.foreignArtistId;
   const artistName=service==='lidarr'?item.artistName:'';
   const name=esc(service==='lidarr'?item.artistName:item.title||item.titleSlug||'Untitled'),year=esc(item.year||item.yearStart||'');
   const rootOptions=roots.map(x=>'<option value="'+esc(x.path)+'">'+esc(x.path)+'</option>').join('');
   const profileOptions=profiles.map(x=>'<option value="'+esc(x.id)+'">'+esc(x.name)+'</option>').join('');
   const metadataOptions=(setup.metadata_profiles||[]).map(x=>'<option value="'+esc(x.id)+'">'+esc(x.name)+'</option>').join('');
   const extra=service==='lidarr'?'<select data-metadata-profile style="max-width:220px;background:#0e1728;color:#e8edf5;padding:8px;border:1px solid #34435d;border-radius:8px">'+metadataOptions+'</select>':'';
   return '<article class="card" '+(service==='lidarr'?'data-artist-name="'+esc(artistName)+'" ':'')+'style="margin:10px 0"><div class="cardtop"><div class="name">'+name+' <span class="muted">'+year+'</span></div><span class="muted">'+(id?'ID '+esc(id):'No external ID')+'</span></div><div class="version">'+esc(item.disambiguation||item.overview||'')+'</div>'+(id?'<div class="actions" style="flex-wrap:wrap;margin-top:12px"><select data-root style="max-width:250px;background:#0e1728;color:#e8edf5;padding:8px;border:1px solid #34435d;border-radius:8px">'+rootOptions+'</select><select data-profile style="max-width:220px;background:#0e1728;color:#e8edf5;padding:8px;border:1px solid #34435d;border-radius:8px">'+profileOptions+'</select>'+extra+'<label class="muted"><input type="checkbox" data-search-now> Search immediately</label><button data-add-title data-service="'+service+'" data-id="'+esc(id)+'">Add to '+service+'</button></div>':'')+'</article>';
  }).join('');
 }catch(err){out.innerHTML='<div class="error">'+esc(err.message)+'</div>';}
});
 $('workspace').addEventListener('click',async e=>{
  const previewButton=e.target.closest('[data-scryer-delete-preview]');
  if(previewButton){previewButton.disabled=true;const out=$('scryer-delete-preview');out.textContent='Preparing deletion preview…';try{const result=await request('/web-api/scryer/delete-title/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title_id:previewButton.dataset.titleId})});if(result.errors?.length)throw new Error(result.errors.map(x=>x.message).join('; '));const p=result.data?.deleteTitlePreview;if(!p)throw new Error('Scryer did not return a deletion preview.');const expected=p.typedConfirmationPrompt||p.targetLabel||'';out.innerHTML='<article class="card"><div class="name">Preview: '+esc(previewButton.dataset.titleName)+'</div><p class="muted">'+esc(p.totalFileCount)+' files · '+esc(p.mediaCount)+' media · '+esc(p.subtitleCount)+' subtitles · '+esc(p.imageCount)+' images · '+esc(p.directoryCount)+' directories</p><p class="muted">Sample paths: '+esc((p.samplePaths||[]).join(' · ')||'none')+'</p><label class="muted">Type exactly: <strong>'+esc(expected)+'</strong><input id="scryer-delete-confirmation" autocomplete="off" style="max-width:480px"></label><label class="muted" style="display:block"><input id="scryer-delete-files" type="checkbox" style="width:auto"> Delete media files from disk too</label><button data-scryer-delete-confirm data-title-id="'+esc(previewButton.dataset.titleId)+'" data-title-name="'+esc(previewButton.dataset.titleName)+'" data-fingerprint="'+esc(p.fingerprint)+'" data-expected="'+esc(expected)+'">Confirm title deletion</button></article>';}catch(err){out.innerHTML='<div class="error">'+esc(err.message)+'</div>';previewButton.disabled=false;}return;}
  const deleteButton=e.target.closest('[data-scryer-delete-confirm]');
  if(deleteButton){const typed=$('scryer-delete-confirmation').value,deleteFiles=$('scryer-delete-files').checked;if(typed!==deleteButton.dataset.expected){alert('The confirmation text does not match the preview.');return;}if(!confirm('Delete '+deleteButton.dataset.titleName+' from Scryer'+(deleteFiles?' and remove its media files from disk':'')+'?'))return;deleteButton.disabled=true;try{const result=await request('/web-api/scryer/delete-title',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title_id:deleteButton.dataset.titleId,preview_fingerprint:deleteButton.dataset.fingerprint,typed_confirmation:typed,delete_files_on_disk:deleteFiles})});if(result.errors?.length)throw new Error(result.errors.map(x=>x.message).join('; '));$('scryer-delete-preview').innerHTML='<div class="info">Deletion accepted: '+esc(JSON.stringify(result.data?.deleteTitle||result))+'</div>';await openView('scryer-titles');}catch(err){alert('Deletion was not completed: '+err.message);deleteButton.disabled=false;}return;}
  const dockerButton=e.target.closest('[data-docker-action]');
  if(dockerButton){const action=dockerButton.dataset.dockerAction,container=dockerButton.dataset.container;if(!confirm(action+' allowlisted container '+container+'?'))return;dockerButton.disabled=true;try{await request('/web-api/docker/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({container,action})});await openView('docker');}catch(err){alert(err.message);dockerButton.disabled=false;}return;}
 });
 $('workspace').addEventListener('click',async e=>{const remove=e.target.closest('[data-torrent-delete]');if(!remove)return;e.preventDefault();e.stopImmediatePropagation();remove.disabled=true;try{const preview=await request('/web-api/torrents/delete-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hashes:remove.dataset.hash,delete_files:false})});const detail=(preview.items||[]).map(x=>x.name+' · '+x.state+' · '+x.save_path).join('\n');if(!confirm('qBittorrent deletion preview (downloaded files will be kept):\n'+detail))return;const typed=prompt('Type this exact confirmation to remove the torrent:\n'+preview.confirmation_text,'');if(typed!==preview.confirmation_text)return;await request('/web-api/torrents/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hashes:remove.dataset.hash,delete_files:false,preview_token:preview.preview_token,typed_confirmation:typed})});await openView('downloads');}catch(err){alert('Could not remove torrent: '+err.message);}finally{remove.disabled=false;}},true);
$('workspace').addEventListener('click',async e=>{const add=e.target.closest('[data-add-title]');if(add){const card=add.closest('.card');const service=add.dataset.service,id=add.dataset.id;if(!confirm('Add this title to '+service+'?'))return;add.disabled=true;try{const body={service,root_folder_path:card.querySelector('[data-root]').value,quality_profile_id:Number(card.querySelector('[data-profile]').value),monitored:true,search_now:card.querySelector('[data-search-now]').checked};if(service==='radarr')body.tmdb_id=Number(id);else if(service==='sonarr')body.tvdb_id=Number(id);else{body.foreign_artist_id=id;body.artist_name=card.dataset.artistName;body.metadata_profile_id=Number(card.querySelector('[data-metadata-profile]').value);}await request('/web-api/catalog/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});add.textContent='Added';}catch(err){alert(err.message);add.disabled=false;}return;}const category=e.target.closest('[data-torrent-set-category]');if(category){const row=category.closest('tr'),value=row.querySelector('[data-torrent-category]').value.trim();if(!value){alert('Enter a category name.');return;}category.disabled=true;try{await request('/web-api/torrents/category',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hashes:category.dataset.hash,category:value})});category.textContent='Saved';}catch(err){alert(err.message);category.disabled=false;}return;}const remove=e.target.closest('[data-torrent-delete]');if(remove){if(!confirm('Remove this torrent from qBittorrent? Downloaded files will be kept.'))return;remove.disabled=true;try{await request('/web-api/torrents/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hashes:remove.dataset.hash,delete_files:false})});await openView('downloads');}catch(err){alert(err.message);remove.disabled=false;}return;}const b=e.target.closest('[data-torrent-action]');if(!b)return;const action=b.dataset.torrentAction;const verb=action==='pause'?'pause':'resume';if(!confirm('Are you sure you want to '+verb+' this torrent?'))return;b.disabled=true;try{await request('/web-api/torrents/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,hashes:b.dataset.hash})});await openView('downloads');}catch(err){alert(err.message);b.disabled=false;}});
$('workspace').addEventListener('click',async e=>{
 const artistAlbums=e.target.closest('[data-artist-albums]');
 if(artistAlbums){
  const out=$('artist-albums');out.innerHTML='<div class="muted">Loading albums…</div>';artistAlbums.disabled=true;
  try{
   const albums=await request('/web-api/albums?artist_id='+artistAlbums.dataset.id);
   const rows=(albums||[]).map(album=>'<tr><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(album.title)+'</td><td style="padding:10px;border-bottom:1px solid #25344d">'+cell(album.releaseDate)+'</td><td style="padding:10px;border-bottom:1px solid #25344d"><input type="checkbox" data-album-monitored style="width:auto;margin:0" '+(album.monitored?'checked':'')+'></td><td style="padding:10px;border-bottom:1px solid #25344d"><button data-album-save data-id="'+esc(album.id)+'">Save</button> <button data-library-releases data-service="lidarr" data-id="'+esc(album.id)+'">Search releases</button></td></tr>');
   out.innerHTML='<h3>Albums <span class="muted">('+rows.length+')</span></h3>'+table(['Album','Release date','Monitored','Actions'],rows)+'<div id="release-results" style="margin-top:14px"></div>';
  }catch(err){out.innerHTML='<div class="error">'+esc(err.message)+'</div>';}
  finally{artistAlbums.disabled=false;}
  return;
 }
 const albumSave=e.target.closest('[data-album-save]');
 if(albumSave){
  const row=albumSave.closest('tr'),monitored=row.querySelector('[data-album-monitored]').checked;
  if(!confirm('Save album monitoring?'))return;albumSave.disabled=true;
  try{await request('/web-api/albums/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:Number(albumSave.dataset.id),monitored})});albumSave.textContent='Saved';}
  catch(err){alert(err.message);albumSave.disabled=false;}return;
 }
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
 const metadataProfile=row.querySelector('[data-library-metadata-profile]');
 const body={service:button.dataset.service,id:Number(button.dataset.id),monitored:row.querySelector('[data-library-monitored]').checked};
 if(profile&&profile.value)body.quality_profile_id=Number(profile.value);
 if(metadataProfile&&metadataProfile.value)body.metadata_profile_id=Number(metadataProfile.value);
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


class HomeLabPilotWebMiddleware:
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
            if method == "POST":
                fetch_site = headers.get(b"sec-fetch-site", b"").lower()
                origin = headers.get(b"origin", b"").decode("latin1")
                host = headers.get(b"host", b"").decode("latin1")
                if fetch_site == b"cross-site" or (
                    origin and host and urlsplit(origin).netloc.lower() != host.lower()
                ):
                    await self._respond(send, 403, b'{"error":"Cross-origin request rejected"}')
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

