"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const root = path.resolve(__dirname, "../../..");
const workerSource = fs.readFileSync(path.join(root, "static/sw.js"), "utf8");
const controlSource = fs.readFileSync(path.join(root, "static/js/phone-notifications.js"), "utf8");
const plain = data => JSON.parse(JSON.stringify(data));

function worker(windows = []) {
    const handlers = {}, shown = [], opened = [], closed = [];
    const self = {
        location: { origin: "https://clinic.example" },
        registration: { showNotification: async (title, options) => shown.push({ title, ...plain(options) }) },
        clients: {
            matchAll: async options => { assert.deepEqual(plain(options), { type: "window", includeUncontrolled: true }); return windows; },
            openWindow: async url => opened.push(url), claim: async () => {},
        },
        skipWaiting: () => {},
        addEventListener: (name, callback) => { handlers[name] = callback; },
    };
    vm.runInNewContext(workerSource, { self, URL });
    async function emit(name, data, invalidJSON = false) {
        const pending = [];
        handlers[name]({
            data: { json: () => { if (invalidJSON) throw new Error("invalid"); return data; } },
            notification: { data, close: () => closed.push(true) },
            waitUntil: promise => pending.push(promise),
        });
        await Promise.all(pending);
    }
    return { shown, opened, closed, emit, handlers };
}

test("fixed AR/EN copy, no private text/options, stable collapse tags and no intrusive behavior", async () => {
    const sw = worker();
    for (const event of ["new-consultation", "new-booking"]) {
        for (const language of ["ar", "en"]) {
            for (let i = 0; i < 2; i++) {
                await sw.emit("push", { event, language, title: "PRIVATE name", body: "PRIVATE diagnosis", url: "https://evil.test/private-id", requireInteraction: true, vibrate: [100] });
                const notification = sw.shown.at(-1);
                assert.equal(notification.tag, "kbc-" + event);
                assert.equal(notification.requireInteraction, false);
                assert.equal(notification.renotify, false);
                assert.equal(notification.dir, language === "ar" ? "rtl" : "ltr");
                assert.deepEqual(notification.data, { event, language });
                assert(!JSON.stringify(notification).includes("PRIVATE"));
                for (const option of ["vibrate", "sound", "image", "actions", "badge"]) assert(!(option in notification));
                assert.equal(notification.title, event === "new-consultation" ? (language === "ar" ? "استشارة جديدة" : "New consultation") : (language === "ar" ? "موعد جديد" : "New appointment"));
            }
        }
    }
    assert.equal(sw.shown[0].body, "لديك استشارة جديدة في العيادة.");
    assert.equal(sw.shown[4].body, "تم حجز موعد جديد عبر الموقع.");
    assert.equal(sw.shown.length, 8);
    assert(!("fetch" in sw.handlers));
});

test("malformed and unapproved events cannot display supplied content or route a click", async () => {
    const sw = worker();
    for (const data of [null, {}, [], { event: "reply", language: "ar" }, { event: "__proto__", language: "ar" }, { event: "new-booking", language: "fr" }]) {
        await sw.emit("push", data);
        await sw.emit("notificationclick", data);
    }
    await sw.emit("push", {}, true);
    assert.equal(sw.shown.length, 0);
    assert.equal(sw.opened.length, 0);
});

test("click opens only the protected category list in the subscription language", async () => {
    const sw = worker();
    for (const [event, route] of [["new-consultation", "/dashboard/consultations/"], ["new-booking", "/staff/appointments/"]]) {
        for (const language of ["ar", "en"]) {
            await sw.emit("notificationclick", { event, language, url: "https://evil.test/", path: "/private/media/123" });
            assert.equal(sw.opened.at(-1), "https://clinic.example" + route + (language === "en" ? "?lang=en" : ""));
        }
    }
    assert.equal(sw.closed.length, 4);
});

