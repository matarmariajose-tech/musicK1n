import { defineAgent } from "eve";

const contextWindowTokens = Number(process.env.K1N_MODEL_CONTEXT_TOKENS || 32000);
if (!Number.isSafeInteger(contextWindowTokens) || contextWindowTokens < 4096) {
  throw new Error("K1N_MODEL_CONTEXT_TOKENS debe ser un entero de al menos 4096");
}

export default defineAgent({
  defaultTools: false,
  model: process.env.K1N_MODEL || "openai/gpt-6-luna-fast",
  modelContextWindowTokens: contextWindowTokens,
  reasoning: "high",
});
