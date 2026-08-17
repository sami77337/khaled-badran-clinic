(() => {
    "use strict";

    const menuToggle = document.querySelector("[data-menu-toggle]");
    const drawer = document.querySelector("[data-mobile-drawer]");
    const drawerBackdrop = document.querySelector("[data-menu-close]");
    const mobileBookingCta = document.querySelector("[data-mobile-booking-cta]");

    if (menuToggle && drawer && drawerBackdrop) {
        const closeMenu = ({ restoreFocus = false } = {}) => {
            drawer.hidden = true;
            drawerBackdrop.hidden = true;
            menuToggle.setAttribute("aria-expanded", "false");
            document.body.classList.remove("menu-is-open");
            if (mobileBookingCta) {
                mobileBookingCta.hidden = false;
            }
            if (restoreFocus) {
                menuToggle.focus();
            }
        };

        const openMenu = () => {
            drawer.hidden = false;
            drawerBackdrop.hidden = false;
            menuToggle.setAttribute("aria-expanded", "true");
            document.body.classList.add("menu-is-open");
            if (mobileBookingCta) {
                mobileBookingCta.hidden = true;
            }
            const firstLink = drawer.querySelector("a");
            if (firstLink) {
                firstLink.focus();
            }
        };

        menuToggle.addEventListener("click", () => {
            if (menuToggle.getAttribute("aria-expanded") === "true") {
                closeMenu({ restoreFocus: true });
            } else {
                openMenu();
            }
        });
        drawerBackdrop.addEventListener("click", () => closeMenu({ restoreFocus: true }));
        drawer.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => closeMenu()));
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && menuToggle.getAttribute("aria-expanded") === "true") {
                closeMenu({ restoreFocus: true });
            }
        });
        window.matchMedia("(min-width: 1120px)").addEventListener("change", (event) => {
            if (event.matches) {
                closeMenu();
            }
        });
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const heroCarousel = document.querySelector("[data-hero-carousel]");

    if (heroCarousel) {
        const slides = Array.from(heroCarousel.querySelectorAll("[data-hero-slide]"));
        const dots = Array.from(heroCarousel.querySelectorAll("[data-hero-dot]"));
        let activeIndex = 0;
        let timerId = null;
        let paused = false;

        const showSlide = (nextIndex) => {
            if (!slides.length) {
                return;
            }
            activeIndex = (nextIndex + slides.length) % slides.length;
            slides.forEach((slide, index) => {
                const isActive = index === activeIndex;
                slide.hidden = !isActive;
                slide.classList.toggle("is-active", isActive);
            });
            dots.forEach((dot, index) => {
                const isActive = index === activeIndex;
                dot.classList.toggle("is-active", isActive);
                dot.setAttribute("aria-pressed", isActive ? "true" : "false");
            });
        };

        const stopAutoplay = () => {
            if (timerId !== null) {
                window.clearInterval(timerId);
                timerId = null;
            }
        };

        const startAutoplay = () => {
            stopAutoplay();
            if (!reducedMotion && !paused && slides.length > 1) {
                timerId = window.setInterval(() => showSlide(activeIndex + 1), 4500);
            }
        };

        dots.forEach((dot, index) => {
            dot.addEventListener("click", () => {
                paused = true;
                showSlide(index);
                stopAutoplay();
            });
        });
        heroCarousel.addEventListener("pointerenter", () => {
            paused = true;
            stopAutoplay();
        });
        heroCarousel.addEventListener("pointerleave", () => {
            paused = false;
            startAutoplay();
        });
        heroCarousel.addEventListener("focusin", stopAutoplay);
        heroCarousel.addEventListener("focusout", startAutoplay);
        showSlide(0);
        startAutoplay();
    }

    const caseCarousel = document.querySelector("[data-card-carousel]");
    const caseDotsContainer = document.querySelector("[data-card-dots]");

    if (caseCarousel && caseDotsContainer) {
        const cards = Array.from(caseCarousel.children);
        const dots = Array.from(caseDotsContainer.querySelectorAll("[data-card-dot]"));
        let activeIndex = 0;
        let timerId = null;
        let paused = false;

        const setActiveDot = (index) => {
            activeIndex = Math.max(0, Math.min(index, cards.length - 1));
            dots.forEach((dot, dotIndex) => {
                const isActive = dotIndex === activeIndex;
                dot.classList.toggle("is-active", isActive);
                dot.setAttribute("aria-pressed", isActive ? "true" : "false");
            });
        };

        const scrollToCard = (index, behavior = "smooth") => {
            if (!cards.length) {
                return;
            }
            const nextIndex = (index + cards.length) % cards.length;
            cards[nextIndex].scrollIntoView({
                behavior,
                block: "nearest",
                inline: "start",
            });
            setActiveDot(nextIndex);
        };

        const stopAutoplay = () => {
            if (timerId !== null) {
                window.clearInterval(timerId);
                timerId = null;
            }
        };

        const startAutoplay = () => {
            stopAutoplay();
            if (!reducedMotion && !paused && window.innerWidth < 768 && cards.length > 1) {
                timerId = window.setInterval(() => scrollToCard(activeIndex + 1), 5500);
            }
        };

        dots.forEach((dot, index) => {
            dot.addEventListener("click", () => {
                paused = true;
                stopAutoplay();
                scrollToCard(index);
            });
        });
        caseCarousel.addEventListener("pointerdown", () => {
            paused = true;
            stopAutoplay();
        });
        caseCarousel.addEventListener("scroll", () => {
            const isRtl = window.getComputedStyle(caseCarousel).direction === "rtl";
            const carouselRect = caseCarousel.getBoundingClientRect();
            const carouselStart = isRtl ? carouselRect.right : carouselRect.left;
            let closestIndex = 0;
            let closestDistance = Number.POSITIVE_INFINITY;
            cards.forEach((card, index) => {
                const cardRect = card.getBoundingClientRect();
                const cardStart = isRtl ? cardRect.right : cardRect.left;
                const distance = Math.abs(cardStart - carouselStart);
                if (distance < closestDistance) {
                    closestDistance = distance;
                    closestIndex = index;
                }
            });
            setActiveDot(closestIndex);
        }, { passive: true });
        window.addEventListener("resize", startAutoplay, { passive: true });
        startAutoplay();
    }

    // Service worker registration remains intentionally disabled. Public pages
    // must not establish a cache strategy that could include authenticated or
    // private medical content.
})();
