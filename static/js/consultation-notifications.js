(() => {
    "use strict";

    const roots = Array.from(document.querySelectorAll("[data-consultation-notifications]"));
    if (!roots.length) {
        return;
    }

    // Hiding a header can blur its focused control before the resize event.
    let focusedControl = document.activeElement;
    document.addEventListener("focusin", (event) => {
        focusedControl = event.target;
    });

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

    // Both headers render the same notifications. Carry the open panel to
    // the visible header when a resize crosses their layout breakpoint.
    const syncHeader = () => {
        const currentRoot = roots.find((root) =>
            root.querySelector("[data-consultation-notification-panel]")?.hidden === false
        );
        if (!currentRoot || currentRoot.getBoundingClientRect().width) {
            return;
        }
        const nextRoot = roots.find((root) => root.getBoundingClientRect().width);
        if (!nextRoot) {
            return;
        }
        const nextPanel = nextRoot.querySelector("[data-consultation-notification-panel]");
        const nextTrigger = nextRoot.querySelector("[data-consultation-notification-trigger]");
        const activeControl = document.activeElement === document.body ? focusedControl : document.activeElement;
        const focusedIndex = Array.from(currentRoot.querySelectorAll("button, a[href]"))
            .indexOf(activeControl);
        close(currentRoot);
        nextPanel.hidden = false;
        nextTrigger.setAttribute("aria-expanded", "true");
        if (focusedIndex !== -1) {
            const nextControl = nextRoot.querySelectorAll("button, a[href]")[focusedIndex];
            (nextControl || nextTrigger).focus({ preventScroll: true });
        }
    };
    let resizeFrame;
    window.addEventListener("resize", () => {
        cancelAnimationFrame(resizeFrame);
        // Let the dashboard's media-query handler clear sidebar inertness
        // before restoring keyboard focus inside the desktop panel.
        resizeFrame = requestAnimationFrame(syncHeader);
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
