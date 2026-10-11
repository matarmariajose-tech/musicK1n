import { defineTool } from 'eve/tools';
import { z } from 'zod';
import { rpc } from '../lib/engine.js';
export default defineTool({
 description:'Consulta el catálogo, experimentos y resultados reales para proponer próximos experimentos. No publica ni cambia datos.',
 inputSchema:z.object({action:z.enum(['overview','report'])}),
 async execute({action}){return rpc(action);}
});
