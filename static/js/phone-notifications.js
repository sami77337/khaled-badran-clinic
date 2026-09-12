(() => {
    "use strict";
    const panel = document.querySelector("[data-phone-notifications]");
    if (!panel) return;
    const enable = panel.querySelector("[data-phone-enable]");
    const disable = panel.querySelector("[data-phone-disable]");
    const status = panel.querySelector("[data-phone-status]");
    const csrf = panel.querySelector('[name="csrfmiddlewaretoken"]').value;
    let registration, subscription, config, busy = false, subscribed = false;
    const message = key => { status.textContent = panel.dataset[key]; };
    const render = () => {
        enable.disabled = busy || !config?.available || !registration;
        enable.hidden = subscribed;
        disable.hidden = !subscription;
        disable.disabled = busy;
    };
    async function api(url, body) {
        const response = await fetch(url, {
            method: body === undefined ? "GET" : "POST",
            credentials: "same-origin", cache: "no-store", redirect: "error",
            headers: body === undefined ? {} : { "Content-Type": "application/json", "X-CSRFToken": csrf },
            ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        });
        if (!response.ok) throw new Error("Notification request failed.");
        return response.json();
    }
    const keyBytes = key => Uint8Array.from(atob(key.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - key.length % 4) % 4)), char => char.charCodeAt(0));

    async function unsubscribeBrowser() {
        await subscription.unsubscribe();
        // A subscription already removed in another tab may resolve false.
        // Confirm the current browser state before reporting success or failure.
        subscription = await registration.pushManager.getSubscription();
        if (subscription) throw new Error("Unsubscribe failed.");
    }

    enable.addEventListener("click", async () => {
        if (busy || !registration || !config?.available) return;
        busy = true;
        render();
        try {
            // Invoke directly in the click handler before any await/network work:
            // iOS Home Screen permission must retain the user's activation.
            const permission = await Notification.requestPermission();
            if (permission !== "granted") { message("denied"); return; }
            const publicKey = keyBytes(config.publicKey);
            if (subscription?.options?.applicationServerKey) {
                const currentKey = new Uint8Array(subscription.options.applicationServerKey);
                if (currentKey.length !== publicKey.length || currentKey.some((byte, i) => byte !== publicKey[i])) {
                    await api(panel.dataset.unsubscribeUrl, { endpoint: subscription.endpoint });
                    await unsubscribeBrowser();
                }
            }
            subscription = subscription || await registration.pushManager.subscribe({
                userVisibleOnly: true, applicationServerKey: publicKey,
            });
            await api(panel.dataset.subscribeUrl, { subscription: subscription.toJSON(), language: panel.dataset.language });
            subscribed = true;
            message("enabled");
        } catch (_) { message("error"); }
        finally { busy = false; render(); }
    });

    disable.addEventListener("click", async () => {
        if (busy || !subscription) return;
        busy = true;
        render();
        try {
            await api(panel.dataset.unsubscribeUrl, { endpoint: subscription.endpoint });
            subscribed = false;
            await unsubscribeBrowser();
            message("disabled");
        } catch (_) { message("error"); }
        finally { busy = false; render(); }
    });

    async function initialize() {
        const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
        const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
        if (!window.isSecureContext || !("serviceWorker" in navigator) || !("PushManager" in window)
                || !("Notification" in window) || (ios && !standalone)) {
            message("unsupported");
            return;
        }
        try {
            config = await api(panel.dataset.configUrl);
            await navigator.serviceWorker.register(panel.dataset.workerUrl, { scope: "/", updateViaCache: "none" });
            registration = await navigator.serviceWorker.ready;
            subscription = await registration.pushManager.getSubscription();
            if (subscription) {
                subscribed = (await api(panel.dataset.statusUrl, { endpoint: subscription.endpoint })).subscribed;
            }
            message(!config.available ? "unavailable" : subscribed ? "enabled" : "disabled");
        } catch (_) { message("error"); }
        finally { render(); }
    }
    // Read-only setup: no permission prompt or subscription on page load.
    initialize();
})();
