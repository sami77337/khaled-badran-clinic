"use strict";

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
            res.setHeader("Content-Type", "text/html; charset=utf-8");
            res.end(pages[pathname.slice(1)]);
        } else if (pathname === '/static/img/location/clinic-location-illustrated-map.png') {
            res.setHeader("Content-Type", "image/png");
            res.end(fs.readFileSync(path.join(root, pathname.slice(1))));
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
            const key = ++id; pending.set(key, { resolve, reject });
            ws.send(JSON.stringify({ id: key, method, params }));
        });
        const evaluate = async expression => {
            const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
            assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
            return result.result.value;
        };
        const resize = (width, height, mobile = true) => send("Emulation.setDeviceMetricsOverride", {
            width, height, deviceScaleFactor: 1, mobile,
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
        const mapViewports = [[320, 568], [360, 640], [390, 844], [412, 915], [640, 960],
            [768, 1024], [1024, 768], [1280, 720], [1280, 800], [1366, 768], [1440, 900],
            [1536, 864], [1600, 900], [1920, 1080]];
        let illustratedMaps = 0;
        for (const language of ['ar', 'en']) {
            for (const surface of ['home', 'contact']) {
                await navigate(`${surface}-${language}`);
                for (const [width, height] of mapViewports) {
                    await resize(width, height, width < 768);
                    await evaluate(`(async () => {
                        const map = document.querySelector('.home-map-preview, .contact-map-panel');
                        map.scrollIntoView({ block: 'center', behavior: 'instant' });
                        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                        const img = map.querySelector('img');
                        try { await img.decode(); } catch (error) {
                            const response = await fetch(img.src);
                            throw new Error('Map image failed to decode: ' + JSON.stringify({
                                src: img.src, status: response.status,
                                type: response.headers.get('content-type'),
                                bytes: (await response.arrayBuffer()).byteLength,
                            }));
                        }
                        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                    })()`);
                    const result = await evaluate(`(() => {
                        const errors = [];
                        const map = document.querySelector('.home-map-preview, .contact-map-panel');
                        const img = map.querySelector('img');
                        const visual = map.querySelector('.location-map-visual');
                        const cta = map.querySelector('.map-open-link');
                        const directions = document.querySelector('.contact-actions .btn-secondary, .contact-page-actions .btn-secondary');
                        const details = document.querySelector('.home-contact-copy, .contact-details-panel');
                        const b = img.getBoundingClientRect(), panel = map.getBoundingClientRect();
                        const style = getComputedStyle(img);
                        if (!img.complete || img.naturalWidth !== 1536 || img.naturalHeight !== 1024 || b.width <= 0) errors.push('image missing');
                        if (Math.abs(b.height - b.width * 1024 / 1536) > 1) errors.push('distorted image');
                        if (style.objectFit === 'cover' || style.clipPath !== 'none' || style.transform !== 'none') errors.push('cropped or transformed image');
                        if (map.querySelector('iframe')) errors.push('iframe remains');
                        if (img.getAttribute('src') !== '/static/img/location/clinic-location-illustrated-map.png') errors.push('wrong asset');
                        if (document.documentElement.scrollWidth > innerWidth + 1) errors.push('horizontal overflow');
                        if (panel.height > b.height + 140) errors.push('unexpected blank map height');
                        for (let el = img.parentElement; el; el = el.parentElement) {
                            const css = getComputedStyle(el), r = el.getBoundingClientRect();
                            if (['hidden', 'clip', 'auto', 'scroll'].includes(css.overflowX) && (b.left < r.left - 1 || b.right > r.right + 1)) errors.push('horizontal artwork clipping');
                            if (['hidden', 'clip', 'auto', 'scroll'].includes(css.overflowY) && (b.top < r.top - 1 || b.bottom > r.bottom + 1)) errors.push('vertical artwork clipping');
                        }
                        const d = details.getBoundingClientRect(), c = cta.getBoundingClientRect();
                        const overlaps = (x, y) => Math.min(x.right, y.right) > Math.max(x.left, y.left) + 1 && Math.min(x.bottom, y.bottom) > Math.max(x.top, y.top) + 1;
                        if (overlaps(b, d) || overlaps(b, c)) errors.push('text or CTA overlaps artwork');
                        if (${width} >= 768 && (b.height > 600 || Math.abs(panel.top + panel.height / 2 - d.top - d.height / 2) > 2)) errors.push('unbalanced desktop map');
                        for (const link of [visual, cta, directions]) {
                            if (!link || link.href !== directions.href || link.target !== '_blank' || !link.relList.contains('noopener') || !link.relList.contains('noreferrer')) errors.push('navigation contract');
                            link.scrollIntoView({ block: 'center', behavior: 'instant' });
                            const r = link.getBoundingClientRect();
                            if (!link.contains(document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2))) errors.push('navigation covered or unreachable');
                        }
                        // Every area can be brought clear of fixed mobile chrome by normal scrolling.
                        for (const fraction of [0.08, 0.5, 0.92]) {
                            const r = img.getBoundingClientRect();
                            window.scrollTo({ top: scrollY + r.top + r.height * fraction - innerHeight / 2, behavior: 'instant' });
                            const moved = img.getBoundingClientRect();
                            for (const x of [0.08, 0.5, 0.92]) {
                                if (!visual.contains(document.elementFromPoint(moved.left + moved.width * x, moved.top + moved.height * fraction))) errors.push('artwork covered by fixed chrome');
                            }
                        }
                        return { errors, direction: document.documentElement.dir };
                    })()`);
                    assert.deepEqual(result.errors, [], `${surface}/${language} ${width}x${height}: ${JSON.stringify(result)}`);
                    assert.equal(result.direction, language === 'ar' ? 'rtl' : 'ltr');
                    illustratedMaps++;
                    if (process.env.KBC_LOCATION_QA_DIR) {
                        await evaluate(`document.querySelector('.home-map-preview, .contact-map-panel').scrollIntoView({ block: 'center', behavior: 'instant' })`);
                        const shot = await send('Page.captureScreenshot', { format: 'png' });
                        fs.mkdirSync(process.env.KBC_LOCATION_QA_DIR, { recursive: true });
                        fs.writeFileSync(path.join(process.env.KBC_LOCATION_QA_DIR, `${surface}-${language}-${width}x${height}.png`), Buffer.from(shot.data, 'base64'));
                    }
                }
            }
        }
        const widths = [320, 360, 375, 390, 412, 430, 479, 480, 540, 600, 639, 640, 641, 667, 719, 720, 767, 768, 799, 800, 844, 899, 900, 1023, 1024, 1279, 1280, 1440];
        let reviews = 0, folders = 0, notifications = 0, rotations = 0, closeout = 0;
        for (const language of ["ar", "en"]) {
            for (const surface of ["home", "contact", "case-detail", "medical-records", "consultation-patient", "consultation-staff", "folder-delete", "link", "link-errors"]) {
                await navigate(`${surface}-${language}`);
                for (const width of widths) {
                    for (const height of [260, 844]) {
                        await resize(width, height);
                        const result = await evaluate(`(() => {
                            const failures = [];
                            const surface = ${JSON.stringify(surface)};
                            const selectors = {
                                'case-detail': '.public-case-detail-hero h1, .public-case-detail-hero p, .public-case-detail-note-card',
                                'medical-records': '.portal-rich-text, .portal-media-card h3',
                                'consultation-patient': '.portal-media-meta',
                                'consultation-staff': '.portal-media-meta',
                                'folder-delete': '#folder-delete-title',
                            };
                            const nodes = selectors[surface] ? [...document.querySelectorAll(selectors[surface])] : [];
                            for (const el of nodes) {
                                const bounds = el.getBoundingClientRect();
                                // pre-wrap may hang trailing spaces outside a line.
                                // Check visible words, including every fragment of an
                                // unbroken filename/URL, rather than those spaces.
                                const rects = [];
                                const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
                                let text;
                                while ((text = walker.nextNode())) {
                                    for (const word of text.textContent.matchAll(/\\S+/g)) {
                                        const range = document.createRange();
                                        range.setStart(text, word.index);
                                        range.setEnd(text, word.index + word[0].length);
                                        rects.push(...range.getClientRects());
                                    }
                                }
                                if (rects.some(r => r.left < bounds.left - 1 || r.right > bounds.right + 1)) {
                                    failures.push({ kind: 'clipped-text', text: el.textContent.slice(0, 30), bounds: bounds.toJSON() });
                                }
                            }
                            const map = document.querySelector('.home-map-preview, .contact-map-panel');
                            if (map && map.getBoundingClientRect().width) {
                                const bounds = map.getBoundingClientRect();
                                const link = map.querySelector('.map-open-link');
                                const rect = link.getBoundingClientRect();
                                if (rect.left < bounds.left || rect.right > bounds.right || Math.abs((rect.left + rect.right) - (bounds.left + bounds.right)) > 2) {
                                    failures.push({ kind: 'map-link-outside-or-off-center', rect: rect.toJSON(), bounds: bounds.toJSON() });
                                }
                                link.scrollIntoView({ block: 'center', behavior: 'instant' });
                                const target = link.getBoundingClientRect();
                                if (!link.contains(document.elementFromPoint((target.left + target.right) / 2, (target.top + target.bottom) / 2))) failures.push({ kind: 'map-link-unreachable' });
                            }
                            if (surface.startsWith('link')) {
                                const actions = document.querySelector('.patient-form-actions');
                                const recovery = document.querySelector('.patient-card-body > .muted > a');
                                const gap = recovery.getBoundingClientRect().top - actions.getBoundingClientRect().bottom;
                                const expected = parseFloat(getComputedStyle(actions).rowGap);
                                if (Math.abs(gap - expected) > 1) failures.push({ kind: 'recovery-action-gap', gap, expected });
                            }
                            return { failures, count: nodes.length, expectsText: !!selectors[surface], direction: document.documentElement.dir,
                                width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth };
                        })()`);
                        const label = `${surface}/${language} ${width}x${height}`;
                        assert(!result.expectsText || result.count > 0, `${label}: missing stress fixture`);
                        assert.equal(result.direction, language === 'ar' ? 'rtl' : 'ltr', label);
                        assert.equal(result.failures.length, 0, `${label}: ${JSON.stringify(result.failures)}`);
                        assert(result.scrollWidth <= result.width, `${label}: horizontal overflow ${JSON.stringify(result)}`);
                        closeout++;
                    }
                }
            }
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
                for (const [width, height] of [[640, 260], [641, 288], [390, 844],
                    [1024, 768], [1120, 768], [1920, 1080], [1024, 768], [390, 844]]) {
                    await evaluate("document.querySelector('.consultation-notification-panel:not([hidden]) .consultation-notification-panel-actions a').focus({preventScroll: true})");
                    await resize(width, height);
                    await evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))");
                    await checkNotification(`open rotation ${surface}/${language} ${width}x${height}`);
                    assert(await evaluate(`document.activeElement.matches('.consultation-notification-panel-actions a') &&
                        document.activeElement.getBoundingClientRect().width > 0`),
                    `${surface}/${language} ${width}x${height}: keyboard focus follows the visible panel`);
                    rotations++;
                }
                await evaluate(`(() => {
                    const panel = document.querySelector('.consultation-notification-panel:not([hidden])');
                    panel.querySelector('.consultation-notification-panel-actions a').focus();
                    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
                })()`);
                assert(await evaluate(`(() => {
                    const trigger = document.activeElement;
                    return trigger.matches('.consultation-notification-trigger') &&
                        trigger.getBoundingClientRect().width > 0 &&
                        !document.querySelector('.consultation-notification-panel:not([hidden])');
                })()`), `${surface}/${language}: Escape closes resized panel and restores visible focus`);
                await resize(1920, 1080);
                await evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))");
                assert(await evaluate("!document.querySelector('.consultation-notification-panel:not([hidden])')"),
                    `${surface}/${language}: resize must not reopen a closed panel`);
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
                const root = panel.closest('[data-consultation-notifications]');
                const expanded = root.querySelector('.consultation-notification-trigger').getAttribute('aria-expanded');
                return { count: buttons.length, height: list.clientHeight, scrollHeight: list.scrollHeight,
                    expanded, openPanels: document.querySelectorAll('.consultation-notification-panel:not([hidden])').length,
                    firstReachable, lastReachable, actionsReachable: actionControls.every(el => hit(el, bounds)),
                    headerVisible: header.getBoundingClientRect().top >= bounds.top,
                    fits: bounds.top >= 0 && bounds.bottom <= innerHeight && bounds.left >= 0 && bounds.right <= innerWidth,
                    bounds: bounds.toJSON(), viewport: [innerWidth, innerHeight] };
            })()`);
            assert(!result.missing && result.count >= 8, `${label}: notification fixture ${JSON.stringify(result)}`);
            assert(result.expanded === "true" && result.openPanels === 1, `${label}: one accessible open panel`);
            assert(result.height >= 48 && result.fits && result.headerVisible && result.actionsReachable,
                `${label}: panel usability ${JSON.stringify(result)}`);
            assert(result.firstReachable && result.lastReachable, `${label}: entries inaccessible ${JSON.stringify(result)}`);
        }
        console.log(`PASS: ${illustratedMaps} approved illustrated map cases (Home/Contact, AR/EN, 14 exact viewports); ${closeout} additional closeout cases (maps, case details, medical text, attachment names, folder deletion, link actions); ${reviews} Home/Reviews long-content cases; ${folders} medical-folder text geometry cases; ${notifications} notification viewport cases; ${rotations} open-panel rotations (AR/EN).`);
    } finally {
        if (send && ws?.readyState === WebSocket.OPEN) { send("Browser.close").catch(() => {}); await delay(300); }
        server.close();
        await launcher?.stop();
    }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
