"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");
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
            return;
        }
        let file = assets[pathname];
        if (!file && pathname.startsWith("/static/admin/") && !pathname.includes("..")) {
            file = path.join(path.dirname(path.dirname(assets["/static/admin/css/base.css"])),
                pathname.slice("/static/admin/".length));
        }
        if (file && fs.existsSync(file)) {
            res.setHeader("Content-Type", file.endsWith(".css") ? "text/css" : file.endsWith(".js") ? "text/javascript" : "image/svg+xml");
            res.end(fs.readFileSync(file));
        } else { res.writeHead(404); res.end(); }
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    const profile = path.join(path.dirname(fixture), "browser-profile");
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
        for (const page of Object.keys(pages)) {
            await send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${page}` });
            for (let i = 0; i < 150; i++) {
                if (await evaluate(`location.pathname === '/${page}' && document.readyState === 'complete'`)) break;
                await delay(20);
            }
            for (const [width, height] of viewports) {
                await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 768 });
                await evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
                const result = await evaluate(`(() => {
                    scrollTo({top: 0, behavior: 'instant'});
                    const issues = [];
                    if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('page overflow');
                    const textRects = el => {
                        const range = document.createRange(); range.selectNodeContents(el);
                        return [...range.getClientRects()].filter(r => r.width && r.height);
                    };
                    for (const el of document.querySelectorAll('.breadcrumbs, #content > h2, .readonly, #content > p, #deleted-objects')) {
                        const bounds = el.getBoundingClientRect();
                        if (textRects(el).some(r => r.left < bounds.left - 1 || r.right > bounds.right + 1)) {
                            issues.push('text escaping ' + el.tagName + '.' + el.className);
                        }
                    }
                    const title = document.querySelector('#content > h2');
                    const history = document.querySelector('.object-tools a');
                    if (title && history) {
                        const control = history.getBoundingClientRect();
                        if (textRects(title).some(r => Math.min(r.right, control.right) - Math.max(r.left, control.left) > 1 &&
                            Math.min(r.bottom, control.bottom) - Math.max(r.top, control.top) > 1)) issues.push('history overlaps title');
                    }
                    for (const name of document.querySelectorAll('#result_list .field-reviewer_name a')) {
                        // Smaller screens use Django's horizontally scrollable table.
                        if (innerWidth >= 1024 && name.getBoundingClientRect().width > 300) issues.push('unbounded reviewer column');
                    }
                    const controls = [...document.querySelectorAll('#content input[type=submit], #content button, #content .cancel-link, #content .deletelink')]
                        .filter(el => !el.disabled && el.checkVisibility() && el.getBoundingClientRect().width);
                    for (const control of controls) {
                        control.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'});
                        const r = control.getBoundingClientRect();
                        if (!control.contains(document.elementFromPoint((r.left+r.right)/2, (r.top+r.bottom)/2))) issues.push('covered moderation action');
                    }
                    return { issues, direction: document.documentElement.dir };
                })()`);
                assert.equal(result.direction, page.endsWith("-ar") ? "rtl" : "ltr", page);
                assert.deepEqual(result.issues, [], `${page} ${width}x${height}: ${JSON.stringify(result.issues)}`);
                cases++;
            }
        }
        console.log(`PASS: ${cases} review admin responsive cases (AR/EN; long text, bounded desktop columns, History spacing, moderation/delete actions).`);
    } finally {
        if (send && ws?.readyState === WebSocket.OPEN) { send("Browser.close").catch(() => {}); await delay(300); }
        ws?.close();
        if (child.exitCode === null) child.kill();
        server.close();
    }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
