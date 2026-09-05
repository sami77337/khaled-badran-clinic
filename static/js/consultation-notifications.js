(() => {
    "use strict";

    const roots = Array.from(document.querySelectorAll("[data-consultation-notifications]"));
    if (!roots.length) {
        return;
    }

    const close = (root, { restoreFocus = false } = {}) => {
        const trigger = root.querySelector("[data-consultation-notification-trigger]");
        const panel = root.querySelector("[data-consultation-notification-panel]");
        if (!trigger || !panel || panel.hidden) {
            return;
        }
        panel.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
        if (restoreFocus) {
            trigger.focus({ preventScroll: true });
        }
    };

    const closeOthers = (currentRoot) => {
        roots.forEach((root) => {
            if (root !== currentRoot) {
                close(root);
            }
        });
    };

    roots.forEach((root) => {
        const trigger = root.querySelector("[data-consultation-notification-trigger]");
        const panel = root.querySelector("[data-consultation-notification-panel]");
        if (!trigger || !panel) {
            return;
        }
        panel.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
        trigger.addEventListener("click", () => {
            const willOpen = panel.hidden;
            closeOthers(root);
            panel.hidden = !willOpen;
            trigger.setAttribute("aria-expanded", String(willOpen));
        });
    });

    document.addEventListener("click", (event) => {
        roots.forEach((root) => {
            if (!root.contains(event.target)) {
                close(root);
            }
        });
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }
        roots.forEach((root) => {
            const panel = root.querySelector("[data-consultation-notification-panel]");
            if (panel && !panel.hidden) {
                event.preventDefault();
                close(root, { restoreFocus: true });
            }
        });
    });
})();
