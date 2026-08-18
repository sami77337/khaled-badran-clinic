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
        const desktopCaseLayout = window.matchMedia("(min-width: 1024px)");
        let activeIndex = 0;
        let timerId = null;
        let paused = false;
        let desktopStartIndex = null;
        const pauseReasons = new Set();

        const setActiveDot = (index) => {
            activeIndex = Math.max(0, Math.min(index, cards.length - 1));
            cards.forEach((card, cardIndex) => {
                const isActive = cardIndex === activeIndex;
                card.classList.toggle("is-active", isActive);
                if (isActive) {
                    card.setAttribute("aria-current", "true");
                } else {
                    card.removeAttribute("aria-current");
                }
            });
            dots.forEach((dot, dotIndex) => {
                const isActive = dotIndex === activeIndex;
                dot.classList.toggle("is-active", isActive);
                dot.setAttribute("aria-pressed", isActive ? "true" : "false");
            });
        };

        const restoreOriginalCardOrder = () => {
            if (desktopStartIndex === null) {
                return;
            }
            cards.forEach((card) => caseCarousel.append(card));
            desktopStartIndex = null;
        };

        const rotateDesktopCards = (startIndex) => {
            if (desktopStartIndex === startIndex) {
                return;
            }
            const orderedCards = cards.slice(startIndex).concat(cards.slice(0, startIndex));
            orderedCards.forEach((card) => caseCarousel.append(card));
            desktopStartIndex = startIndex;
        };

        const scrollToCard = (index, behavior = "smooth") => {
            if (!cards.length) {
                return;
            }
            const nextIndex = (index + cards.length) % cards.length;
            const effectiveBehavior = reducedMotion ? "auto" : behavior;
            setActiveDot(nextIndex);
            if (desktopCaseLayout.matches) {
                rotateDesktopCards(nextIndex);
            } else {
                restoreOriginalCardOrder();
                cards[nextIndex].scrollIntoView({
                    behavior: effectiveBehavior,
                    block: "nearest",
                    inline: "start",
                });
            }
        };

        const stopAutoplay = () => {
            if (timerId !== null) {
                window.clearInterval(timerId);
                timerId = null;
            }
        };

        const startAutoplay = () => {
            stopAutoplay();
            if (!reducedMotion && !paused && cards.length > 1) {
                timerId = window.setInterval(() => scrollToCard(activeIndex + 1), 5500);
            }
        };

        const pauseAutoplay = (reason) => {
            pauseReasons.add(reason);
            paused = true;
            stopAutoplay();
        };

        const resumeAutoplay = (reason) => {
            pauseReasons.delete(reason);
            paused = pauseReasons.size > 0;
            startAutoplay();
        };

        const focusRemainsInCaseControls = (nextTarget) => (
            nextTarget instanceof Node
            && (caseCarousel.contains(nextTarget) || caseDotsContainer.contains(nextTarget))
        );

        dots.forEach((dot, index) => {
            dot.addEventListener("click", () => {
                stopAutoplay();
                scrollToCard(index);
                startAutoplay();
            });
        });

        cards.forEach((card, index) => {
            card.addEventListener("pointerenter", () => setActiveDot(index));
            card.addEventListener("focusin", () => setActiveDot(index));
        });

        caseCarousel.addEventListener("pointerenter", (event) => {
            if (event.pointerType !== "touch") {
                pauseAutoplay("hover");
            }
        });
        caseCarousel.addEventListener("pointerleave", () => resumeAutoplay("hover"));
        caseCarousel.addEventListener("pointerdown", () => pauseAutoplay("pointer"));
        caseCarousel.addEventListener("pointerup", () => resumeAutoplay("pointer"));
        caseCarousel.addEventListener("pointercancel", () => resumeAutoplay("pointer"));
        caseCarousel.addEventListener("focusin", () => pauseAutoplay("focus"));
        caseCarousel.addEventListener("focusout", (event) => {
            if (!focusRemainsInCaseControls(event.relatedTarget)) {
                resumeAutoplay("focus");
            }
        });
        caseDotsContainer.addEventListener("pointerenter", (event) => {
            if (event.pointerType !== "touch") {
                pauseAutoplay("hover");
            }
        });
        caseDotsContainer.addEventListener("pointerleave", () => resumeAutoplay("hover"));
        caseDotsContainer.addEventListener("focusin", () => pauseAutoplay("focus"));
        caseDotsContainer.addEventListener("focusout", (event) => {
            if (!focusRemainsInCaseControls(event.relatedTarget)) {
                resumeAutoplay("focus");
            }
        });
        caseCarousel.addEventListener("scroll", () => {
            if (desktopCaseLayout.matches) {
                return;
            }
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
        window.addEventListener("resize", () => {
            if (desktopCaseLayout.matches) {
                rotateDesktopCards(activeIndex);
            } else {
                restoreOriginalCardOrder();
            }
            startAutoplay();
        }, { passive: true });
        setActiveDot(0);
        if (desktopCaseLayout.matches) {
            rotateDesktopCards(0);
        }
        startAutoplay();
    }

    const clinicGalleries = document.querySelectorAll("[data-clinic-gallery]");

    clinicGalleries.forEach((gallery) => {
        const viewport = gallery.querySelector("[data-gallery-viewport]");
        const slides = Array.from(gallery.querySelectorAll("[data-gallery-slide]"));
        const dots = Array.from(gallery.querySelectorAll("[data-gallery-dot]"));
        const previousButton = gallery.querySelector("[data-gallery-previous]");
        const nextButton = gallery.querySelector("[data-gallery-next]");
        const controls = gallery.querySelector("[data-gallery-controls]");
        const currentPosition = gallery.querySelector("[data-gallery-current]");

        if (!viewport || !slides.length) {
            return;
        }

        let activeIndex = 0;
        let timerId = null;
        let manualResumeId = null;
        let scrollFrameId = null;
        const pauseReasons = new Set();

        if (controls) {
            controls.hidden = slides.length <= 1;
        }

        const setActiveSlide = (index) => {
            activeIndex = (index + slides.length) % slides.length;
            slides.forEach((slide, slideIndex) => {
                const isActive = slideIndex === activeIndex;
                slide.classList.toggle("is-active", isActive);
                if (isActive) {
                    slide.setAttribute("aria-current", "true");
                } else {
                    slide.removeAttribute("aria-current");
                }
            });
            dots.forEach((dot, dotIndex) => {
                const isActive = dotIndex === activeIndex;
                dot.classList.toggle("is-active", isActive);
                dot.setAttribute("aria-pressed", isActive ? "true" : "false");
            });
            if (currentPosition) {
                currentPosition.textContent = String(activeIndex + 1);
            }
        };

        const scrollToSlide = (index, behavior = "smooth") => {
            const nextIndex = (index + slides.length) % slides.length;
            const effectiveBehavior = reducedMotion ? "auto" : behavior;
            setActiveSlide(nextIndex);
            slides[nextIndex].scrollIntoView({
                behavior: effectiveBehavior,
                block: "nearest",
                inline: "start",
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
            if (!reducedMotion && pauseReasons.size === 0 && slides.length > 1) {
                timerId = window.setInterval(() => scrollToSlide(activeIndex + 1), 6000);
            }
        };

        const pauseAutoplay = (reason) => {
            pauseReasons.add(reason);
            stopAutoplay();
        };

        const resumeAutoplay = (reason) => {
            pauseReasons.delete(reason);
            startAutoplay();
        };

        const scheduleManualResume = () => {
            if (manualResumeId !== null) {
                window.clearTimeout(manualResumeId);
            }
            manualResumeId = window.setTimeout(() => {
                manualResumeId = null;
                resumeAutoplay("manual");
            }, 7000);
        };

        const manuallySelectSlide = (index) => {
            pauseAutoplay("manual");
            scrollToSlide(index);
            scheduleManualResume();
        };

        const focusRemainsInGallery = (nextTarget) => (
            nextTarget instanceof Node && gallery.contains(nextTarget)
        );

        dots.forEach((dot, index) => {
            dot.addEventListener("click", () => manuallySelectSlide(index));
        });
        if (previousButton) {
            previousButton.addEventListener("click", () => manuallySelectSlide(activeIndex - 1));
        }
        if (nextButton) {
            nextButton.addEventListener("click", () => manuallySelectSlide(activeIndex + 1));
        }

        gallery.addEventListener("pointerenter", (event) => {
            if (event.pointerType !== "touch") {
                pauseAutoplay("hover");
            }
        });
        gallery.addEventListener("pointerleave", () => resumeAutoplay("hover"));
        gallery.addEventListener("focusin", () => pauseAutoplay("focus"));
        gallery.addEventListener("focusout", (event) => {
            if (!focusRemainsInGallery(event.relatedTarget)) {
                resumeAutoplay("focus");
            }
        });
        viewport.addEventListener("pointerdown", () => pauseAutoplay("pointer"));
        viewport.addEventListener("pointerup", () => resumeAutoplay("pointer"));
        viewport.addEventListener("pointercancel", () => resumeAutoplay("pointer"));
        viewport.addEventListener("wheel", () => {
            pauseAutoplay("manual");
            scheduleManualResume();
        }, { passive: true });
        viewport.addEventListener("keydown", (event) => {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
                return;
            }
            event.preventDefault();
            const isRtl = window.getComputedStyle(viewport).direction === "rtl";
            const direction = event.key === "ArrowRight"
                ? (isRtl ? -1 : 1)
                : (isRtl ? 1 : -1);
            manuallySelectSlide(activeIndex + direction);
        });
        viewport.addEventListener("scroll", () => {
            if (scrollFrameId !== null) {
                window.cancelAnimationFrame(scrollFrameId);
            }
            scrollFrameId = window.requestAnimationFrame(() => {
                scrollFrameId = null;
                const isRtl = window.getComputedStyle(viewport).direction === "rtl";
                const viewportRect = viewport.getBoundingClientRect();
                const viewportStart = isRtl ? viewportRect.right : viewportRect.left;
                let closestIndex = 0;
                let closestDistance = Number.POSITIVE_INFINITY;
                slides.forEach((slide, index) => {
                    const slideRect = slide.getBoundingClientRect();
                    const slideStart = isRtl ? slideRect.right : slideRect.left;
                    const distance = Math.abs(slideStart - viewportStart);
                    if (distance < closestDistance) {
                        closestDistance = distance;
                        closestIndex = index;
                    }
                });
                setActiveSlide(closestIndex);
            });
        }, { passive: true });
        document.addEventListener("visibilitychange", () => {
            if (document.hidden) {
                pauseAutoplay("visibility");
            } else {
                resumeAutoplay("visibility");
            }
        });

        setActiveSlide(0);
        if (document.hidden) {
            pauseReasons.add("visibility");
        }
        startAutoplay();
    });

    // Service worker registration remains intentionally disabled. Public pages
    // must not establish a cache strategy that could include authenticated or
    // private medical content.
})();
