import { defineTool } from "eve/tools";
import { z } from "zod";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
const run = promisify(execFile);
export default defineTool({
 description: "Lee el catálogo, crea borradores sobre segmentos cargados o evalúa experimentos. No publica.",
 inputSchema: z.object({ action: z.enum(["catalog", "plan", "evaluate"]) }),
 async execute({ action }) {
  const root = resolve(process.env.K1N_PROJECT_ROOT || process.cwd());
  if (action === "catalog") return JSON.parse(await readFile(resolve(root, "catalog.json"), "utf8"));
  const { stdout } = await run("python3", [resolve(root, "core/growth.py"), action], { cwd: root, timeout: 15000, maxBuffer: 1048576 });
  return JSON.parse(stdout);
 }
});
