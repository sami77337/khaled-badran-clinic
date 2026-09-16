(() => {
    "use strict";
    const buttons = [...document.querySelectorAll("[data-install-app]")];
    const sheet = document.querySelector("[data-install-sheet]");
    if (!buttons.length || !sheet) return;

    const standalone = window.matchMedia("(display-mode: standalone)");
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
        || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    let installEvent = null;
    let installed = false;
    let prompting = false;
    const isInstalled = () => installed || standalone.matches || navigator.standalone === true;
    const refresh = () => {
        buttons.forEach(button => {
            button.hidden = isInstalled();
            button.disabled = prompting;
        });
        if (isInstalled() && sheet.open) sheet.close();
    };

    window.addEventListener("beforeinstallprompt", event => {
        event.preventDefault();
        installEvent = event;
        refresh();
    });
    window.addEventListener("appinstalled", () => {
        installed = true;
        installEvent = null;
        refresh();
    });
    standalone.addEventListener("change", refresh);
    buttons.forEach(button => button.addEventListener("click", async () => {
        if (isInstalled() || prompting) return;
        if (installEvent) {
            const event = installEvent;
            // A deferred browser event is single-use, including dismissal/errors.
            installEvent = null;
            prompting = true;
            refresh();
            try {
                await event.prompt();
                const choice = await event.userChoice;
                if (choice.outcome === "accepted") installed = true;
            } catch (_) {
                // Browser policy may withdraw the prompt; the manual path remains.
            } finally {
                prompting = false;
                refresh();
            }
            return;
        }
        sheet.querySelector("[data-install-ios]").hidden = !isIOS;
        sheet.querySelector("[data-install-browser]").hidden = isIOS;
        if (!sheet.open) sheet.showModal();
    }));
    refresh();

    // The existing root worker handles push only. It has no fetch/cache handler.
    // Registration never requests notification permission or creates subscriptions.
    if ("serviceWorker" in navigator && window.isSecureContext) {
        navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    }
})();
