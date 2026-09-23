(function () {
    "use strict";

    var customizationToggle = document.querySelector("[data-scheduling-customization-toggle]");
    if (customizationToggle) {
        var customizationDetails = document.getElementById(
            customizationToggle.getAttribute("aria-controls")
        );
        if (customizationDetails) {
            customizationToggle.addEventListener("click", function () {
                var shouldExpand = customizationToggle.getAttribute("aria-expanded") !== "true";
                customizationToggle.setAttribute("aria-expanded", shouldExpand ? "true" : "false");
                customizationDetails.hidden = !shouldExpand;
                if (shouldExpand) {
                    var customizationTarget =
                        document.getElementById("customize-day-form") ||
                        customizationDetails.querySelector(".scheduling-conflict-warning") ||
                        customizationDetails;
                    var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
                    window.requestAnimationFrame(function () {
                        customizationTarget.scrollIntoView({
                            behavior: reducedMotion ? "auto" : "smooth",
                            block: "start",
                        });
                    });
                }
            });
        }
    }

    var schedulingRoot = document.querySelector("[data-scheduling-default-view]");
    if (!schedulingRoot || !window.matchMedia("(max-width: 35rem)").matches) {
        return;
    }

    var currentUrl = new URL(window.location.href);
    if (currentUrl.searchParams.has("view")) {
        return;
    }

    currentUrl.searchParams.set("view", "day");
    window.location.replace(currentUrl.toString());
}());
