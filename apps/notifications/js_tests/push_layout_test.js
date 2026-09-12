"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { launchBrowser } = require("../../core/js_tests/browser_launcher");
const [browser, fixture, root] = process.argv.slice(2);
const pages = JSON.parse(fs.readFileSync(fixture, "utf8"));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
    const server = http.createServer((req, res) => {
        const pathname = new URL(req.url, "http://localhost").pathname;
        if (pages[pathname.slice(1)]) {
            res.setHeader("Content-Type", "text/html; charset=utf-8");
            res.end(pages[pathname.slice(1)]);
        } else if (pathname === "/dashboard/phone-notifications/config/") {
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify({ available: true, publicKey: "BA" }));
        } else if (pathname === "/sw.js") {
            res.setHeader("Content-Type", "text/javascript");
            res.setHeader("Service-Worker-Allowed", "/");
            res.end(fs.readFileSync(path.join(root, "static/sw.js")));
        } else if (pathname.startsWith("/static/") && !pathname.includes("..")) {
            const file = path.join(root, pathname.slice(1));
            if (!fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); res.end(); return; }
            const types = { ".css": "text/css", ".js": "text/javascript", ".webmanifest": "application/manifest+json", ".png": "image/png", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
            res.setHeader("Content-Type", types[path.extname(file)] || "application/octet-stream");
            res.end(fs.readFileSync(file));
        } else { res.writeHead(404); res.end(); }
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    let launcher;
    try {
        launcher = await launchBrowser(browser, path.join(path.dirname(fixture), "profile"));
        let id = 0;
        const pending = new Map();
        launcher.ws.addEventListener("message", ({ data }) => {
            const response = JSON.parse(data);
            if (!response.id) return;
            const task = pending.get(response.id);
            pending.delete(response.id);
            if (response.error) task.reject(new Error(JSON.stringify(response.error)));
            else task.resolve(response.result);
        });
        const send = (method, params = {}) => new Promise((resolve, reject) => {
            const key = ++id; pending.set(key, { resolve, reject });
            launcher.ws.send(JSON.stringify({ id: key, method, params }));
        });
        const evaluate = async expression => {
            const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
            assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
            return result.result.value;
        };
        for (const language of ["ar", "en"]) {
            await send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${language}` });
            let ready = false;
            for (let i = 0; i < 100; i++) {
                ready = await evaluate(`document.readyState === 'complete' && !!document.querySelector('[data-phone-enable]') && !document.querySelector('[data-phone-enable]').disabled`);
                if (ready) break;
                await delay(50);
            }
            assert(ready, "Phone control did not initialize");
            assert.equal(await evaluate("Notification.permission"), "default", "Page load must not prompt");
            assert.equal(await evaluate("navigator.serviceWorker.ready.then(r => r.scope)"), `http://127.0.0.1:${server.address().port}/`);
            assert.equal(await evaluate("navigator.serviceWorker.ready.then(r => r.pushManager.getSubscription()).then(s => s === null)"), true);
            for (const width of [320, 375, 390, 768, 1280]) {
                await send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: width < 768 });
                await evaluate("document.fonts.ready");
                for (const enabled of [false, true]) {
                    await evaluate(`document.querySelector('[data-phone-enable]').hidden = ${enabled}; document.querySelector('[data-phone-disable]').hidden = ${!enabled};`);
                    const geometry = await evaluate(`(() => {
                        const panel = document.querySelector('[data-phone-notifications]');
                        const elements = [panel, ...panel.querySelectorAll('h2, p, button:not([hidden])')];
                        return { direction: document.documentElement.dir,
                            overflow: document.documentElement.scrollWidth > innerWidth + 1,
                            boxes: elements.map(el => { const b = el.getBoundingClientRect(); return { left: b.left, right: b.right, width: b.width, height: b.height, textClipped: el.scrollWidth > el.clientWidth + 1 }; }) };
                    })()`);
                    assert.equal(geometry.direction, language === "ar" ? "rtl" : "ltr");
                    assert(!geometry.overflow, `${language}/${width} page overflow`);
                    for (const box of geometry.boxes) {
                        assert(box.left >= -1 && box.right <= width + 1, `${language}/${width}: ${JSON.stringify(box)}`);
                        assert(box.width > 0 && box.height > 0 && !box.textClipped, `${language}/${width}: clipped control`);
                    }
                    if (process.env.KBC_PUSH_SCREENSHOT_DIR && !enabled && [390, 1280].includes(width)) {
                        fs.mkdirSync(process.env.KBC_PUSH_SCREENSHOT_DIR, { recursive: true });
                        const capture = await send("Page.captureScreenshot", { format: "png" });
                        fs.writeFileSync(path.join(process.env.KBC_PUSH_SCREENSHOT_DIR, `push-${language}-${width}.png`), Buffer.from(capture.data, "base64"));
                    }
                }
            }
        }
        console.log("Push dashboard: AR/EN, 320/375/390/768/1280px, enable/disable geometry, real root-scoped worker, no automatic permission/subscription: passed.");
    } finally {
        if (launcher) await launcher.stop();
        await new Promise(resolve => server.close(resolve));
    }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
