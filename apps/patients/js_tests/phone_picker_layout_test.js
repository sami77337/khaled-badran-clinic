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
const pickerTokens = [...new Set([...fs.readFileSync(path.join(root, "static/css/auth-phone.css"), "utf8")
    .matchAll(/var\(\s*(--auth-[\w-]+)/g)].map(match => match[1]))];
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
        for (const width of [320, 360, 390, 412, 640]) {
            await send("Emulation.setDeviceMetricsOverride", { width, height: 844, deviceScaleFactor: 1, mobile: true });
            for (const language of ["ar", "en"]) {
                let reference;
                const pageNames = ["login", "register", "link", "phone", "link-errors", "phone-errors"];
                if (pages[`before-login-${language}`]) pageNames.push("before-login", "before-link");
                for (const page of pageNames) {
                    await send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${page}-${language}` });
                    for (let i = 0; i < 100; i++) {
                        if (await evaluate(`document.readyState === 'complete' && (() => { const c = document.querySelector('[data-booking-phone-control]'); return !!(c?.bookingComposeNumber || c?.composePhoneNumber); })()`)) break;
                        await delay(20);
                    }
                    // Give every picker the same available parent width when comparing
                    // its appearance; portal cards intentionally have different gutters.
                    const result = await evaluate(`(async () => {
                        await document.fonts.ready;
                        const control = document.querySelector('[data-booking-phone-control]');
                        control.style.width = '${width - 100}px';
                        const trigger = control.querySelector('[data-booking-country-trigger]');
                        const menu = control.querySelector('[data-booking-country-menu]');
                        const search = control.querySelector('[data-booking-country-search]');
                        const options = control.querySelector('[data-booking-country-options]');
                        trigger.click();
                        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                        const noSearchFocus = document.activeElement !== search;
                        const selectors = ['.booking-phone-row', '.booking-country-trigger', '.booking-country-flag', '.booking-country-dial', '.booking-icon-chevron', '.booking-phone-row > input', '.booking-country-menu', '.booking-country-search-label', '.booking-country-search', '.booking-country-options', '[data-booking-country-option]', '[data-booking-country-option] bdi'];
                        const properties = ['display', 'position', 'fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'borderTop', 'borderRight', 'borderBottom', 'borderLeft', 'borderRadius', 'boxShadow', 'backgroundColor', 'color', 'gap', 'gridTemplateColumns', 'overflowX', 'overflowY', 'textAlign', 'direction'];
                        const styles = Object.fromEntries(selectors.map(selector => {
                            const el = control.querySelector(selector), css = getComputedStyle(el);
                            return [selector, Object.fromEntries(properties.map(p => [p, css[p]]))];
                        }));
                        const rect = el => { const r=el.getBoundingClientRect(); return {top:r.top,bottom:r.bottom,width:r.width,height:r.height}; };
                        const unresolvedTokens = ${JSON.stringify(pickerTokens)}.filter(token => !getComputedStyle(control).getPropertyValue(token).trim());
                        const portalForm = control.closest('.patient-form');
                        const surrounding = portalForm ? [portalForm, ...portalForm.querySelectorAll('.form-field, .form-field > label, .form-field > input, .patient-form-actions')] : [];
                        const formChrome = () => surrounding.map(el => {
                            const css = getComputedStyle(el);
                            const properties = ['gap', 'fontSize', 'lineHeight', 'padding', 'border', 'borderRadius'];
                            if (!el.contains(control)) properties.push('height');
                            return properties.map(p => css[p]);
                        });
                        const surroundingBefore = formChrome();
                        const pickerSheet = [...document.styleSheets].find(sheet => sheet.href?.endsWith('/auth-phone.css'));
                        if (portalForm && pickerSheet) pickerSheet.disabled = true;
                        const surroundingAfter = formChrome();
                        if (portalForm && pickerSheet) pickerSheet.disabled = false;
                        const formIsolated = JSON.stringify(surroundingBefore) === JSON.stringify(surroundingAfter);
                        const dimensions = { trigger: rect(trigger), menu: rect(menu), row: rect(control.querySelector('.booking-phone-row')), option: rect(options.querySelector('button')) };
                        const field = control.parentElement;
                        const following = field.nextElementSibling;
                        const noOverlap = rect(control).bottom <= rect(field).bottom + 1 && (!following || rect(following).top >= rect(field).bottom - 1);
                        const before = field.previousElementSibling;
                        const precedingClear = !before || rect(before).bottom <= rect(field).top + 1;
                        const nav = document.querySelector('[data-mobile-bottom-navigation]');
                        const navClear = !nav || rect(menu).bottom <= rect(nav).top;
                        const overflow = document.documentElement.scrollWidth > innerWidth;
                        options.scrollTop = 100;
                        const scrolls = options.scrollTop > 0;
                        search.focus();
                        const deliberateFocus = document.activeElement === search;
                        search.value = 'Canada';
                        search.dispatchEvent(new Event('input', {bubbles:true}));
                        const option = options.querySelector('[data-country-code="CA"]');
                        const filtered = !option.hidden && options.querySelector('[data-country-code="JO"]').hidden;
                        option.click();
                        const closed = menu.hidden && trigger.getAttribute('aria-expanded') === 'false';
                        const input = control.querySelector('.booking-phone-row > input');
                        const selectionFocus = document.activeElement === trigger;
                        input.focus();
                        const inputUsable = document.activeElement === input && !input.disabled;
                        input.value = '4165550123';
                        const e164 = new FormData(control.closest('form')).get(input.name);
                        trigger.click(); document.body.click(); const outsideCloses = menu.hidden;
                        trigger.click(); document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'})); const escapeCloses = menu.hidden;
                        const checkbox = document.querySelector('.patient-checkbox-field input');
                        control.style.removeProperty('width');
                        trigger.click();
                        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                        const nativeWidth = rect(menu).width === rect(control).width;
                        const nativeFlow = !following || rect(following).top >= rect(field).bottom - 1;
                        const nativeOverflow = document.documentElement.scrollWidth > innerWidth;
                        const nativeNavClear = !nav || rect(menu).bottom <= rect(nav).top;
                        return {styles, dimensions, unresolvedTokens, formIsolated, selectionFocus, nativeWidth, nativeFlow, nativeOverflow, nativeNavClear, noSearchFocus, noOverlap, precedingClear, navClear, overflow, scrolls, deliberateFocus, filtered, closed, inputUsable, e164, outsideCloses, escapeCloses, checkboxWidth:checkbox ? rect(checkbox).width : null, checkboxHeight:checkbox ? rect(checkbox).height : null, checkboxLabelHeight:checkbox ? rect(checkbox.closest('label')).height : null};
                    })()`);
                    const label = `${page}-${language} ${width}px`;
                    for (const key of ["nativeWidth", "nativeFlow", "nativeNavClear", "noSearchFocus", "noOverlap", "precedingClear", "navClear", "scrolls", "deliberateFocus", "filtered", "closed", "inputUsable", "outsideCloses", "escapeCloses"]) assert.equal(result[key], true, `${label}: ${key}`);
                    assert.equal(result.overflow, false, `${label}: horizontal overflow`);
                    assert.equal(result.nativeOverflow, false, `${label}: native horizontal overflow`);
                    if (page !== "before-link") {
                        assert.deepEqual(result.unresolvedTokens, [], `${label}: all picker visual tokens resolve`);
                        assert.equal(result.formIsolated, true, `${label}: picker CSS does not change Portal form chrome`);
                    }
                    assert.equal(result.selectionFocus, true, `${label}: selection restores trigger focus`);
                    assert.equal(result.e164, "+14165550123", `${label}: E.164 serialization`);
                    if (result.checkboxWidth !== null) {
                        assert(Math.abs(result.checkboxWidth - 17.6) < 1 && Math.abs(result.checkboxHeight - 17.6) < 1, `${label}: checkbox compact`);
                        assert(result.checkboxLabelHeight >= 44, `${label}: checkbox label touch area`);
                    }
                    if (page === "login") reference = result;
                    else if (page === "before-link") {
                        assert.notDeepEqual(result.styles, reference.styles, `${label}: reproduce the old visual mismatch`);
                        if (width === 390 && language === "en") {
                            console.log("Starting portal vs approved Login:", JSON.stringify({
                                old: result.dimensions, login: reference.dimensions,
                                oldSearchLabel: result.styles['.booking-country-search-label'],
                                loginSearchLabel: reference.styles['.booking-country-search-label'],
                            }));
                        }
                    } else {
                        assert.deepEqual(result.styles, reference.styles, `${label}: computed Login style parity`);
                        for (const part of ["trigger", "menu", "row", "option"]) {
                            for (const dimension of ["width", "height"]) assert(Math.abs(result.dimensions[part][dimension] - reference.dimensions[part][dimension]) < 1, `${label}: ${part} ${dimension}: ${result.dimensions[part][dimension]} vs Login ${reference.dimensions[part][dimension]}`);
                        }
                    }
                    // A reduced visual viewport exercises the same resize path used
                    // by the Android keyboard. OS keyboard appearance is owner QA.
                    await send("Emulation.setDeviceMetricsOverride", { width, height: 500, deviceScaleFactor: 1, mobile: true });
                    const keyboardFits = await evaluate(`(async () => {
                        const control = document.querySelector('[data-booking-phone-control]');
                        const menu = control.querySelector('[data-booking-country-menu]');
                        control.querySelector('[data-booking-country-search]').focus();
                        await new Promise(r => setTimeout(r, 700));
                        const nav = document.querySelector('[data-mobile-bottom-navigation]');
                        const header = document.querySelector('[data-portal-compact-header]');
                        const rect = menu.getBoundingClientRect();
                        const bottom = Math.min(visualViewport.offsetTop + visualViewport.height, nav?.getBoundingClientRect().top ?? Infinity);
                        const top = Math.max(visualViewport.offsetTop, header?.getBoundingClientRect().bottom ?? 0);
                        return {fits: rect.top >= top && rect.bottom <= bottom, top:rect.top, bottom:rect.bottom, safeTop:top, safeBottom:bottom};
                    })()`);
                    assert(keyboardFits.fits, `${label}: menu fits reduced keyboard viewport ${JSON.stringify(keyboardFits)}`);
                    if (process.env.KBC_QA_SCREENSHOTS && width === 390) {
                        fs.mkdirSync(process.env.KBC_QA_SCREENSHOTS, { recursive: true });
                        const screenshot = await send("Page.captureScreenshot", { format: "png" });
                        fs.writeFileSync(path.join(process.env.KBC_QA_SCREENSHOTS, `${page}-${language}.png`), Buffer.from(screenshot.data, "base64"));
                    }
                    await send("Emulation.setDeviceMetricsOverride", { width, height: 844, deviceScaleFactor: 1, mobile: true });
                    cases++;
                }
            }
        }
        console.log(`${cases} rendered mobile cases passed: Login/Register/Link/Phone plus Portal field errors, AR/EN, 320/360/390/412/640px; computed style parity, tokens, form isolation, checkbox, layout, scrolling, focus, closing, E.164.`);
        let landscapeCases = 0;
        for (const width of [640, 667, 720, 740, 800, 844, 900]) {
            for (const language of ["ar", "en"]) {
                for (const page of ["link", "phone"]) {
                    await send("Emulation.setDeviceMetricsOverride", { width, height: 360, deviceScaleFactor: 1, mobile: true });
                    await send("Page.navigate", { url: `http://127.0.0.1:${server.address().port}/${page}-${language}` });
                    for (let i = 0; i < 100; i++) {
                        if (await evaluate(`document.readyState === 'complete' && (() => { const c = document.querySelector('[data-booking-phone-control]'); return !!(c?.bookingComposeNumber || c?.composePhoneNumber); })()`)) break;
                        await delay(20);
                    }
                    const layout = await evaluate(`(async () => {
                        await document.fonts.ready;
                        const control = document.querySelector('[data-booking-phone-control]');
                        const trigger = control.querySelector('[data-booking-country-trigger]');
                        const menu = control.querySelector('[data-booking-country-menu]');
                        const options = control.querySelector('[data-booking-country-options]');
                        const field = control.parentElement;
                        const following = field.nextElementSibling;
                        const closedTop = following.getBoundingClientRect().top + scrollY;
                        trigger.scrollIntoView({block:'center'});
                        trigger.click();
                        await new Promise(r => setTimeout(r, 100));
                        const rect = menu.getBoundingClientRect();
                        const header = document.querySelector('[data-portal-compact-header]');
                        const nav = document.querySelector('[data-mobile-bottom-navigation]');
                        const safeTop = Math.max(visualViewport.offsetTop, header.getBoundingClientRect().bottom);
                        const safeBottom = Math.min(visualViewport.offsetTop + visualViewport.height,
                            nav.getClientRects().length ? nav.getBoundingClientRect().top : Infinity);
                        options.scrollTop = options.scrollHeight;
                        return {position:getComputedStyle(menu).position, top:rect.top, bottom:rect.bottom, safeTop, safeBottom,
                            pushes:following.getBoundingClientRect().top + scrollY > closedTop + rect.height,
                            contained:rect.bottom <= field.getBoundingClientRect().bottom,
                            scrollable:options.scrollTop > 0,
                            overflow:document.documentElement.scrollWidth > innerWidth};
                    })()`);
                    const label = `${page}-${language} ${width}x360 landscape`;
                    assert.equal(layout.position, "static", `${label}: menu must occupy document flow ${JSON.stringify(layout)}`);
                    assert(layout.pushes && layout.contained, `${label}: following fields must move below menu ${JSON.stringify(layout)}`);
                    assert(layout.top >= layout.safeTop && layout.bottom <= layout.safeBottom, `${label}: fixed chrome clearance ${JSON.stringify(layout)}`);
                    assert(layout.scrollable && !layout.overflow, `${label}: scrollable options without horizontal overflow`);
                    await send("Emulation.setDeviceMetricsOverride", { width, height: 260, deviceScaleFactor: 1, mobile: true });
                    const reduced = await evaluate(`(async () => {
                        const control = document.querySelector('[data-booking-phone-control]');
                        control.querySelector('[data-booking-country-search]').focus();
                        await new Promise(r => setTimeout(r, 100));
                        const menuElement = control.querySelector('[data-booking-country-menu]');
                        const menu = menuElement.getBoundingClientRect();
                        const header = document.querySelector('[data-portal-compact-header]').getBoundingClientRect();
                        const nav = document.querySelector('[data-mobile-bottom-navigation]');
                        const top = Math.max(visualViewport.offsetTop, header.bottom);
                        const bottom = Math.min(visualViewport.offsetTop + visualViewport.height,
                            nav.getClientRects().length ? nav.getBoundingClientRect().top : Infinity);
                        const options = control.querySelector('[data-booking-country-options]');
                        options.scrollTop = options.scrollHeight;
                        menuElement.scrollTop = menuElement.scrollHeight;
                        const lastOption = options.lastElementChild;
                        const lastRect = lastOption.getBoundingClientRect();
                        const trigger = control.querySelector('[data-booking-country-trigger]');
                        const focus = trigger.focus.bind(trigger);
                        let focusScrollDelta = 0;
                        trigger.focus = (...args) => { const before = scrollY; focus(...args); focusScrollDelta = scrollY - before; };
                        const scrollable = options.scrollTop > 0;
                        lastOption.click();
                        const selected = menuElement.hidden && document.activeElement === trigger
                            && control.dataset.bookingCountryCode === lastOption.dataset.countryCode;
                        return {fits:menu.top >= top && menu.bottom <= bottom, scrollable, selected, focusScrollDelta,
                            lastOptionReachable:lastRect.top >= top && lastRect.bottom <= bottom,
                            top:menu.top, bottom:menu.bottom, safeTop:top, safeBottom:bottom};
                    })()`);
                    assert(reduced.fits && reduced.scrollable, `${label}: reduced landscape viewport ${JSON.stringify(reduced)}`);
                    assert(reduced.lastOptionReachable && reduced.selected && Math.abs(reduced.focusScrollDelta) < 1, `${label}: bottom option selection stays usable without focus scrolling ${JSON.stringify(reduced)}`);
                    landscapeCases++;
                }
            }
        }
        console.log(`${landscapeCases} Portal landscape cases passed: Link/Phone, AR/EN, 640/667/720/740/800/844/900px.`);
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
