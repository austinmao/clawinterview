// @ts-nocheck
/**
 * clawinterview — OpenClaw gateway bridge plugin
 *
 * Thin Node.js wrapper that registers a `clawinterview` tool with the gateway
 * and delegates all calls to the Python CLI via child_process.execFile.
 *
 * Actions: compile, validate, run
 */

import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

function defaultRepoRoot() {
  return process.env.OPENCLAW_WORKSPACE || process.cwd();
}

function resolveRepoRoot(api) {
  const config = (api.pluginConfig ?? {});
  if (typeof config.repoRoot === "string" && config.repoRoot.trim()) {
    return path.resolve(config.repoRoot.trim());
  }
  return defaultRepoRoot();
}

function resolvePythonBin(api) {
  const config = (api.pluginConfig ?? {});
  if (typeof config.pythonBin === "string" && config.pythonBin.trim()) {
    return config.pythonBin.trim();
  }
  const repoRoot = resolveRepoRoot(api);
  return path.join(repoRoot, "clawpipe", ".venv", "bin", "python");
}

function resolveTimeoutMs(api) {
  const config = (api.pluginConfig ?? {});
  if (typeof config.timeoutMs === "number" && Number.isFinite(config.timeoutMs)) {
    return config.timeoutMs;
  }
  return 60_000;
}

function textResult(payload) {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(payload),
      },
    ],
  };
}

async function runClawinterviewCli(pythonBin, repoRoot, timeoutMs, args) {
  const { stdout, stderr } = await execFileAsync(
    pythonBin,
    ["-m", "clawinterview", ...args],
    {
      cwd: repoRoot,
      timeout: timeoutMs,
      maxBuffer: 2 * 1024 * 1024,
      env: {
        ...process.env,
        PYTHONPATH: path.join(repoRoot, "clawinterview", "src"),
      },
    },
  );

  const raw = stdout.trim();
  if (!raw) {
    throw new Error(
      `clawinterview CLI returned empty stdout${stderr ? ` (${stderr.trim()})` : ""}`,
    );
  }

  try {
    return JSON.parse(raw);
  } catch {
    throw new Error(
      `clawinterview CLI returned non-JSON: ${raw.slice(0, 500)}${stderr ? ` stderr: ${stderr.trim()}` : ""}`,
    );
  }
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString())); }
      catch { resolve({}); }
    });
    req.on("error", reject);
  });
}

export function register(api) {
  const repoRoot = resolveRepoRoot(api);
  const pythonBin = resolvePythonBin(api);
  const timeoutMs = resolveTimeoutMs(api);

  // Legacy helper that uses api closure (kept for tool handler backward compat)
  async function runCliLegacy(args) {
    return runClawinterviewCli(pythonBin, repoRoot, timeoutMs, args);
  }

  api.registerTool(
    {
      name: "clawinterview",
      description:
        "Interview engine for pipeline intake. Use 'start' to begin a multi-turn brainstorming interview (returns first question as JSON), then 'respond' with the operator's answer to advance. Each respond call returns the next question or 'complete' status with the assembled brief. Also supports 'compile', 'validate', and 'run'.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          action: {
            type: "string",
            enum: ["compile", "validate", "run", "start", "respond"],
            description: "Action to perform: compile, validate, run, start (begin multi-turn interview, returns JSON with first question), or respond (continue interview with operator answer).",
          },
          pipeline_path: {
            type: "string",
            description:
              "Path to the pipeline config (required for compile, run, and start actions).",
          },
          target_path: {
            type: "string",
            description:
              "Path to the target whose interview contract should be validated (required for validate action).",
          },
          run_id: {
            type: "string",
            description:
              "Run ID from a previous start call (required for respond action).",
          },
          response: {
            type: "string",
            description:
              "Operator's answer to the current interview question (required for respond action).",
          },
          pipeline_args: {
            type: "object",
            description:
              "Key-value args to pre-fill interview inputs (optional for start action).",
            additionalProperties: { type: "string" },
          },
          accept_recommendations: {
            type: "boolean",
            description:
              "For run: automatically accept scaffold recommendations without prompting.",
          },
        },
        required: ["action"],
      },
      async execute(_id, params) {
        const action = String(params.action);

        switch (action) {
          case "compile": {
            if (!params.pipeline_path) {
              return textResult({
                status: "error",
                error: "pipeline_path is required for compile action",
              });
            }
            const args = ["compile", "--pipeline", String(params.pipeline_path)];
            return textResult(await runCliLegacy(args));
          }

          case "validate": {
            if (!params.target_path) {
              return textResult({
                status: "error",
                error: "target_path is required for validate action",
              });
            }
            const args = ["validate", "--target", String(params.target_path)];
            return textResult(await runCliLegacy(args));
          }

          case "run": {
            if (!params.pipeline_path) {
              return textResult({
                status: "error",
                error: "pipeline_path is required for run action",
              });
            }
            const args = ["run", "--pipeline", String(params.pipeline_path)];
            if (params.accept_recommendations === true) {
              args.push("--accept-recommendations");
            }
            return textResult(await runCliLegacy(args));
          }

          case "start": {
            if (!params.pipeline_path) {
              return textResult({
                status: "error",
                error: "pipeline_path is required for start action",
              });
            }
            const startArgs = ["start", String(params.pipeline_path)];
            if (params.pipeline_args && typeof params.pipeline_args === "object") {
              for (const [k, v] of Object.entries(params.pipeline_args)) {
                startArgs.push("--args", `${k}=${v}`);
              }
            }
            return textResult(await runCliLegacy(startArgs));
          }

          case "respond": {
            if (!params.run_id || !params.response) {
              return textResult({
                status: "error",
                error: "run_id and response are required for respond action",
              });
            }
            const respondArgs = ["respond", String(params.run_id), String(params.response)];
            return textResult(await runCliLegacy(respondArgs));
          }

          default:
            return textResult({
              status: "error",
              error: `Unknown action: ${action}`,
            });
        }
      },
    },
    { optional: true },
  );

  // --- HTTP webhook routes ---

  api.registerHttpRoute({
    path: "/clawinterview/compile",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const body = await readBody(req);
      const args = ["compile"];
      if (body.pipeline_path) args.push("--pipeline", String(body.pipeline_path));
      try {
        const result = await runClawinterviewCli(pythonBin, repoRoot, timeoutMs, args);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  api.registerHttpRoute({
    path: "/clawinterview/validate",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const body = await readBody(req);
      const args = ["validate"];
      if (body.target_path) args.push("--target", String(body.target_path));
      try {
        const result = await runClawinterviewCli(pythonBin, repoRoot, timeoutMs, args);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  api.registerHttpRoute({
    path: "/clawinterview/run",
    auth: "gateway",
    match: "exact",
    handler: async (req, res) => {
      const body = await readBody(req);
      const args = ["run"];
      if (body.target_path) args.push("--pipeline", String(body.target_path));
      if (body.pipeline_id) args.push("--pipeline-id", String(body.pipeline_id));
      try {
        const result = await runClawinterviewCli(pythonBin, repoRoot, timeoutMs, args);
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err) {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ status: "error", error: err.message }));
      }
    },
  });

  console.log("[clawinterview] tool + 3 HTTP routes registered");
}

export function activate(api) {
  register(api);
}

export default { register, activate };
