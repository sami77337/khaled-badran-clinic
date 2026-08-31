(() => {
    "use strict";

    const recordSectionSelector = "details[data-record-section]";
    const restorationKey = "dashboardPatientRecordContext:v1";
    const restorationMaxAgeMilliseconds = 2 * 60 * 1000;

    const fragmentId = () => {
        const rawFragment = window.location.hash.slice(1);
        if (!rawFragment) {
            return "";
        }
        try {
            return decodeURIComponent(rawFragment);
        } catch (error) {
            return rawFragment;
        }
    };

    const sectionForAlias = (fragment) => Array.from(
        document.querySelectorAll(recordSectionSelector),
    ).find((section) => (
        section.dataset.recordSectionAliases || ""
    ).split(/\s+/).includes(fragment));

    const openAncestorDetails = (target) => {
        let current = target;
        while (current instanceof Element) {
            const details = current.matches("details") ? current : current.closest("details");
            if (!details) {
                break;
            }
            details.open = true;
            current = details.parentElement;
        }
    };

    const clearStoredRecordContext = () => {
        try {
            sessionStorage.removeItem(restorationKey);
        } catch (error) {
            // Storage can be unavailable in privacy-restricted browser contexts.
        }
    };

    const openFragmentSection = () => {
        const fragment = fragmentId();
        if (!fragment) {
            return false;
        }
        clearStoredRecordContext();
        const directTarget = document.getElementById(fragment);
        const target = directTarget || sectionForAlias(fragment);
        if (!target) {
            return true;
        }
        openAncestorDetails(target);
        window.requestAnimationFrame(() => {
            target.scrollIntoView({ block: "start" });
        });
        return true;
    };

    const recordIdentity = () => {
        const query = new URLSearchParams(window.location.search);
        query.sort();
        const serializedQuery = query.toString();
        return `${window.location.pathname}${serializedQuery ? `?${serializedQuery}` : ""}`;
    };

    const storeRecordContext = () => {
        const openSectionIds = Array.from(document.querySelectorAll(recordSectionSelector))
            .filter((section) => section.open && section.id)
            .map((section) => section.id);
        try {
            sessionStorage.setItem(restorationKey, JSON.stringify({
                identity: recordIdentity(),
                scrollY: window.scrollY,
                openSectionIds,
                createdAt: Date.now(),
            }));
        } catch (error) {
            // The server action remains usable when sessionStorage is unavailable.
        }
    };

    const restoreRecordContext = () => {
        let state;
        try {
            state = JSON.parse(sessionStorage.getItem(restorationKey) || "null");
        } catch (error) {
            clearStoredRecordContext();
            return;
        }
        if (!state) {
            return;
        }

        const isFresh = Number.isFinite(state.createdAt)
            && Date.now() - state.createdAt <= restorationMaxAgeMilliseconds;
        if (!isFresh || state.identity !== recordIdentity()) {
            clearStoredRecordContext();
            return;
        }

        clearStoredRecordContext();
        (state.openSectionIds || []).forEach((sectionId) => {
            const section = document.getElementById(sectionId);
            if (section && section.matches(recordSectionSelector)) {
                section.open = true;
            }
        });
        const scrollY = Number.isFinite(state.scrollY) ? Math.max(0, state.scrollY) : 0;
        window.requestAnimationFrame(() => {
            window.scrollTo({ top: scrollY, left: 0, behavior: "auto" });
        });
    };

    const initializeContextActions = () => {
        document.addEventListener("submit", (event) => {
            if (event.target.matches("form[data-record-context-action]")) {
                storeRecordContext();
            }
        });
        document.addEventListener("click", (event) => {
            const actionLink = event.target.closest("a[data-record-context-action]");
            if (actionLink) {
                storeRecordContext();
            }
        });
    };

    const initializeMediaPreviewDialog = () => {
        const dialog = document.querySelector("[data-media-preview-dialog]");
        if (!dialog) {
            return;
        }
        const image = dialog.querySelector("[data-media-preview-image]");
        const video = dialog.querySelector("[data-media-preview-video]");
        const closeButton = dialog.querySelector("[data-media-preview-close]");
        let returnFocusTo = null;

        const clearMedia = () => {
            image.hidden = true;
            image.removeAttribute("src");
            video.pause();
            video.hidden = true;
            video.removeAttribute("src");
            video.load();
        };

        const closeDialog = () => {
            if (dialog.open) {
                dialog.close();
            }
        };

        document.querySelectorAll("[data-media-preview-trigger]").forEach((trigger) => {
            trigger.addEventListener("click", () => {
                clearMedia();
                returnFocusTo = trigger;
                if (trigger.dataset.mediaType === "short_video") {
                    video.src = trigger.dataset.previewUrl;
                    video.hidden = false;
                    video.load();
                } else {
                    image.src = trigger.dataset.previewUrl;
                    image.hidden = false;
                }
                dialog.showModal();
                closeButton.focus();
            });
        });
        closeButton.addEventListener("click", closeDialog);
        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) {
                closeDialog();
            }
        });
        dialog.addEventListener("close", () => {
            clearMedia();
            if (returnFocusTo) {
                returnFocusTo.focus();
                returnFocusTo = null;
            }
        });
    };

    const initializePublicCaseDeleteDialog = () => {
        const dialog = document.querySelector("[data-public-case-delete-dialog]");
        if (!dialog) {
            return;
        }
        const form = dialog.querySelector("[data-public-case-delete-form]");
        const closeButton = dialog.querySelector("[data-public-case-delete-close]");
        let returnFocusTo = null;

        const closeDialog = () => {
            if (dialog.open) {
                dialog.close();
            }
        };

        document.querySelectorAll("[data-public-case-delete-trigger]").forEach((trigger) => {
            trigger.addEventListener("click", () => {
                form.action = trigger.dataset.deleteUrl;
                returnFocusTo = trigger;
                dialog.showModal();
                closeButton.focus();
            });
        });
        closeButton.addEventListener("click", closeDialog);
        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) {
                closeDialog();
            }
        });
        dialog.addEventListener("close", () => {
            form.removeAttribute("action");
            if (returnFocusTo) {
                returnFocusTo.focus();
                returnFocusTo = null;
            }
        });
    };

    const initializePatientRecord = () => {
        initializeContextActions();
        initializeMediaPreviewDialog();
        initializePublicCaseDeleteDialog();
        if (!openFragmentSection()) {
            restoreRecordContext();
        }
        window.addEventListener("hashchange", openFragmentSection);
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializePatientRecord, {
            once: true,
        });
    } else {
        initializePatientRecord();
    }
})();
