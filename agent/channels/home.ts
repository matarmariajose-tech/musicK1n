import { defineChannel, GET, POST } from 'eve/channels';
import { operator } from '../lib/auth.js';
import { dataDirectory, project, rpc } from '../lib/engine.js';
import { readFile, mkdir, writeFile, unlink } from 'node:fs/promises';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
const headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
async function authorize(request:Request) {
 const principal=await operator(request);
 if (!principal) return new Response('Acceso restringido',{status:401,headers:{...headers,'WWW-Authenticate':'Basic realm="K1N", charset="UTF-8"'}});
 if (request.method==='POST') {
  const origin=request.headers.get('origin');
  if (origin && origin!==new URL(request.url).origin) return new Response('Origen inválido',{status:403});
 }
 return null;
}
async function limited(request:Request,limit:number) {
 const length=Number(request.headers.get('content-length') || 0);
 if(length>limit)throw new Error('Archivo demasiado grande');
 const reader=request.body?.getReader();if(!reader)return new Uint8Array();
 const chunks:Uint8Array[]=[];let size=0;
 while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>limit){await reader.cancel();throw new Error('Archivo demasiado grande');}chunks.push(value);}
 const out=new Uint8Array(size);let offset=0;for(const c of chunks){out.set(c,offset);offset+=c.length;}return out;
}
const actions=new Set(['track','experiment','render','approve','published','metrics','report','contact','spotify-sync','youtube-sync','upload-private','oauth-start']);
export default defineChannel({routes:[
 GET('/',async request=>{
  const denied=await authorize(request);if(denied)return denied;
  return new Response(await readFile(resolve(project,'web/index.html'),'utf8'),{headers:{...headers,'Content-Type':'text/html; charset=utf-8','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; media-src 'self' blob:; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"}});
 }),
 GET('/oauth/google/callback',async request=>{
  const denied=await authorize(request);if(denied)return denied;
  try {
   const query=new URL(request.url).searchParams;
   if(query.has('error'))throw new Error('Autorización cancelada');
   await rpc('oauth-finish',{code:query.get('code'),state:query.get('state')});
   return Response.redirect(new URL('/',request.url),303);
  }catch(err){return new Response(err instanceof Error?err.message:'No se pudo autorizar',{status:400,headers});}
 }),
 GET('/api/overview' ,async request=>{const denied=await authorize(request);if(denied)return denied;return Response.json(await rpc('overview'),{headers});}),
 POST('/api/ask',async(request,{from})=>{
  const denied=await authorize(request);if(denied)return denied;
  try {
   if(!process.env.AI_GATEWAY_API_KEY)throw new Error('Falta configurar AI_GATEWAY_API_KEY');
   const body=JSON.parse(new TextDecoder().decode(await limited(request,20000)));
   if(typeof body.message!=='string' || !body.message.trim() || body.message.length>10000)throw new Error('Mensaje inválido');
   const auth=await operator(request);
   const session=await from(randomUUID()).send(body.message,{auth:auth || null});
   return Response.json({sessionId:session.id},{headers});
  }catch(err){return Response.json({error:err instanceof Error?err.message:'No se pudo consultar el agente'},{status:400,headers});}
 }),
 POST('/api/action' ,async request=>{
  const denied=await authorize(request);if(denied)return denied;
  try {
   const input=JSON.parse(new TextDecoder().decode(await limited(request,2000000)));
   if(!actions.has(input.action))throw new Error('Acción inválida');
   return Response.json(await rpc(input.action,input.payload || {}),{headers});
  }catch(err){return Response.json({error:err instanceof Error?err.message:'Operación fallida'},{status:400,headers});}
 }),
 POST('/api/upload',async request=>{
  const denied=await authorize(request);if(denied)return denied;
  const id=randomUUID().replaceAll('-','');const path=resolve(dataDirectory,'uploads',id);
  try {
   const bytes=await limited(request,50*1024*1024);
   const kind=request.headers.get('x-asset-kind');if(!['audio','cover'].includes(kind || ''))throw new Error('Tipo inválido');
   await mkdir(resolve(dataDirectory,'uploads'),{recursive:true});await writeFile(path,bytes,{flag:'wx'});
   const result=await rpc('asset',{id,kind,name:decodeURIComponent(request.headers.get('x-file-name') || 'archivo')});
   return Response.json(result,{headers});
  }catch(err){await unlink(path).catch(()=>{});return Response.json({error:err instanceof Error?err.message:'Archivo inválido'},{status:400,headers});}
 }),
 GET('/media/:id',async(request,{params})=>{
  const denied=await authorize(request);if(denied)return denied;
  if(!/^[a-f0-9]{32}$/.test(params.id))return new Response('Id inválido',{status:400});
  try{return new Response(await readFile(resolve(dataDirectory,'clips',params.id+'.mp4')),{headers:{...headers,'Content-Type':'video/mp4','Content-Disposition':'inline; filename="K1N-'+params.id+'.mp4"'}});}catch{return new Response('Clip no encontrado',{status:404});}
 })
]});
