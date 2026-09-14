"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { launchBrowser } = require("../../core/js_tests/browser_launcher");
const [browser, fixture] = process.argv.slice(2);
const { pages, assets } = JSON.parse(fs.readFileSync(fixture, "utf8"));
const viewports = [[320, 568], [360, 640], [390, 844], [412, 915], [640, 960], [768, 1024],
    [1024, 768], [1280, 720], [1280, 800], [1366, 768], [1440, 900],
    [1536, 864], [1600, 900], [1920, 1080], [1440, 1200]];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
    const server = http.createServer((req, res) => {
        const pathname = new URL(req.url, "http://localhost").pathname;
        if (pages[pathname.slice(1)]) {
            res.setHeader("Content-Type", "text/html; charset=utf-8");
            res.end(pages[pathname.slice(1)]);
        } else if (assets[pathname]) {
            const file = assets[pathname];
            const types = { ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg" };
            res.setHeader("Content-Type", types[path.extname(file)] || "application/octet-stream");
            res.end(fs.readFileSync(file));
        } else { res.writeHead(404); res.end(); }
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    let launcher, ws, send;
    try {
        launcher = await launchBrowser(browser, path.join(path.dirname(fixture), "browser-profile"));
        ws = launcher.ws;
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
            const key = ++id;
            pending.set(key, { resolve, reject });
            ws.send(JSON.stringify({ id: key, method, params }));
        });
        const evaluate = async expression => {
            const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
            if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
            return result.result.value;
        };
        await send("Page.enable");
        let cases = 0;
        for (const page of Object.keys(pages)) {
            await send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${page}` });
            for (let attempt = 0; attempt < 100; attempt++) {
                if (await evaluate(`location.pathname === '/${page}' && document.readyState === 'complete'`)) break;
                await delay(20);
            }
            assert.ok(await evaluate(`location.pathname === '/${page}' && document.readyState === 'complete'`), page);
            for (const [width, height] of viewports) {
                await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 768 });
                await evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
                const result = await evaluate(`(() => {
                    scrollTo({top: 0, behavior: 'instant'});
                    const issues = [];
                    if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('page overflow');
                    for (const el of document.querySelectorAll('.record-entry h3, .record-clinical-text, .record-form-errors')) {
                        const bounds = el.getBoundingClientRect();
                        const range = document.createRange(); range.selectNodeContents(el);
                        if ([...range.getClientRects()].filter(r => r.width && r.height)
                            .some(r => r.left < bounds.left - 1 || r.right > bounds.right + 1)) issues.push('text escaping ' + el.className);
                    }
                    const controls = [...document.querySelectorAll('#dashboard-main button, #dashboard-main a')]
                        .filter(el => !el.disabled && el.checkVisibility() && el.getBoundingClientRect().width);
                    for (const control of controls) {
                        control.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'});
                        const r = control.getBoundingClientRect();
                        if (r.left < -1 || r.right > innerWidth + 1) issues.push('action overflow');
                        if (r.height < 40) issues.push('small action target');
                        if (!control.contains(document.elementFromPoint((r.left+r.right)/2, (r.top+r.bottom)/2))) issues.push('covered review action');
                    }
                    return { issues, direction: document.documentElement.dir };
                })()`);
                assert.equal(result.direction, page.endsWith("-ar") ? "rtl" : "ltr", page);
                assert.deepEqual(result.issues, [], `${page} ${width}x${height}: ${JSON.stringify(result.issues)}`);
                if (process.env.KBC_REVIEW_QA_OUTPUT && page === "visible-ar" && (width === 390 || width === 1440)) {
                    await evaluate("scrollTo({top: 0, behavior: 'instant'})");
                    const screenshot = await send("Page.captureScreenshot", { format: "png" });
                    fs.mkdirSync(process.env.KBC_REVIEW_QA_OUTPUT, {recursive: true});
                    fs.writeFileSync(path.join(process.env.KBC_REVIEW_QA_OUTPUT, `reviews-ar-${width}.png`), Buffer.from(screenshot.data, "base64"));
                }
                cases++;
            }
        }
        console.log(`PASS: ${cases} dashboard review responsive cases (AR/EN; visible, hidden, empty, delete and stale states).`);
    } finally {
        if (send && ws?.readyState === WebSocket.OPEN) { send("Browser.close").catch(() => {}); await delay(300); }
        server.close();
        await launcher?.stop();
    }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
