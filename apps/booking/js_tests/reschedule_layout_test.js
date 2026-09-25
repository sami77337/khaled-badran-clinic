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
            const types = { ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp" };
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
            for (const [width, height] of viewports) {
                await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 768 });
                await send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${page}` });
                for (let attempt = 0; attempt < 100; attempt++) {
                    if (await evaluate(`location.pathname === '/${page}' && document.readyState === 'complete'`)) break;
                    await delay(20);
                }
                assert.ok(await evaluate(`location.pathname === '/${page}' && document.readyState === 'complete'`), page);
                await evaluate("document.fonts.ready");
                const result = await evaluate(`(() => {
                    const issues = [];
                    if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('page overflow');
                    const visible = el => el.checkVisibility() && el.getBoundingClientRect().width;
                    for (const el of [...document.querySelectorAll('.booking-flow h1, .booking-flow h2, .booking-flow p, .booking-flow dd, .booking-flow time')].filter(visible)) {
                        const r = el.getBoundingClientRect();
                        if (r.left < -1 || r.right > innerWidth + 1) issues.push('content overflow: ' + el.tagName);
                        const range = document.createRange(); range.selectNodeContents(el);
                        if ([...range.getClientRects()].filter(r => r.width && r.height).some(t => t.left < -1 || t.right > innerWidth + 1)) issues.push('text overflow: ' + el.tagName);
                    }
                    for (const control of [...document.querySelectorAll('.booking-flow a, .booking-flow button')].filter(visible)) {
                        control.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'});
                        const r = control.getBoundingClientRect();
                        if (r.left < -1 || r.right > innerWidth + 1) issues.push('action overflow');
                        if (r.height < 40) issues.push('small action target');
                        if (!control.contains(document.elementFromPoint((r.left+r.right)/2, (r.top+r.bottom)/2))) issues.push('covered action');
                    }
                    for (const field of [...document.querySelectorAll(
                        '.booking-flow input:not([type=hidden]):not([type=checkbox]):not([type=radio]), ' +
                        '.booking-flow select, .booking-flow textarea'
                    )].filter(visible)) {
                        const r = field.getBoundingClientRect();
                        if (r.left < -1 || r.right > innerWidth + 1) issues.push('field overflow');
                        if (r.height < 40) issues.push('small field target');
                    }
                    return { issues, direction: document.documentElement.dir };
                })()`);
                assert.equal(result.direction, page.endsWith("-ar") ? "rtl" : "ltr", page);
                assert.deepEqual(result.issues, [], `${page} ${width}x${height}: ${JSON.stringify(result.issues)}`);
                if (page.startsWith("slots-") || page.startsWith("selected-") || page.startsWith("booking-")) {
                    const interaction = await evaluate(`(() => {
                        const flow = document.querySelector('[data-booking-slot-step]');
                        const dates = [...flow.querySelectorAll('[data-booking-date-group]')];
                        dates[dates.length > 1 ? 1 : 0].click();
                        const disabled = flow.querySelector('[data-booking-slot-continue]').getAttribute('aria-disabled');
                        const panel = flow.querySelector('[data-booking-time-panel]:not([hidden])');
                        const slot = panel.querySelector('[data-booking-slot]');
                        slot.click();
                        const next = new URL(flow.querySelector('[data-booking-slot-continue]').href);
                        const switches = [...document.querySelectorAll('a[hreflang]')].map(a => new URL(a.href));
                        return {
                            disabled, value: slot.dataset.bookingSlotValue, nextValue: next.searchParams.get('starts_at'),
                            nextPath: next.pathname, expectedPath: new URL(flow.dataset.bookingConfirmUrl, location.href).pathname,
                            languageRetained: switches.every(u => u.searchParams.get('starts_at') === slot.dataset.bookingSlotValue),
                            selected: panel.querySelectorAll('[data-booking-selected-time]').length,
                        };
                    })()`);
                    assert.equal(interaction.disabled, "true");
                    assert.equal(interaction.value, interaction.nextValue);
                    assert.equal(interaction.nextPath, interaction.expectedPath);
                    assert.ok(interaction.languageRetained);
                    assert.equal(interaction.selected, 1);
                }
                if (page.startsWith("confirm-")) {
                    assert.deepEqual(await evaluate(`(() => {
                        const form = document.querySelector('[data-reschedule-form]');
                        return {method: form.method, fields: [...form.elements].map(el => el.name).filter(Boolean).sort()};
                    })()`), {method: "post", fields: ["csrfmiddlewaretoken", "starts_at"]});
                }
                if (page.startsWith("booking-confirm-")) {
                    const bookingForm = await evaluate(`(() => {
                        const form = document.querySelector('[data-booking-patient-form]');
                        const fields = [...form.elements].map(el => el.name).filter(Boolean);
                        const required = ["csrfmiddlewaretoken", "full_name", "phone", "same_as_phone", "whatsapp_phone", "booking_note", "visit_type", "starts_at"];
                        return {
                            method: form.method,
                            hasRequired: required.every(name => fields.includes(name)),
                            action: new URL(form.action).pathname,
                        };
                    })()`);
                    assert.equal(bookingForm.method, "post");
                    assert.ok(bookingForm.hasRequired, page + ": required public booking fields");
                    assert.ok(bookingForm.action.includes("/book/confirm/"), page + ": public booking action");
                }
                if (page.startsWith("booking-success-")) {
                    assert.ok(await evaluate(`Boolean(document.querySelector('[data-booking-success]'))`), page + ": success marker");
                }
                if (process.env.KBC_RESCHEDULE_QA_OUTPUT && (width === 390 || width === 1440) && !page.startsWith("booking-")) {
                    // Slot selection preserves the viewport on the next frame.
                    // Let that and the existing selection transition finish first.
                    await delay(250);
                    await evaluate("scrollTo({top: 0, behavior: 'instant'})");
                    await evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
                    const screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
                        clip: {x: 0, y: 0, width, height: await evaluate("document.documentElement.scrollHeight"), scale: 1} });
                    fs.mkdirSync(process.env.KBC_RESCHEDULE_QA_OUTPUT, {recursive: true});
                    fs.writeFileSync(path.join(process.env.KBC_RESCHEDULE_QA_OUTPUT, `${page}-${width}.png`), Buffer.from(screenshot.data, "base64"));
                }
                cases++;
            }
        }
        assert.deepEqual(runtimeErrors, [], "Browser runtime errors");
        console.log(`PASS: ${cases} rendered AR/EN cases at 320/390/768/1024/1440; reschedule + public booking slots/confirm/success, empty/error states, and privacy-safe actions.`);
    } finally {
        if (send && ws?.readyState === WebSocket.OPEN) { send("Browser.close").catch(() => {}); await delay(300); }
        server.close();
        await launcher?.stop();
    }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
