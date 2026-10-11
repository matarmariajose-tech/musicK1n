import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
export const project = resolve(process.env.K1N_PROJECT_ROOT || process.cwd());
export const dataDirectory = resolve(process.env.K1N_DATA_DIR || resolve(project, 'data'));
export function rpc(action: string, payload: Record<string, unknown> = {}): Promise<any> {
 return new Promise((accept, reject) => {
  const child = spawn('python3', [resolve(project, 'core/engine.py')], {cwd: project, stdio:['pipe','pipe','pipe']});
  let output=''; let bytes=0;
  const timer=setTimeout(()=>{child.kill('SIGKILL');reject(new Error('Operación excedió el tiempo máximo'));},120000);
  child.stdout.on('data',chunk=>{bytes+=chunk.length;if(bytes>4000000){child.kill();reject(new Error('Respuesta demasiado grande'));}else output+=chunk;});
  child.stderr.resume();
  child.on('error',err=>{clearTimeout(timer);reject(err);});
  child.on('close',code=>{clearTimeout(timer);try {const result=JSON.parse(output);if(code || result.error)reject(new Error(result.error || 'Operación fallida'));else accept(result);}catch {reject(new Error('El motor no pudo completar la operación'));}});
  child.stdin.on('error',()=>{});
  child.stdin.end(JSON.stringify({action,payload}));
 });
}
