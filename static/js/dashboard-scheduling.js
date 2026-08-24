(function () {
    "use strict";

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
