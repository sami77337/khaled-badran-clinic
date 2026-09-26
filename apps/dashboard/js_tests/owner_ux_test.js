"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { launchBrowser } = require("../../core/js_tests/browser_launcher");
const [browser, fixture] = process.argv.slice(2);
const { pages, assets } = JSON.parse(fs.readFileSync(fixture, "utf8"));
const viewports = [[320, 568], [390, 844], [768, 1024], [1024, 768], [1440, 900]];
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
        const runtimeErrors = [];
        ws.addEventListener("message", ({ data }) => {
            const response = JSON.parse(data);
            if (response.method === "Runtime.exceptionThrown") runtimeErrors.push(response.params.exceptionDetails.text);
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
        await send("Runtime.enable");
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
                    for (const el of document.querySelectorAll('.owner-content-page input:not([type=hidden]), .owner-content-page textarea, .owner-content-page select, .owner-content-page button, .owner-content-page a')) {
                        if (!el.checkVisibility()) continue;
                        const r = el.getBoundingClientRect();
                        if (r.left < -1 || r.right > innerWidth + 1) issues.push('control overflow: ' + el.name);
                        if (r.height < 40 && el.type !== 'checkbox') issues.push('small target: ' + el.name);
                    }
                    for (const el of document.querySelectorAll('[data-doctor-section], [data-doctor-section] span, .doctor-condition-group')) {
                        const r = el.getBoundingClientRect();
                        if (r.left < -1 || r.right > innerWidth + 1) issues.push('section overflow');
                    }
                    const homeServices = document.querySelector('.home-services');
                    return {
                        issues,
                        direction: document.documentElement.dir,
                        homeServicesVisible: homeServices ? getComputedStyle(homeServices).display !== 'none' : null,
                    };
                })()`);
                assert.equal(result.direction, page.endsWith("-ar") ? "rtl" : "ltr", page);
                assert.deepEqual(result.issues, [], `${page} ${width}x${height}: ${JSON.stringify(result.issues)}`);
                if (page === "home-ar" || page === "home-en") {
                    assert.equal(
                        result.homeServicesVisible,
                        width >= 768,
                        `${page} ${width}x${height}: Home Services must be hidden only below 768px`,
                    );
                }
                if (process.env.KBC_OWNER_QA_OUTPUT && (width === 390 || width === 1440)) {
                    await evaluate("scrollTo({top: 0, behavior: 'instant'})");
                    const screenshot = await send("Page.captureScreenshot", { format: "png" });
                    fs.mkdirSync(process.env.KBC_OWNER_QA_OUTPUT, {recursive: true});
                    fs.writeFileSync(path.join(process.env.KBC_OWNER_QA_OUTPUT, `${page}-${width}.png`), Buffer.from(screenshot.data, "base64"));
                    if (page.startsWith('doctor-') || page.startsWith('custom-modes-')) {
                        await evaluate("document.querySelector('.doctor-details-section').scrollIntoView({behavior:'instant'})");
                        const detail = await send('Page.captureScreenshot', {format: 'png'});
                        fs.writeFileSync(path.join(process.env.KBC_OWNER_QA_OUTPUT, `${page}-${width}-sections.png`), Buffer.from(detail.data, 'base64'));
                    }
                }
                cases++;
            }
        }
        // Exercise real DOM events with a synthetic browser install event.
        // This verifies the application contract without claiming OS installation.
        const installCases = [];
        for (const language of ['ar', 'en']) {
            const go = async (ua, platform, touch = 0) => {
                await send('Emulation.setUserAgentOverride', {userAgent: ua, platform});
                await send('Emulation.setTouchEmulationEnabled', {enabled: touch > 0, maxTouchPoints: touch || 1});
                await send('Page.navigate', {url: `http://127.0.0.1:${server.address().port}/home-${language}`});
                for (let n=0; n<100; n++) {
                    if (await evaluate(`document.readyState === 'complete' && document.querySelector('[data-install-app]') && !document.querySelector('[data-install-app]').hidden`)) break;
                    await delay(25);
                }
            };
            await go('Mozilla/5.0 (Linux; Android 14) Chrome/130.0 Mobile Safari/537.36', 'Linux', 5);
            for (const outcome of ['dismissed', 'accepted']) {
                const state = await evaluate(`(async () => {
                    let calls = 0;
                    const event = new Event('beforeinstallprompt', {cancelable: true});
                    event.prompt = async () => { calls++; };
                    event.userChoice = Promise.resolve({outcome: '${outcome}'});
                    window.dispatchEvent(event);
                    const before = calls;
                    if (document.querySelector('[data-install-sheet]').open) throw new Error('Unexpected install nag');
                    document.querySelector('[data-install-app]').click();
                    await new Promise(resolve => setTimeout(resolve, 30));
                    return {before, calls, prevented: event.defaultPrevented, hidden: document.querySelector('[data-install-app]').hidden};
                })()`);
                assert.deepEqual(state, {before: 0, calls: 1, prevented: true, hidden: outcome === 'accepted'});
                installCases.push(`${language} Android ${outcome}`);
            }
            for (const [device, ua, platform] of [['iPhone', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', 'iPhone'], ['iPad', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)', 'MacIntel']]) {
                await go(ua, platform, 5);
                await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
                const state = await evaluate(`(() => {
                    document.querySelector('[data-install-app]').click();
                    const sheet = document.querySelector('[data-install-sheet]');
                    const r = sheet.getBoundingClientRect();
                    return {open: sheet.open, ios: !sheet.querySelector('[data-install-ios]').hidden,
                        generic: sheet.querySelector('[data-install-browser]').hidden,
                        fits: r.left >= 0 && r.right <= innerWidth && r.bottom <= innerHeight,
                        focus: sheet.contains(document.activeElement)};
                })()`);
                assert.deepEqual(state, {open: true, ios: true, generic: true, fits: true, focus: true});
                if (process.env.KBC_OWNER_QA_OUTPUT && device === 'iPhone') {
                    const screenshot = await send('Page.captureScreenshot', {format: 'png'});
                    fs.writeFileSync(path.join(process.env.KBC_OWNER_QA_OUTPUT, `install-ios-${language}-390.png`), Buffer.from(screenshot.data, 'base64'));
                }
                await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
                await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27});
                assert.equal(await evaluate("document.querySelector('[data-install-sheet]').open"), false);
                await evaluate("window.dispatchEvent(new Event('appinstalled'))");
                assert.equal(await evaluate("document.querySelector('[data-install-app]').hidden"), true);
                installCases.push(`${language} ${device} instructions / Escape / installed`);
            }
            // navigator.standalone covers installed Safari; matchMedia covers Chrome.
            for (const mode of ['navigator', 'media']) {
                const {identifier} = await send('Page.addScriptToEvaluateOnNewDocument', {source: mode === 'navigator'
                    ? "Object.defineProperty(navigator, 'standalone', {get: () => true})"
                    : "const originalMatchMedia = window.matchMedia; window.matchMedia = query => query === '(display-mode: standalone)' ? {matches: true, addEventListener() {}} : originalMatchMedia(query)"});
                await send('Page.navigate', {url: `http://127.0.0.1:${server.address().port}/home-${language}`});
                await delay(150);
                assert.equal(await evaluate("document.querySelector('[data-install-app]').hidden"), true);
                await send('Page.removeScriptToEvaluateOnNewDocument', {identifier});
                installCases.push(`${language} standalone ${mode}`);
            }
        }
        assert.deepEqual(runtimeErrors, [], 'No uncaught browser exceptions');
        assert.deepEqual(await evaluate('caches.keys()'), [], 'No response cache created');
        assert.equal(await evaluate("navigator.serviceWorker.getRegistration('/').then(reg => Boolean(reg && reg.active && reg.active.scriptURL.endsWith('/sw.js')))"), true, 'Existing root worker registered');
        console.log(`PASS: ${cases} responsive pages (320/390/768/1024/1440, AR/EN); ${installCases.length} install runtime cases. Native device installation is not exercised.`);
    } finally {
        if (send && ws?.readyState === WebSocket.OPEN) { send("Browser.close").catch(() => {}); await delay(300); }
        server.close();
        await launcher?.stop();
    }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
