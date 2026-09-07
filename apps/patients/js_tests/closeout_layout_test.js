"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { spawn } = require("node:child_process");
const [browser, fixture, root] = process.argv.slice(2);
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
        const widths = [320, 360, 375, 390, 412, 430, 479, 480, 540, 600, 639, 640, 641, 667, 720, 767, 768, 800, 844, 900, 1023, 1024];
        let reviews = 0, folders = 0, notifications = 0, rotations = 0;
        for (const language of ["ar", "en"]) {
            for (const surface of ["home", "reviews", "record"]) {
                await navigate(`${surface}-${language}`);
                for (const width of widths) {
                    for (const height of [320, 844]) {
                        await resize(width, height);
                        const result = await evaluate(`(() => {
                            const nodes = ${surface === "record"
        ? "[...document.querySelectorAll('.record-media-meta > span')].filter(el => el.textContent.includes('W'.repeat(120)))"
        : "[...document.querySelectorAll('.home-review-card:not([hidden]) blockquote, .home-review-card:not([hidden]) .review-card-footer p')]"};
                            const failures = [];
                            for (const el of nodes) {
                                const container = el.closest('${surface === "record" ? ".record-media-meta" : ".home-review-card"}');
                                const bounds = container.getBoundingClientRect();
                                const own = el.getBoundingClientRect();
                                const range = document.createRange(); range.selectNodeContents(el);
                                const rects = [...range.getClientRects()];
                                if (!rects.length || rects.some(r => r.left < bounds.left - 1 || r.right > bounds.right + 1 || r.top < own.top - 1 || r.bottom > own.bottom + 1)) {
                                    failures.push({ text: el.textContent.slice(0, 24), bounds: bounds.toJSON(), own: own.toJSON(), rects: rects.map(r => r.toJSON()) });
                                }
                            }
                            return { count: nodes.length, failures, width: document.documentElement.clientWidth,
                                scrollWidth: document.documentElement.scrollWidth, direction: document.documentElement.dir };
                        })()`);
                        const label = `${surface}/${language} ${width}x${height}`;
                        assert(result.count > 0, `${label}: missing stress content`);
                        assert.equal(result.direction, language === "ar" ? "rtl" : "ltr", label);
                        assert.equal(result.failures.length, 0, `${label}: clipped text ${JSON.stringify(result.failures)}`);
                        assert(result.scrollWidth <= result.width, `${label}: horizontal overflow ${JSON.stringify(result)}`);
                        if (surface === "record") folders++; else reviews++;
                    }
                }
            }
            for (const surface of ["public", "patient", "staff"]) {
                for (const width of [320, 360, 390, 412, 639, 640, 641, 667, 720, 844, 900]) {
                    for (const height of [260, 288, 320, 844]) {
                        await resize(width, height);
                        await navigate(`notifications-${surface}-${language}`);
                        await evaluate(`(() => {
                            const trigger = [...document.querySelectorAll('.consultation-notification-trigger')].find(el => el.getBoundingClientRect().width);
                            trigger.click();
                        })()`);
                        await checkNotification(`${surface}/${language} ${width}x${height}`);
                        notifications++;
                    }
                }
                await resize(390, 844);
                await navigate(`notifications-${surface}-${language}`);
                await evaluate("[...document.querySelectorAll('.consultation-notification-trigger')].find(el => el.getBoundingClientRect().width).click()");
                for (const [width, height] of [[640, 260], [641, 288], [390, 844]]) {
                    await resize(width, height);
                    await checkNotification(`open rotation ${surface}/${language} ${width}x${height}`);
                    rotations++;
                }
            }
        }

        async function checkNotification(label) {
            const result = await evaluate(`(() => {
                const panel = [...document.querySelectorAll('.consultation-notification-panel:not([hidden])')].find(el => el.getBoundingClientRect().width);
                if (!panel) return { missing: true };
                const list = panel.querySelector('.consultation-notification-list');
                const header = panel.querySelector('.consultation-notification-panel-header');
                const actions = panel.querySelector('.consultation-notification-panel-actions');
                const buttons = [...list.querySelectorAll('button')];
                const bounds = panel.getBoundingClientRect();
                const hit = (el, clip) => {
                    const r = el.getBoundingClientRect();
                    const x = (r.left + r.right) / 2;
                    const y = (Math.max(r.top, clip.top) + Math.min(r.bottom, clip.bottom)) / 2;
                    return el.contains(document.elementFromPoint(x, y));
                };
                list.scrollTop = 0;
                const firstReachable = buttons.length && hit(buttons[0], list.getBoundingClientRect());
                list.scrollTop = list.scrollHeight;
                const lastReachable = buttons.length && hit(buttons.at(-1), list.getBoundingClientRect());
                const actionControls = [...actions.querySelectorAll('button, a')];
                return { count: buttons.length, height: list.clientHeight, scrollHeight: list.scrollHeight,
                    firstReachable, lastReachable, actionsReachable: actionControls.every(el => hit(el, bounds)),
                    headerVisible: header.getBoundingClientRect().top >= bounds.top,
                    fits: bounds.top >= 0 && bounds.bottom <= innerHeight && bounds.left >= 0 && bounds.right <= innerWidth,
                    bounds: bounds.toJSON(), viewport: [innerWidth, innerHeight] };
            })()`);
            assert(!result.missing && result.count >= 8, `${label}: notification fixture ${JSON.stringify(result)}`);
            assert(result.height >= 48 && result.fits && result.headerVisible && result.actionsReachable,
                `${label}: panel usability ${JSON.stringify(result)}`);
            assert(result.firstReachable && result.lastReachable, `${label}: entries inaccessible ${JSON.stringify(result)}`);
        }
        console.log(`PASS: ${reviews} Home/Reviews long-content cases; ${folders} medical-folder text geometry cases; ${notifications} notification viewport cases; ${rotations} open-panel rotations (AR/EN).`);
    } finally {
        if (send && ws?.readyState === WebSocket.OPEN) { send("Browser.close").catch(() => {}); await delay(300); }
        ws?.close();
        if (child.exitCode === null) child.kill();
        server.close();
    }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
