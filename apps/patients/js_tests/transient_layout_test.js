"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { spawn } = require("node:child_process");
const [browser, fixture, root, screenshotDir] = process.argv.slice(2);
const pages = JSON.parse(fs.readFileSync(fixture, "utf8"));
const profile = path.join(path.dirname(fixture), "browser-profile");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
    const server = http.createServer((req, res) => {
        const pathname = new URL(req.url, "http://localhost").pathname;
        if (pages[pathname.slice(1)]) {
            res.setHeader("Content-Type", "text/html; charset=utf-8");
            res.end(pages[pathname.slice(1)]);
        } else if (/^\/static\/(css|js|fonts)\/[\w./-]+$/.test(pathname) && !pathname.includes("..")) {
            const file = path.join(root, pathname.slice(1));
            if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
            res.setHeader("Content-Type", pathname.endsWith(".css") ? "text/css" : pathname.endsWith(".js") ? "text/javascript" : "font/woff2");
            res.end(fs.readFileSync(file));
        } else { res.writeHead(404); res.end(); }
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    const child = spawn(browser, ["--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"],
    { windowsHide: true, stdio: "ignore" });
    let ws, send;
    try {
        const portFile = path.join(profile, "DevToolsActivePort");
        for (let i = 0; !fs.existsSync(portFile) && i < 100; i++) await delay(100);
        const port = fs.readFileSync(portFile, "utf8").split("\n")[0];
        const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        ws = new WebSocket(targets.find(target => target.type === "page").webSocketDebuggerUrl);
        await new Promise(resolve => ws.addEventListener("open", resolve, { once: true }));
        let id = 0;
        const pending = new Map();
        ws.addEventListener("message", ({ data }) => {
            const response = JSON.parse(data);
            if (!response.id) return;
            const task = pending.get(response.id);
            pending.delete(response.id);
            if (response.error) task.reject(new Error(JSON.stringify(response.error)));
            else task.resolve(response.result);
        });
        send = (method, params = {}) => new Promise((resolve, reject) => {
            const key = ++id; pending.set(key, { resolve, reject });
            ws.send(JSON.stringify({ id: key, method, params }));
        });
        const evaluate = async expression => {
            const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
            assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
            return result.result.value;
        };
        const resize = (width, height) => send("Emulation.setDeviceMetricsOverride", {
            width, height, deviceScaleFactor: 1, mobile: true,
        });
        const navigate = async page => {
            await send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${page}` });
            for (let i = 0; i < 100; i++) {
                if (await evaluate(`location.pathname === '/${page}' && document.readyState === 'complete'`)) break;
                await delay(20);
            }
            await evaluate("document.fonts.ready.then(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))))");
        };
        await send("Page.enable");
        await send("Emulation.setFocusEmulationEnabled", { enabled: true });
        const widths = [320, 360, 390, 412, 640, 768, 1024, 1280, 1440];
        let cases = 0;
        for (const page of Object.keys(pages)) {
            await navigate(page);
            for (const width of widths) {
                for (const height of [568, 900]) {
                    await resize(width, height);
                    await evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))");
                    const result = await evaluate(`(() => {
                        const root = document.querySelector('.guest-consultation') || document.querySelector('.appointment-detail-content');
                        const failures = [];
                        if (!root) return { failures: ['missing page'] };
                        if (document.documentElement.scrollWidth > innerWidth + 1) failures.push('page overflow');
                        for (const el of root.querySelectorAll('input:not([type=hidden]), textarea, select, button, .guest-text, .guest-filename, .portal-media-meta, .guest-card')) {
                            if (el.hidden || !el.getClientRects().length) continue;
                            const b = el.getBoundingClientRect();
                            if (b.left < -1 || b.right > innerWidth + 1) failures.push(el.tagName + '.' + el.className + ': outside viewport');
                            if (el.matches('.guest-text,.guest-filename,.portal-media-meta') && el.scrollWidth > el.clientWidth + 1) failures.push('text overflow');
                            if (el.tagName === 'BUTTON' && b.height < 43) failures.push('short button');
                            if (el.matches('input:not([type=hidden]),textarea,select') && !el.hidden && !el.labels?.length && el.type !== 'file') failures.push('missing input label');
                        }
                        return { failures, direction: document.documentElement.dir, language: document.documentElement.lang };
                    })()`);
                    assert.deepEqual(result.failures, [], `${page} ${width}x${height}: ${JSON.stringify(result)}`);
                    assert.equal(result.language, page.endsWith('-ar') ? 'ar' : 'en');
                    assert.equal(result.direction, page.endsWith('-ar') ? 'rtl' : 'ltr');
                    cases++;
                }
            }
            if (screenshotDir && ['phone-ar', 'form-en', 'answered-ar', 'staff-unavailable-en'].includes(page)) {
                fs.mkdirSync(screenshotDir, { recursive: true });
                await resize(page.startsWith('staff') ? 1280 : 390, 900);
                const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
                fs.writeFileSync(path.join(screenshotDir, page + '.png'), Buffer.from(shot.data, 'base64'));
            }
        }
        console.log(`PASS: ${cases} guest/staff layout cases; ${Object.keys(pages).length} AR/EN states at 9 requested widths and 2 heights.`);
    } finally {
        if (send && ws?.readyState === WebSocket.OPEN) { send('Browser.close').catch(() => {}); await delay(300); }
        ws?.close();
        if (child.exitCode === null) child.kill();
        server.close();
    }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
