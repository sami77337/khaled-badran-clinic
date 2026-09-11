"use strict";

// Browser-level regression test: real Django responses, real stylesheets and JS.
// Uses Node's built-in WebSocket and an already installed headless Chromium.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { launchBrowser } = require("../../core/js_tests/browser_launcher");
const [browser, fixture, root] = process.argv.slice(2);
const pages = JSON.parse(fs.readFileSync(fixture, "utf8"));
const profile = path.join(path.dirname(fixture), "browser-profile");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
    const server = http.createServer((req, res) => {
        const pathname = new URL(req.url, "http://localhost").pathname;
        if (pages[pathname.slice(1)]) {
            res.setHeader("Content-Type", pathname.endsWith(".css") ? "text/css" : "text/html; charset=utf-8");
            res.end(pages[pathname.slice(1)]);
        } else if (/^\/static\/(css|js|fonts)\/[\w./-]+$/.test(pathname) && !pathname.includes("..")) {
            const file = path.join(root, pathname.slice(1));
            if (!fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
            res.setHeader("Content-Type", pathname.endsWith(".css") ? "text/css" : pathname.endsWith(".js") ? "text/javascript" : "font/woff2");
            res.end(fs.readFileSync(file));
        } else { res.writeHead(404); res.end(); }
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    let launcher, ws, send;
    try {
        launcher = await launchBrowser(browser, profile);
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
            const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
            assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
            return result.result.value;
        };
        await send("Page.enable");
        let cases = 0;
        for (const width of [320, 360, 390, 430, 768, 1024]) {
            await send("Emulation.setDeviceMetricsOverride", { width, height: 850, deviceScaleFactor: 1, mobile: false });
            for (const name of Object.keys(pages)) {
                await send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${name}` });
                await delay(120);
                await evaluate("document.fonts.ready");
                for (const role of name.startsWith("login") ? ["patient", "doctor"] : [""]) {
                    const result = await evaluate(`(() => {
                        const role = ${JSON.stringify(role)};
                        if (role) document.querySelector('[data-auth-role="' + role + '"]')?.click();
                        const controls = [...document.querySelectorAll('.auth-password-control')].filter(el => el.getBoundingClientRect().width > 0);
                        return {
                            overflow: document.documentElement.scrollWidth > innerWidth + 1,
                            controls: controls.map(control => {
                                const input = control.querySelector('input'), button = control.querySelector('[data-password-toggle]');
                                input.value = '\u0643\u0644\u0645\u0629\u0627\u0644\u0645\u0631\u0648\u0631-long-Synthetic-123!';
                                const rect = input.getBoundingClientRect(), b = button.getBoundingClientRect(), css = getComputedStyle(input);
                                button.click();
                                const visible = input.type === 'text' && button.getAttribute('aria-pressed') === 'true';
                                button.click();
                                return { visible, hidden: input.type === 'password' && button.getAttribute('aria-pressed') === 'false',
                                    inputDirection: css.direction, clearance: b.left - (rect.right - parseFloat(css.paddingRight)),
                                    fits: b.left >= rect.left && b.right <= rect.right && b.top >= rect.top && b.bottom <= rect.bottom,
                                    named: Boolean(button.getAttribute('aria-label')), focused: document.activeElement === input };
                            })
                        };
                    })()`);
                    assert(!result.overflow, `${width}/${name}/${role}: page overflow`);
                    assert(result.controls.length, `${width}/${name}/${role}: no password controls`);
                    for (const control of result.controls) {
                        assert(control.visible && control.hidden && control.fits && control.named && control.focused,
                            `${width}/${name}/${role}: toggle contract ${JSON.stringify(control)}`);
                        assert(control.inputDirection === "ltr" && control.clearance >= 2,
                            `${width}/${name}/${role}: text overlaps toggle ${JSON.stringify(control)}`);
                    }
                    cases++;
                }
                if (width === 360 && process.env.KBC_OWNER_QA_ARTIFACTS) {
                    fs.mkdirSync(process.env.KBC_OWNER_QA_ARTIFACTS, { recursive: true });
                    const capture = await send("Page.captureScreenshot", { format: "png" });
                    fs.writeFileSync(path.join(process.env.KBC_OWNER_QA_ARTIFACTS, `${name}-360.png`), Buffer.from(capture.data, "base64"));
                }
            }
        }
        console.log(`${cases} password visibility cases passed: login patient/staff, registration, recovery; AR/EN; 320/360/390/430/768/1024px.`);
    } finally {
        if (send && ws?.readyState === WebSocket.OPEN) {
            send("Browser.close").catch(() => {});
            await delay(300);
        }
        server.close();
        await launcher?.stop();
    }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
