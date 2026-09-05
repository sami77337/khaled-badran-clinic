(() => {
    "use strict";

    const contactTriggers = Array.from(
        document.querySelectorAll("[data-patient-contact-trigger]")
    );
    if (!contactTriggers.length) {
        return;
    }

    let openTrigger = null;

    const controlledMenu = (trigger) => {
        const menuId = trigger.getAttribute("aria-controls");
        return menuId ? document.getElementById(menuId) : null;
    };

    const closeMenu = ({ restoreFocus = false } = {}) => {
        if (!openTrigger) {
            return;
        }
        const trigger = openTrigger;
        const menu = controlledMenu(trigger);
        trigger.setAttribute("aria-expanded", "false");
        if (menu) {
            menu.hidden = true;
        }
        openTrigger = null;
        if (restoreFocus) {
            trigger.focus({ preventScroll: true });
        }
    };

    const openMenu = (trigger) => {
        const menu = controlledMenu(trigger);
        if (!menu) {
            return;
        }
        if (openTrigger && openTrigger !== trigger) {
            closeMenu();
        }
        menu.querySelectorAll(".patient-contact-feedback").forEach((feedback) => {
            feedback.textContent = "";
        });
        menu.classList.remove("opens-upward");
        menu.hidden = false;
        const menuBounds = menu.getBoundingClientRect();
        const triggerBounds = trigger.getBoundingClientRect();
        if (
            menuBounds.bottom > window.innerHeight - 8 &&
            triggerBounds.top > menuBounds.height + 8
        ) {
            menu.classList.add("opens-upward");
        }
        trigger.setAttribute("aria-expanded", "true");
        openTrigger = trigger;
    };

    contactTriggers.forEach((trigger) => {
        trigger.addEventListener("click", () => {
            if (openTrigger === trigger) {
                closeMenu();
            } else {
                openMenu(trigger);
            }
        });
    });

    document.addEventListener("click", (event) => {
        if (!openTrigger || !(event.target instanceof Node)) {
            return;
        }
        const contact = openTrigger.closest(".patient-contact");
        if (!contact || !contact.contains(event.target)) {
            closeMenu();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !openTrigger) {
            return;
        }
        event.preventDefault();
        closeMenu({ restoreFocus: true });
    });

    const fallbackCopy = (number) => {
        if (typeof document.execCommand !== "function") {
            return false;
        }
        const textarea = document.createElement("textarea");
        textarea.value = number;
        textarea.setAttribute("readonly", "");
        textarea.setAttribute("aria-hidden", "true");
        textarea.style.position = "fixed";
        textarea.style.top = "0";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        textarea.setSelectionRange(0, textarea.value.length);
        try {
            return document.execCommand("copy");
        } catch (_error) {
            return false;
        } finally {
            textarea.remove();
        }
    };

    const copyNumber = async (number) => {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
            try {
                await navigator.clipboard.writeText(number);
                return true;
            } catch (_error) {
                // Fall through to the legacy browser copy path.
            }
        }
        return fallbackCopy(number);
    };

    document.querySelectorAll("[data-copy-number]").forEach((copyButton) => {
        copyButton.addEventListener("click", async () => {
            const number = copyButton.dataset.copyNumber || "";
            const feedbackId = copyButton.getAttribute("aria-describedby");
            const feedback = feedbackId ? document.getElementById(feedbackId) : null;
            if (feedback) {
                feedback.textContent = "";
            }
            const copied = number ? await copyNumber(number) : false;
            if (feedback) {
                feedback.textContent = copied
                    ? copyButton.dataset.copySuccess || ""
                    : copyButton.dataset.copyFailure || "";
            }
        });
    });
})();