test("click navigates and focuses an existing staff window, and reuses an exact destination", async () => {
    let navigated = [], focused = 0;
    const client = { url: "https://clinic.example/dashboard/", navigate: async url => { navigated.push(url); client.url = url; return client; }, focus: async () => { focused++; } };
    const sw = worker([client]);
    for (let i = 0; i < 2; i++) await sw.emit("notificationclick", { event: "new-booking", language: "en" });
    assert.deepEqual(navigated, ["https://clinic.example/staff/appointments/?lang=en"]);
    assert.equal(focused, 2);
    assert.equal(sw.opened.length, 0);
});

test("unrelated windows are left alone and a closing staff window falls back to openWindow", async () => {
    const sw = worker([
        { url: "https://evil.test/dashboard/", navigate: () => assert.fail("cross-origin") },
        { url: "https://clinic.example/portal/", navigate: () => assert.fail("patient window") },
        { url: "https://clinic.example/dashboard/", navigate: async () => { throw new Error("closing"); } },
    ]);
    await sw.emit("notificationclick", { event: "new-consultation", language: "ar" });
    assert.deepEqual(sw.opened, ["https://clinic.example/dashboard/consultations/"]);
});

const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
async function control(options = {}) {
    const calls = [], listeners = {}, status = { textContent: "" };
    let gesture = false, current = options.existing ? { endpoint: "https://fcm.googleapis.com/wp/synthetic" } : null;
    const makeSubscription = () => ({
        endpoint: "https://fcm.googleapis.com/wp/synthetic",
        toJSON() { return { endpoint: this.endpoint, keys: { p256dh: "synthetic", auth: "synthetic" } }; },
        async unsubscribe() { calls.push("browser-unsubscribe"); if (options.localUnsubscribeFailure) return false; current = null; return true; },
    });
    if (current) current = makeSubscription();
    const button = name => ({ disabled: name === "enable", hidden: name === "disable", addEventListener: (_, callback) => { listeners[name] = callback; } });
    const enable = button("enable"), disable = button("disable");
    const dataset = {
        configUrl: "/config", statusUrl: "/status", subscribeUrl: "/subscribe", unsubscribeUrl: "/unsubscribe", workerUrl: "/sw.js",
        language: options.language || "ar", enabled: "enabled", disabled: "disabled", unavailable: "unavailable", unsupported: "unsupported", denied: "denied", error: "error",
    };
    const panel = { dataset, querySelector: selector => ({ "[data-phone-enable]": enable, "[data-phone-disable]": disable, "[data-phone-status]": status, '[name="csrfmiddlewaretoken"]': { value: "synthetic-csrf" } })[selector] };
    const registration = { pushManager: {
        getSubscription: async () => { calls.push("get-subscription"); return current; },
        subscribe: async data => { calls.push(["browser-subscribe", plain(data)]); current = makeSubscription(); return current; },
    } };
    const Notification = { permission: options.permission || "default", requestPermission: async () => {
        assert(gesture, "Permission must be called directly inside a user gesture"); calls.push("permission"); return options.permission || "granted";
    } };
    const navigator = {
        userAgent: options.ios ? "iPhone" : "Android Chrome", platform: "", maxTouchPoints: 1, standalone: !!options.standalone,
        serviceWorker: { ready: Promise.resolve(registration), register: async (url, data) => { calls.push(["register", url, plain(data)]); return registration; } },
    };
    const window = { isSecureContext: !options.insecure, Notification, PushManager: {}, matchMedia: () => ({ matches: !!options.standalone }) };
    if (options.unsupported) delete window.PushManager;
    vm.runInNewContext(controlSource, {
        document: { querySelector: () => panel }, window, navigator, Notification, Uint8Array, atob,
        fetch: async (url, data) => {
            calls.push(["fetch", url, plain(data)]);
            if (url === options.failUrl) return { ok: false, status: 503 };
            return { ok: true, json: async () => url === "/config" ? { available: options.available !== false, publicKey: "BA" } : { subscribed: options.subscribed !== false } };
        },
    });
    await settle();
    return { enable, disable, status, calls, async click(name) { gesture = true; const pending = listeners[name](); gesture = false; await pending; await settle(); } };
}

