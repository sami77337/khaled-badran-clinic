"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { test } = require("node:test");
const { browserArgs, launchBrowser } = require("./browser_launcher");

// The Django wrapper owns and removes this temporary directory after Node exits.
const profile = () => fs.mkdtempSync(path.join(process.env.KBC_LAUNCHER_TEST_DIR, "profile-"));

function syntheticBrowser(script) {
    let child, closed = false;
    return {
        spawnProcess(browser, args, options) {
            const directory = args.find(arg => arg.startsWith("--user-data-dir=")).split("=").slice(1).join("=");
            child = spawn(process.execPath, ["-e", `
                const fs = require('node:fs');
                const portFile = require('node:path').join(${JSON.stringify(directory)}, 'DevToolsActivePort');
                ${script}
            `], options);
            child.once("close", () => { closed = true; });
            return child;
        },
        assertStopped() {
            assert(closed, "launcher must reap the browser before returning");
            assert(child.exitCode !== null || child.signalCode !== null);
        },
    };
}

function endpointScript(mode) {
    return `
        const http = require('node:http');
        let requests = 0;
        const server = http.createServer((req, res) => {
            requests++;
            if (${JSON.stringify(mode)} === 'unavailable' ||
                (${JSON.stringify(mode)} === 'last-response' && requests === 1)) {
                res.writeHead(503); res.end(); return;
            }
            if (${JSON.stringify(mode)} === 'last-response') return;
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify(${JSON.stringify(mode)} === 'missing' || requests < 2 ? [] : [{
                type: 'page', webSocketDebuggerUrl: 'ws://127.0.0.1:' + server.address().port + '/devtools/page/test'
            }]));
        });
        server.on('upgrade', (req, socket) => {
            if (${JSON.stringify(mode)} === 'refused') { socket.destroy(); return; }
            if (${JSON.stringify(mode)} === 'stalled') return;
            const accept = require('node:crypto').createHash('sha1')
                .update(req.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
            socket.write('HTTP/1.1 101 Switching Protocols\\r\\nUpgrade: websocket\\r\\nConnection: Upgrade\\r\\n' +
                'Sec-WebSocket-Accept: ' + accept + '\\r\\n\\r\\n');
        });
        server.listen(0, '127.0.0.1', () => {
            // Simulate observing the port file before Chromium finishes writing it.
            fs.writeFileSync(portFile, '');
            setTimeout(() => fs.writeFileSync(portFile, server.address().port + '\\n/devtools/browser/test\\n'), 100);
        });
    `;
}

test("Linux CI flags preserve local Windows/macOS/Linux sandbox and isolated CDP arguments", () => {
    for (const platform of ["win32", "darwin", "linux"]) {
        for (const env of [{}, { CI: "false" }, { CI: "true" }, { GITHUB_ACTIONS: "true" }]) {
            const args = browserArgs("synthetic profile", platform, env);
            assert.equal(args.includes("--no-sandbox"), platform === "linux" &&
                (env.CI === "true" || env.GITHUB_ACTIONS === "true"));
            for (const flag of ["--headless=new", "--remote-debugging-port=0", "--user-data-dir=synthetic profile"]) {
                assert(args.includes(flag));
            }
            assert.equal(args.at(-1), "about:blank");
        }
    }
});

test("missing executable reports launch failure instead of an unhandled spawn error", async () => {
    const directory = profile();
    await assert.rejects(launchBrowser(path.join(directory, "missing-browser"), directory, { timeoutMs: 1500 }),
        /Could not start browser: ENOENT/);
});

test("early exit reports the exit code and bounded stderr, then reaps the child", async () => {
    const fake = syntheticBrowser("process.stderr.write('x'.repeat(9000) + ' synthetic startup failure', () => process.exit(23));");
    await assert.rejects(launchBrowser("synthetic", profile(), { ...fake, timeoutMs: 1500 }), error => {
        assert.match(error.message, /Browser exited before creating DevToolsActivePort\. Exit code: 23/);
        assert.match(error.message, /synthetic startup failure/);
        assert(error.message.length < 8500, "stderr must be bounded");
        return true;
    });
    fake.assertStopped();
});

test("missing port file times out with diagnostics and stops the live child", async () => {
    const fake = syntheticBrowser("process.stderr.write('synthetic browser still starting'); setInterval(() => {}, 100);");
    await assert.rejects(launchBrowser("synthetic", profile(), { ...fake, timeoutMs: 1500 }), error => {
        assert.match(error.message, /Timed out waiting for Chromium DevToolsActivePort/);
        assert.match(error.message, /synthetic browser still starting/);
        assert.doesNotMatch(error.message, /ENOENT/);
        return true;
    });
    fake.assertStopped();
});

for (const [mode, message] of [
    ["unavailable", /CDP endpoint unavailable: HTTP 503/],
    ["last-response", /CDP endpoint unavailable: HTTP 503; latest request:/],
    ["missing", /CDP page target missing/],
    ["refused", /CDP WebSocket connection failed|CDP WebSocket closed/],
    ["stalled", /Timed out connecting to the CDP WebSocket/],
]) {
    test(`${mode} CDP connection fails clearly and stops the browser`, async () => {
        const fake = syntheticBrowser(endpointScript(mode));
        await assert.rejects(launchBrowser("synthetic", profile(), { ...fake, timeoutMs: 1500 }), message);
        fake.assertStopped();
    });
}

test("partial port file and initially empty target list recover; successful launch stops cleanly", async () => {
    const fake = syntheticBrowser(endpointScript("ready"));
    const launcher = await launchBrowser("synthetic", profile(), { ...fake, timeoutMs: 3000 });
    try { assert.equal(launcher.ws.readyState, WebSocket.OPEN); }
    finally { await launcher.stop(); }
    fake.assertStopped();
    await launcher.stop(); // Cleanup is safe after Chromium has already exited.
});
