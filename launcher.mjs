// Supervise the render worker and eve together; platform restarts the whole unit.
import { spawn } from 'node:child_process';
import { mkdir, rm, symlink } from 'node:fs/promises';
import { resolve } from 'node:path';
const root=process.cwd(),data=resolve(process.env.K1N_DATA_DIR || 'data');
await mkdir(data,{recursive:true});await mkdir(resolve(data,'workflow'),{recursive:true});await mkdir(resolve(root,'.eve'),{recursive:true});
const workflow=resolve(root,'.eve/.workflow-data');
if(data!==resolve(root,'data')){await rm(workflow,{recursive:true,force:true});await symlink(resolve(data,'workflow'),workflow,'dir');}
const children=[spawn('python3',['core/engine.py','worker'],{stdio:'inherit'}),spawn('node',['node_modules/eve/bin/eve.js','start','--host','0.0.0.0'],{stdio:'inherit'})];
let stopping=false;
function stop(code=0){if(stopping)return;stopping=true;for(const c of children)c.kill('SIGTERM');setTimeout(()=>process.exit(code),5000).unref();}
for(const c of children){c.on('error',()=>stop(1));c.on('exit',code=>stop(code||0));}
process.on('SIGTERM',()=>stop());process.on('SIGINT',()=>stop());
