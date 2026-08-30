(() => {
    "use strict";

    const recordSectionSelector = "details[data-record-section]";

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

    const openFragmentSection = () => {
        const fragment = fragmentId();
        if (!fragment) {
            return;
        }
        const directTarget = document.getElementById(fragment);
        const target = directTarget || sectionForAlias(fragment);
        if (!target) {
            return;
        }
        openAncestorDetails(target);
        window.requestAnimationFrame(() => {
            target.scrollIntoView({ block: "start" });
        });
    };

    const initializePatientRecordSections = () => {
        openFragmentSection();
        window.addEventListener("hashchange", openFragmentSection);
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializePatientRecordSections, {
            once: true,
        });
    } else {
        initializePatientRecordSections();
    }
})();
