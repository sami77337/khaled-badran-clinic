(() => {
    "use strict";

    const menuButtons = Array.from(document.querySelectorAll("[data-dashboard-menu]"));
    const sidebar = document.querySelector("[data-dashboard-sidebar]");
    const closeButton = document.querySelector("[data-dashboard-close]");
    const overlay = document.querySelector("[data-dashboard-overlay]");

    if (!menuButtons.length || !sidebar || !closeButton || !overlay) {
        return;
    }

    const mobileViewport = window.matchMedia("(max-width: 63.999rem)");
    const focusableSelector = [
        "a[href]",
        "button:not([disabled])",
        "input:not([disabled])",
        "select:not([disabled])",
        "textarea:not([disabled])",
        "[tabindex]:not([tabindex='-1'])",
    ].join(",");
    let drawerOpen = false;
    let returnFocus = null;

    const setTriggerState = (expanded) => {
        menuButtons.forEach((button) => {
            button.setAttribute("aria-expanded", String(expanded));
        });
    };

    const updateSidebarMode = () => {
        if (mobileViewport.matches) {
            sidebar.setAttribute("role", "dialog");
            sidebar.setAttribute("aria-modal", "true");
            sidebar.setAttribute("aria-hidden", String(!drawerOpen));
            sidebar.inert = !drawerOpen;
            return;
        }
        sidebar.removeAttribute("role");
        sidebar.removeAttribute("aria-modal");
        sidebar.removeAttribute("aria-hidden");
        sidebar.inert = false;
    };

    const closeDrawer = ({ restoreFocus = true } = {}) => {
        if (!drawerOpen && mobileViewport.matches) {
            updateSidebarMode();
            return;
        }
        drawerOpen = false;
        sidebar.classList.remove("is-open");
        document.body.classList.remove("dashboard-drawer-open");
        setTriggerState(false);
        overlay.hidden = true;
        updateSidebarMode();
        if (restoreFocus && returnFocus instanceof HTMLElement) {
            returnFocus.focus({ preventScroll: true });
        }
        returnFocus = null;
    };

    const openDrawer = (trigger) => {
        if (!mobileViewport.matches) {
            return;
        }
        returnFocus = trigger;
        drawerOpen = true;
        sidebar.classList.add("is-open");
        document.body.classList.add("dashboard-drawer-open");
        setTriggerState(true);
        overlay.hidden = false;
        updateSidebarMode();
        closeButton.focus({ preventScroll: true });
    };

    menuButtons.forEach((menuButton) => {
        menuButton.addEventListener("click", () => {
            if (drawerOpen) {
                closeDrawer();
            } else {
                openDrawer(menuButton);
            }
        });
    });
    closeButton.addEventListener("click", () => closeDrawer());
    overlay.addEventListener("click", () => closeDrawer());

    sidebar.querySelectorAll("a[href]").forEach((link) => {
        link.addEventListener("click", () => closeDrawer({ restoreFocus: false }));
    });
    sidebar.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", () => closeDrawer({ restoreFocus: false }));
    });

    document.addEventListener("keydown", (event) => {
        if (!drawerOpen || !mobileViewport.matches) {
            return;
        }
        if (event.key === "Escape") {
            event.preventDefault();
            closeDrawer();
            return;
        }
        if (event.key !== "Tab") {
            return;
        }
        const focusable = Array.from(sidebar.querySelectorAll(focusableSelector)).filter(
            (element) => element instanceof HTMLElement && element.offsetParent !== null
        );
        if (!focusable.length) {
            event.preventDefault();
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus({ preventScroll: true });
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus({ preventScroll: true });
        }
    });

    const handleViewportChange = () => {
        if (!mobileViewport.matches) {
            closeDrawer({ restoreFocus: false });
        } else {
            updateSidebarMode();
        }
    };

    if (typeof mobileViewport.addEventListener === "function") {
        mobileViewport.addEventListener("change", handleViewportChange);
    } else {
        mobileViewport.addListener(handleViewportChange);
    }
    updateSidebarMode();
})();
