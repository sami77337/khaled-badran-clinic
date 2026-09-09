"use strict";

// Test-only Chromium startup. Callers own the temporary profile directory and
// remove it after stop() has reaped the browser (including failed launches).
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

function browserArgs(profile, platform = process.platform, env = process.env) {
    const args = ["--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--remote-debugging-port=0",
        `--user-data-dir=${profile}`];
    // Hosted Ubuntu restricts Chromium's user-namespace sandbox. This exception
    // is only for isolated CI fixture pages; keep the local browser sandbox.
    if (platform === "linux" && (env.CI === "true" || env.GITHUB_ACTIONS === "true")) {
        args.push("--no-sandbox");
    }
    return [...args, "about:blank"];
}

async function launchBrowser(browser, profile, { timeoutMs = 15000, spawnProcess = spawn } = {}) {
    const child = spawnProcess(browser, browserArgs(profile), {
        windowsHide: true, stdio: ["ignore", "ignore", "pipe"],
    });
    let stderr = "", spawnError, exited = false, closed = false, exitCode, signal, ws;
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", data => { stderr = (stderr + data).slice(-8192); });
    child.on("error", error => { spawnError = error; });
    child.on("exit", (code, exitSignal) => {
        exited = true; exitCode = code; signal = exitSignal;
    });
    const completion = new Promise(resolve => child.once("close", () => { closed = true; resolve(); }));
    const deadline = Date.now() + timeoutMs;
    const diagnostic = message => new Error(`${message}\nBrowser: ${browser}\n` +
        `stderr (last 8192 characters): ${stderr.trim() || "(empty)"}`);
    const checkProcess = stage => {
        if (spawnError) throw diagnostic(`Could not start browser: ${spawnError.code || spawnError.message}.`);
        if (exited) throw diagnostic(`Browser exited ${stage}. Exit code: ${exitCode}; signal: ${signal || "none"}.`);
    };
    const stop = async () => {
        ws?.close();
        if (closed) return;
        if (child.pid && !exited) child.kill();
        await Promise.race([completion, delay(1000)]);
        if (!closed && child.pid) {
            child.kill("SIGKILL");
            await Promise.race([completion, delay(1000)]);
        }
        if (!closed) throw diagnostic("Browser did not stop within the cleanup timeout.");
    };

    try {
        const portFile = path.join(profile, "DevToolsActivePort");
        let port;
        while (Date.now() < deadline) {
            checkProcess("before creating DevToolsActivePort");
            try {
                const [value, endpoint] = fs.readFileSync(portFile, "utf8").trim().split(/\r?\n/);
                // The file can be observed between creation and the completed write.
                if (/^\d+$/.test(value) && Number(value) > 0 && Number(value) <= 65535 &&
                    endpoint?.startsWith("/devtools/browser/")) {
                    port = Number(value);
                    break;
                }
            } catch (error) {
                if (error.code !== "ENOENT") throw diagnostic(`Cannot read Chromium DevToolsActivePort: ${error.code || error.message}.`);
            }
            await delay(50);
        }
        checkProcess("before creating DevToolsActivePort");
        if (!port) throw diagnostic(`Timed out waiting for Chromium DevToolsActivePort after ${timeoutMs} ms.`);

        let target, endpointProblem = "CDP endpoint unavailable";
        while (Date.now() < deadline) {
            checkProcess("before the CDP endpoint became ready");
            try {
                const response = await fetch(`http://127.0.0.1:${port}/json/list`, {
                    signal: AbortSignal.timeout(Math.max(1, Math.min(1000, deadline - Date.now()))),
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const targets = await response.json();
                if (!Array.isArray(targets)) throw new Error("invalid target list");
                target = targets.find(item => item.type === "page" && item.webSocketDebuggerUrl);
                if (target) break;
                endpointProblem = "CDP page target missing";
            } catch (error) {
                endpointProblem = `CDP endpoint unavailable: ${error.message}`;
            }
            await delay(50);
        }
        checkProcess("before the CDP page target became ready");
        if (!target) throw diagnostic(`${endpointProblem}; startup timeout after ${timeoutMs} ms.`);
        ws = new WebSocket(target.webSocketDebuggerUrl);
        await new Promise((resolve, reject) => {
            const finish = error => {
                clearTimeout(timer);
                ws.removeEventListener("open", onOpen);
                ws.removeEventListener("error", onError);
                ws.removeEventListener("close", onClose);
                child.removeListener("exit", onExit);
                if (error) reject(error); else resolve();
            };
            const onOpen = () => finish();
            const onError = () => finish(diagnostic("CDP WebSocket connection failed."));
            const onClose = () => finish(diagnostic("CDP WebSocket closed before connecting."));
            const onExit = () => finish(diagnostic(`Browser exited before CDP WebSocket connected. Exit code: ${exitCode}; signal: ${signal || "none"}.`));
            const timer = setTimeout(() => finish(diagnostic("Timed out connecting to the CDP WebSocket.")),
                Math.max(1, deadline - Date.now()));
            ws.addEventListener("open", onOpen, { once: true });
            ws.addEventListener("error", onError, { once: true });
            ws.addEventListener("close", onClose, { once: true });
            child.once("exit", onExit);
        });
        return { ws, stop };
    } catch (error) {
        try { await stop(); } catch (cleanupError) {
            error.message += `\n${cleanupError.message}`;
        }
        throw error;
    }
}

module.exports = { browserArgs, launchBrowser };
