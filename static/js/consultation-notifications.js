(() => {
    "use strict";

    const roots = Array.from(document.querySelectorAll("[data-consultation-notifications]"));
    if (!roots.length) {
        return;
    }

    let bookingSeenPromise = null;

    const syncSeenBookings = (sourceRoot) => {
        const form = sourceRoot.querySelector("[data-booking-seen-on-open-form]");
        if (!form || bookingSeenPromise) {
            return;
        }
        const bookingCount = Number(form.dataset.bookingUnseenCount || "0");
        if (!bookingCount) {
            return;
        }

        bookingSeenPromise = fetch(form.action, {
            method: "POST",
            body: new FormData(form),
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error("Could not mark booking notifications as seen.");
                }
                return response.json();
            })
            .then(() => {
                roots.forEach((root) => {
                    const total = Number(root.dataset.notificationTotalCount || "0");
                    const nextTotal = Math.max(0, total - bookingCount);
                    root.dataset.notificationTotalCount = String(nextTotal);

                    const badge = root.querySelector("[data-notification-badge]");
                    const count = root.querySelector("[data-notification-count]");
                    const badgeCopy = root.querySelector("[data-notification-badge-copy]");
                    const badgeText = nextTotal > 99 ? "99+" : String(nextTotal);

                    if (badge) {
                        badge.textContent = badgeText;
                        badge.hidden = nextTotal === 0;
                    }
                    if (count) {
                        const countValue = count.querySelector("[data-notification-count-value]");
                        if (countValue) {
                            countValue.textContent = nextTotal === 0 ? "" : badgeText;
                        }
                        count.hidden = nextTotal === 0;
                    }
                    if (badgeCopy) {
                        const label = root.dataset.notificationCountLabel || "";
                        badgeCopy.textContent = nextTotal === 0 ? "" : `${nextTotal} ${label}`;
                    }

                    root.querySelectorAll("[data-booking-notification-item]").forEach((item) => {
                        item.classList.remove("is-unread");
                        item.querySelector(".consultation-notification-unread-dot")?.remove();
                        item.querySelector("[data-notification-unread-copy]")?.remove();
                    });

                    root.querySelectorAll("[data-booking-seen-on-open-form]").forEach((seenForm) => {
                        seenForm.dataset.bookingUnseenCount = "0";
                    });

                    const markButton = root.querySelector("[data-booking-mark-seen-button]");
                    if (markButton) {
                        markButton.disabled = true;
                    }
                });
            })
            .catch(() => {
                bookingSeenPromise = null;
            });
    };

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
            if (willOpen && root.dataset.staffAttentionBell === "true") {
                syncSeenBookings(root);
            }
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
