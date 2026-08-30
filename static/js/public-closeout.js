(() => {
    "use strict";

    const interactiveCaseSelector = "button, a, video, input, select, textarea";
    let publicCloseoutInitialized = false;

    const enforceSilentPlayback = (video) => {
        video.defaultMuted = true;
        video.muted = true;
    };

    const prepareSilentVideo = (video) => {
        enforceSilentPlayback(video);
        video.setAttribute("controlsList", "nodownload");
        if (video.dataset.silentPlaybackReady === "true") {
            return;
        }
        video.dataset.silentPlaybackReady = "true";
        video.addEventListener("volumechange", () => enforceSilentPlayback(video));
        video.addEventListener("play", () => enforceSilentPlayback(video));
    };

    const hydrateCaseVideo = (video) => {
        if (!video.getAttribute("src") && video.dataset.src) {
            video.setAttribute("src", video.dataset.src);
        }
        prepareSilentVideo(video);
    };

    const pauseCaseVideos = (container) => {
        container.querySelectorAll("video").forEach((video) => video.pause());
    };

    const normalizedIndex = (index, total) => (index + total) % total;

    const caseNavigationOffsetForKey = (key) => {
        const isRtl = document.documentElement.dir === "rtl"
            || getComputedStyle(document.body).direction === "rtl";
        if (key === (isRtl ? "ArrowLeft" : "ArrowRight")) {
            return 1;
        }
        if (key === (isRtl ? "ArrowRight" : "ArrowLeft")) {
            return -1;
        }
        return 0;
    };

    const showCaseSlide = (caseState, nextIndex) => {
        pauseCaseVideos(caseState.card);
        caseState.index = normalizedIndex(nextIndex, caseState.slides.length);
        caseState.slides.forEach((slide, index) => {
            const isCurrent = index === caseState.index;
            slide.hidden = !isCurrent;
            slide.setAttribute("aria-hidden", isCurrent ? "false" : "true");
        });

        const currentSlide = caseState.slides[caseState.index];
        const currentVideo = currentSlide.querySelector("video");
        if (currentVideo) {
            hydrateCaseVideo(currentVideo);
        }
        caseState.label.textContent = currentSlide.dataset.slideLabel || "";
        caseState.counter.textContent = `${caseState.index + 1} / ${caseState.slides.length}`;
    };

    const initializeCaseCarousels = () => {
        const lightbox = document.querySelector("[data-case-lightbox]");
        const lightboxTitle = lightbox
            ? lightbox.querySelector("[data-lightbox-title]")
            : null;
        const lightboxLabel = lightbox
            ? lightbox.querySelector("[data-lightbox-label]")
            : null;
        const lightboxCounter = lightbox
            ? lightbox.querySelector("[data-lightbox-counter]")
            : null;
        const lightboxMedia = lightbox
            ? lightbox.querySelector("[data-lightbox-media]")
            : null;
        const lightboxPrevious = lightbox
            ? lightbox.querySelector("[data-lightbox-prev]")
            : null;
        const lightboxNext = lightbox
            ? lightbox.querySelector("[data-lightbox-next]")
            : null;
        const lightboxClose = lightbox
            ? lightbox.querySelector("[data-lightbox-close]")
            : null;
        const nativeDialogAvailable = Boolean(
            lightbox
            && lightboxTitle
            && lightboxLabel
            && lightboxCounter
            && lightboxMedia
            && lightboxPrevious
            && lightboxNext
            && lightboxClose
            && typeof lightbox.showModal === "function"
            && typeof lightbox.close === "function"
        );
        let activeLightboxState = null;

        const clearLightboxMedia = () => {
            if (!lightboxMedia) {
                return;
            }
            pauseCaseVideos(lightboxMedia);
            lightboxMedia.replaceChildren();
        };

        const renderLightboxSlide = () => {
            if (!activeLightboxState || !nativeDialogAvailable) {
                return;
            }
            clearLightboxMedia();
            const { caseState } = activeLightboxState;
            activeLightboxState.index = normalizedIndex(
                activeLightboxState.index,
                caseState.slides.length,
            );
            const slide = caseState.slides[activeLightboxState.index];
            const label = slide.dataset.slideLabel || "";
            if (slide.dataset.slideKind === "note") {
                const noteSource = slide.querySelector("[data-case-note-text]");
                const noteCard = document.createElement("div");
                const noteHeading = document.createElement("h3");
                const noteText = document.createElement("p");
                noteCard.className = "public-case-lightbox-note";
                noteHeading.textContent = label;
                noteText.textContent = noteSource ? noteSource.textContent : "";
                noteCard.append(noteHeading, noteText);
                lightboxMedia.append(noteCard);
            } else {
                const mediaUrl = slide.dataset.mediaUrl || "";
                let media;
                if (slide.dataset.mediaType === "short_video") {
                    media = document.createElement("video");
                    media.src = mediaUrl;
                    const cardVideo = slide.querySelector("video");
                    const posterUrl = cardVideo ? cardVideo.getAttribute("poster") : "";
                    if (posterUrl) {
                        media.poster = posterUrl;
                    }
                    media.controls = true;
                    media.playsInline = true;
                    media.preload = "metadata";
                    media.setAttribute("aria-label", label);
                    prepareSilentVideo(media);
                } else {
                    media = document.createElement("img");
                    media.src = mediaUrl;
                    media.alt = label;
                }
                lightboxMedia.append(media);
            }
            lightboxTitle.textContent = caseState.title;
            lightboxLabel.textContent = label;
            lightboxCounter.textContent = `${activeLightboxState.index + 1} / ${caseState.slides.length}`;
            const hideNavigation = caseState.slides.length <= 1;
            lightboxPrevious.hidden = hideNavigation;
            lightboxNext.hidden = hideNavigation;
        };

        const resetLightbox = () => {
            const opener = activeLightboxState ? activeLightboxState.opener : null;
            clearLightboxMedia();
            activeLightboxState = null;
            if (opener instanceof HTMLElement && opener.isConnected) {
                opener.focus({ preventScroll: true });
            }
        };

        const closeCaseLightbox = () => {
            if (nativeDialogAvailable && lightbox.open) {
                lightbox.close();
            } else {
                resetLightbox();
            }
        };

        const openCaseLightbox = (caseState, index, opener) => {
            if (!nativeDialogAvailable) {
                if (
                    caseState.detailUrl
                    && window.location
                    && typeof window.location.assign === "function"
                ) {
                    window.location.assign(caseState.detailUrl);
                }
                return;
            }
            pauseCaseVideos(caseState.card);
            activeLightboxState = {
                caseState,
                index,
                opener,
            };
            renderLightboxSlide();
            if (!lightbox.open) {
                lightbox.showModal();
            }
            lightboxClose.focus({ preventScroll: true });
        };

        const moveLightbox = (offset) => {
            if (!activeLightboxState) {
                return;
            }
            activeLightboxState.index += offset;
            renderLightboxSlide();
        };

        if (nativeDialogAvailable) {
            lightboxPrevious.addEventListener("click", (event) => {
                event.preventDefault();
                moveLightbox(-1);
            });
            lightboxNext.addEventListener("click", (event) => {
                event.preventDefault();
                moveLightbox(1);
            });
            lightboxClose.addEventListener("click", (event) => {
                event.preventDefault();
                closeCaseLightbox();
            });
            lightbox.addEventListener("click", (event) => {
                if (event.target === lightbox) {
                    closeCaseLightbox();
                }
            });
            lightbox.addEventListener("cancel", (event) => {
                event.preventDefault();
                closeCaseLightbox();
            });
            lightbox.addEventListener("close", resetLightbox);
            lightbox.addEventListener("keydown", (event) => {
                if (event.key === "Escape") {
                    event.preventDefault();
                    closeCaseLightbox();
                    return;
                }
                if (!activeLightboxState || activeLightboxState.caseState.slides.length <= 1) {
                    return;
                }
                const offset = caseNavigationOffsetForKey(event.key);
                if (offset !== 0) {
                    event.preventDefault();
                    moveLightbox(offset);
                }
            });
        }

        document.querySelectorAll("[data-case-album]").forEach((card) => {
            const carousel = card.querySelector("[data-case-carousel]");
            const slides = Array.from(card.querySelectorAll("[data-case-slide]"));
            const label = card.querySelector("[data-case-current-label]");
            const counter = card.querySelector("[data-case-counter]");
            const titleElement = card.querySelector("h2");
            const title = titleElement ? titleElement.textContent.trim() : "";
            if (
                !carousel
                || carousel.dataset.caseCarouselReady === "true"
                || !slides.length
                || !label
                || !counter
            ) {
                return;
            }

            const caseState = {
                card,
                slides,
                label,
                counter,
                title,
                detailUrl: card.dataset.caseDetailUrl || "",
                index: 0,
            };
            const previousButton = card.querySelector("[data-case-prev]");
            const nextButton = card.querySelector("[data-case-next]");

            if (previousButton) {
                previousButton.addEventListener("click", (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    showCaseSlide(caseState, caseState.index - 1);
                });
            }
            if (nextButton) {
                nextButton.addEventListener("click", (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    showCaseSlide(caseState, caseState.index + 1);
                });
            }
            card.querySelectorAll("[data-case-expand]").forEach((button) => {
                button.addEventListener("click", (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    openCaseLightbox(caseState, caseState.index, button);
                });
            });
            card.addEventListener("click", (event) => {
                const target = event.target;
                if (
                    !(target instanceof Element)
                    || target.closest(interactiveCaseSelector)
                ) {
                    return;
                }
                openCaseLightbox(caseState, caseState.index, card);
            });
            card.addEventListener("keydown", (event) => {
                if (event.target !== card) {
                    return;
                }
                if (["Enter", " "].includes(event.key)) {
                    event.preventDefault();
                    openCaseLightbox(caseState, caseState.index, card);
                    return;
                }
                const offset = caseNavigationOffsetForKey(event.key);
                if (offset !== 0 && caseState.slides.length > 1) {
                    event.preventDefault();
                    showCaseSlide(caseState, caseState.index + offset);
                }
            });

            showCaseSlide(caseState, 0);
            carousel.dataset.caseCarouselReady = "true";
        });
    };

    const createMediaQuery = (query) => {
        if (typeof window.matchMedia === "function") {
            return window.matchMedia(query);
        }
        return { matches: false };
    };

    const addMediaQueryChangeListener = (mediaQuery, callback) => {
        if (typeof mediaQuery.addEventListener === "function") {
            mediaQuery.addEventListener("change", callback);
        } else if (typeof mediaQuery.addListener === "function") {
            mediaQuery.addListener(callback);
        }
    };

    const initializeReviewCarousels = () => {
        const reducedMotion = createMediaQuery("(prefers-reduced-motion: reduce)");
        const desktopReviewLayout = createMediaQuery("(min-width: 768px)");

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
            addMediaQueryChangeListener(desktopReviewLayout, () => {
                groupIndex = 0;
                showGroup(0);
                start();
            });
            addMediaQueryChangeListener(reducedMotion, start);
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
    };

    const initializePublicCloseout = () => {
        if (publicCloseoutInitialized) {
            return;
        }
        publicCloseoutInitialized = true;
        initializeCaseCarousels();
        initializeReviewCarousels();
        document.querySelectorAll("[data-public-case-video]").forEach(prepareSilentVideo);
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializePublicCloseout, { once: true });
    } else {
        initializePublicCloseout();
    }
})();
