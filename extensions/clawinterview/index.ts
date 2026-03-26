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

async function runClawinterviewCli(api, args) {
  const repoRoot = resolveRepoRoot(api);
  const pythonBin = resolvePythonBin(api);
  const timeoutMs = resolveTimeoutMs(api);

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

export function register(api) {
  api.registerTool(
    {
      name: "clawinterview",
      description:
        "Compile, validate, or run scaffold interview contracts for pipelines and targets.",
      parameters: {
        type: "object",
        additionalProperties: false,
        properties: {
          action: {
            type: "string",
            enum: ["compile", "validate", "run"],
            description: "Action to perform: compile (build contracts for a pipeline), validate (check a target's contract), or run (execute interview for a pipeline).",
          },
          pipeline_path: {
            type: "string",
            description:
              "Path to the pipeline config (required for compile and run actions).",
          },
          target_path: {
            type: "string",
            description:
              "Path to the target whose interview contract should be validated (required for validate action).",
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
            return textResult(await runClawinterviewCli(api, args));
          }

          case "validate": {
            if (!params.target_path) {
              return textResult({
                status: "error",
                error: "target_path is required for validate action",
              });
            }
            const args = ["validate", "--target", String(params.target_path)];
            return textResult(await runClawinterviewCli(api, args));
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
            return textResult(await runClawinterviewCli(api, args));
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

  console.log("[clawinterview] tool registered");
}

export function activate(api) {
  register(api);
}

export default { register, activate };
