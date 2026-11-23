import http from "node:http";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { timingSafeEqual } from "node:crypto";
import { isReadOnlyTool, filterToolsListPayload } from "./mcp-readonly-policy.mjs";

const PORT = Number(process.env.MCP_PROXY_PORT || 8001);
const TARGET = (process.env.HOMELABPILOT_MCP_URL || "http://homelabpilot:8000/mcp").replace(/\/$/, "");
const TOKEN = process.env.MCP_AUTH_TOKEN || "";

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
      const denied=calls.filter(call=>call?.method==="tools/call"&&!isReadOnlyTool(call.params?.name));
      if(denied.length){
        const rejected=calls.map(call=>({
          jsonrpc:"2.0",
          id:call?.id??null,
          error:{
            code:-32003,
            message:call?.method==="tools/call"&&!isReadOnlyTool(call.params?.name)
              ? "This HomeLabPilot connection is read-only. The requested tool is not explicitly approved."
              : "The JSON-RPC batch was rejected because it contains a non-approved tool call."
          }
        }));
        json(res,200,Array.isArray(rpc)?rejected:rejected[0]);
        return;
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
    if(req.method==="POST"&&rpc&&(rpc.method==="tools/list"||(Array.isArray(rpc)&&rpc.some(call=>call?.method==="tools/list")))){
      const contentType=upstream.headers.get("content-type")||"";
      if(contentType.includes("application/json")){
        const data=await upstream.json();
        const filtered=filterToolsListPayload(data);
        const out=Buffer.from(JSON.stringify(filtered));
        res.writeHead(upstream.status,{...responseHeaders,"content-length":out.length,"cache-control":"no-store"});res.end(out);return;
      }
      if(contentType.includes("text/event-stream")){
        const source=await upstream.text();
        const events=source.split(/\r?\n\r?\n/);
        const filtered=events.map(event=>{
          const lines=event.split(/\r?\n/);
          const dataIndexes=[];
          for(let i=0;i<lines.length;i++)if(lines[i].startsWith("data:"))dataIndexes.push(i);
          if(!dataIndexes.length)return event;
          try{
            const payload=JSON.parse(dataIndexes.map(i=>lines[i].slice(5).trimStart()).join("\n"));
            const filtered=filterToolsListPayload(payload);
            if(filtered!==payload){
              lines[dataIndexes[0]]="data: "+JSON.stringify(filtered);
              for(const index of dataIndexes.slice(1).reverse())lines.splice(index,1);
            }
            return lines.join("\n");
          }catch{return event;}
        }).join("\n\n");
        const out=Buffer.from(filtered);
        res.writeHead(upstream.status,{...responseHeaders,"content-length":out.length,"cache-control":"no-store"});res.end(out);return;
      }
    }
    res.writeHead(upstream.status,responseHeaders);
    if(upstream.body)await pipeline(Readable.fromWeb(upstream.body),res);else res.end();
  }catch(err){if(!res.headersSent)json(res,502,{error:"MCP upstream unavailable"});else res.destroy(err);}
});
server.listen(PORT,"0.0.0.0",()=>process.stdout.write("Read-only MCP proxy listening on "+PORT+"\n"));