test("page load never requests permission or subscribes; explicit enable saves with CSRF", async () => {
    for (const language of ["ar", "en"]) {
        const ui = await control({ language });
        assert(!ui.calls.includes("permission"));
        assert(!ui.calls.some(item => item[0] === "browser-subscribe"));
        assert.equal(ui.status.textContent, "disabled");
        assert.equal(ui.enable.disabled, false);
        await ui.click("enable");
        assert.equal(ui.status.textContent, "enabled");
        assert.equal(ui.disable.hidden, false);
        const subscribe = ui.calls.find(item => item[0] === "browser-subscribe");
        assert.equal(subscribe[1].userVisibleOnly, true);
        const save = ui.calls.find(item => item[0] === "fetch" && item[1] === "/subscribe")[2];
        assert.equal(save.method, "POST");
        assert.equal(save.credentials, "same-origin");
        assert.equal(save.redirect, "error");
        assert.equal(save.headers["X-CSRFToken"], "synthetic-csrf");
        assert.equal(JSON.parse(save.body).language, language);
    }
});

test("denied and dismissed permission do not subscribe", async () => {
    for (const permission of ["denied", "default"]) {
        const ui = await control({ permission });
        await ui.click("enable");
        assert.equal(ui.status.textContent, "denied");
        assert(!ui.calls.some(item => item[0] === "browser-subscribe"));
    }
});

test("iOS requires Home Screen; installed iOS retains gesture-driven permission", async () => {
    const safari = await control({ ios: true });
    assert.equal(safari.status.textContent, "unsupported");
    assert.equal(safari.calls.length, 0);
    const installed = await control({ ios: true, standalone: true });
    await installed.click("enable");
    assert(installed.calls.includes("permission"));
    assert.equal(installed.status.textContent, "enabled");
});

test("unsupported/insecure contexts and unconfigured backend show clear unavailable states", async () => {
    for (const options of [{ unsupported: true }, { insecure: true }, { available: false }]) {
        const ui = await control(options);
        assert.equal(ui.enable.disabled, true);
        assert(!ui.calls.includes("permission"));
        assert(["unsupported", "unavailable"].includes(ui.status.textContent));
    }
});

test("existing subscription is checked for current staff ownership without resubscribing", async () => {
    const ui = await control({ existing: true, subscribed: false });
    assert.equal(ui.status.textContent, "disabled");
    assert(!ui.calls.includes("permission"));
    assert(!ui.calls.some(item => item[0] === "browser-subscribe"));
    assert(ui.calls.some(item => item[0] === "fetch" && item[1] === "/status"));
    await ui.click("enable");
    assert(!ui.calls.some(item => item[0] === "browser-subscribe"));
    assert.equal(ui.status.textContent, "enabled");
});

test("disable deletes server subscription and unsubscribes browser even if backend push is off", async () => {
    const ui = await control({ existing: true, available: false });
    assert.equal(ui.disable.hidden, false);
    await ui.click("disable");
    assert.equal(ui.status.textContent, "disabled");
    assert.equal(ui.disable.hidden, true);
    const removal = ui.calls.find(item => item[0] === "fetch" && item[1] === "/unsubscribe");
    assert.equal(removal[2].method, "POST");
    assert(ui.calls.includes("browser-unsubscribe"));
    assert(!ui.calls.includes("permission"));
});

test("failed save/unsubscribe never claims success and preserves a retry action", async () => {
    const save = await control({ failUrl: "/subscribe" });
    await save.click("enable");
    assert.equal(save.status.textContent, "error");
    assert.equal(save.enable.disabled, false);
    assert.equal(save.disable.hidden, false);
    for (const options of [{ failUrl: "/unsubscribe" }, { localUnsubscribeFailure: true }]) {
        const remove = await control({ existing: true, ...options });
        await remove.click("disable");
        assert.equal(remove.status.textContent, "error");
        assert.equal(remove.disable.hidden, false);
        assert.equal(remove.disable.disabled, false);
    }
});
