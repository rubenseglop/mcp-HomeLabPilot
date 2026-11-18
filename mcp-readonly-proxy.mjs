import http from "node:http";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { timingSafeEqual } from "node:crypto";

const PORT = Number(process.env.MCP_PROXY_PORT || 8001);
const TARGET = (process.env.HOMELABPILOT_MCP_URL || "http://homelabpilot:8000/mcp").replace(/\/$/, "");
const TOKEN = process.env.MCP_AUTH_TOKEN || "";
const READ_ONLY_TOOLS = /^(stack_status|integration_catalog|scryer_introspect|arr_search_catalog|[a-z0-9]+_(get|list|search|status|schema|introspect|catalog)(_|$))/;

function safeEqual(a,b){const x=Buffer.from(String(a)),y=Buffer.from(String(b));return x.length===y.length&&timingSafeEqual(x,y);}
function json(res,status,body){const data=Buffer.from(JSON.stringify(body));res.writeHead(status,{"content-type":"application/json","content-length":data.length,"cache-control":"no-store"});res.end(data);}
const server=http.createServer(async(req,res)=>{
  if(TOKEN.length<32){json(res,503,{error:"MCP proxy is not configured"});return;}
  if(req.url==="/health"){json(res,200,{ok:true,mode:"read-only"});return;}
  if(!req.url.startsWith("/mcp")){json(res,404,{error:"Not found"});return;}
  try{
    const chunks=[];for await(const chunk of req)chunks.push(chunk);
    const body=Buffer.concat(chunks);
    let rpc=null;
    if(req.method==="POST"&&body.length){
      try{rpc=JSON.parse(body.toString("utf8"));}catch{}
      const calls=Array.isArray(rpc)?rpc:[rpc];
      for(const call of calls){
        if(call?.method==="tools/call"){
          const name=String(call.params?.name||"");
          if(!READ_ONLY_TOOLS.test(name)){
            json(res,200,{jsonrpc:"2.0",id:call.id??null,error:{code:-32003,message:"This HomeLabPilot Codex connection is read-only. Mutating tools are not exposed."}});
            return;
          }
        }
      }
    }
    const headers={};
    for(const [key,value] of Object.entries(req.headers)){
      if(["host","content-length","connection","authorization"].includes(key.toLowerCase()))continue;
      if(typeof value==="string")headers[key]=value;
    }
    headers.authorization="Bearer "+TOKEN;
    const upstream=await fetch(TARGET,{
      method:req.method,
      headers,
      body:["GET","HEAD"].includes(req.method)?undefined:body,
      redirect:"manual"
    });
    const responseHeaders={};
    for(const [key,value] of upstream.headers){
      if(["transfer-encoding","connection","content-length"].includes(key.toLowerCase()))continue;
      responseHeaders[key]=value;
    }
    if(req.method==="POST"&&rpc&&!Array.isArray(rpc)&&rpc.method==="tools/list"&&upstream.headers.get("content-type")?.includes("application/json")){
      const data=await upstream.json();
      if(Array.isArray(data.result?.tools))data.result.tools=data.result.tools.filter(tool=>READ_ONLY_TOOLS.test(String(tool.name||"")));
      const out=Buffer.from(JSON.stringify(data));
      res.writeHead(upstream.status,{...responseHeaders,"content-length":out.length,"cache-control":"no-store"});res.end(out);return;
    }
    res.writeHead(upstream.status,responseHeaders);
    if(upstream.body)await pipeline(Readable.fromWeb(upstream.body),res);else res.end();
  }catch(err){if(!res.headersSent)json(res,502,{error:"MCP upstream unavailable"});else res.destroy(err);}
});
server.listen(PORT,"0.0.0.0",()=>process.stdout.write("Read-only MCP proxy listening on "+PORT+"\n"));
