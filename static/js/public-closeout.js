(() => {
    "use strict";

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const desktopReviewLayout = window.matchMedia("(min-width: 768px)");

    document.querySelectorAll("[data-public-case-video]").forEach((video) => {
        const enforceSilentPlayback = () => {
            video.defaultMuted = true;
            video.muted = true;
            video.volume = 0;
        };
        enforceSilentPlayback();
        video.addEventListener("volumechange", enforceSilentPlayback);
        video.addEventListener("play", enforceSilentPlayback);
    });

    document.querySelectorAll("[data-review-carousel]").forEach((carousel) => {
        const cards = Array.from(carousel.querySelectorAll("[data-review-card]"));
        if (!cards.length) {
            return;
        }

        let groupIndex = 0;
        let timerId = null;
        const pauseReasons = new Set();

        const visibleCount = () => (desktopReviewLayout.matches ? 3 : 1);
        const groupCount = () => Math.max(1, Math.ceil(cards.length / visibleCount()));

        const showGroup = (nextGroup) => {
            groupIndex = (nextGroup + groupCount()) % groupCount();
            const count = visibleCount();
            const start = groupIndex * count;
            cards.forEach((card, index) => {
                const visible = index >= start && index < start + count;
                card.hidden = !visible;
                card.setAttribute("aria-hidden", visible ? "false" : "true");
            });
        };

        const stop = () => {
            if (timerId !== null) {
                window.clearInterval(timerId);
                timerId = null;
            }
        };

        const start = () => {
            stop();
            if (!reducedMotion.matches && pauseReasons.size === 0 && groupCount() > 1) {
                timerId = window.setInterval(() => showGroup(groupIndex + 1), 5500);
            }
        };

        const pause = (reason) => {
            pauseReasons.add(reason);
            stop();
        };

        const resume = (reason) => {
            pauseReasons.delete(reason);
            start();
        };

        carousel.addEventListener("pointerenter", (event) => {
            if (event.pointerType !== "touch") {
                pause("hover");
            }
        });
        carousel.addEventListener("pointerleave", () => resume("hover"));
        carousel.addEventListener("focusin", () => pause("focus"));
        carousel.addEventListener("focusout", (event) => {
            if (!(event.relatedTarget instanceof Node) || !carousel.contains(event.relatedTarget)) {
                resume("focus");
            }
        });
        desktopReviewLayout.addEventListener("change", () => {
            groupIndex = 0;
            showGroup(0);
            start();
        });
        reducedMotion.addEventListener("change", start);
        document.addEventListener("visibilitychange", () => {
            if (document.hidden) {
                pause("visibility");
            } else {
                resume("visibility");
            }
        });

        carousel.classList.add("is-carousel-ready");
        showGroup(0);
        start();
    });
})();
