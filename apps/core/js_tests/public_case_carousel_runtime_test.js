"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const publicCloseoutScriptPath = process.argv[2];

if (!publicCloseoutScriptPath) {
    throw new Error("Expected the public-closeout.js path as the first argument.");
}

const publicCloseoutScript = fs.readFileSync(publicCloseoutScriptPath, "utf8");

class FakeEventTarget {
    constructor() {
        this.listeners = new Map();
    }

    addEventListener(type, callback) {
        const callbacks = this.listeners.get(type) || [];
        callbacks.push(callback);
        this.listeners.set(type, callbacks);
    }

    dispatch(type, properties = {}) {
        const event = {
            defaultPrevented: false,
            key: "",
            relatedTarget: null,
            stopPropagation() {
                this.propagationStopped = true;
            },
            preventDefault() {
                this.defaultPrevented = true;
            },
            target: this,
            ...properties,
            type,
        };
        (this.listeners.get(type) || []).forEach((callback) => callback(event));
        return event;
    }
}

class FakeClassList {
    constructor() {
        this.values = new Set();
    }

    add(value) {
        this.values.add(value);
    }
}

const dataProperty = (selector) => selector
    .slice(6, -1)
    .replace(/-([a-z])/g, (_, character) => character.toUpperCase());

class FakeElement extends FakeEventTarget {
    constructor(tagName, name = tagName.toLowerCase()) {
        super();
        this.attributes = new Map();
        this.children = [];
        this.classList = new FakeClassList();
        this.dataset = {};
        this.focused = false;
        this.hidden = false;
        this.isConnected = true;
        this.name = name;
        this.parentElement = null;
        this.pauseCount = 0;
        this.tagName = tagName.toUpperCase();
        this.textContent = "";
    }

    append(...children) {
        children.forEach((child) => {
            child.parentElement = this;
            this.children.push(child);
        });
    }

    closest(selector) {
        const tagNames = selector.split(",").map((item) => item.trim().toUpperCase());
        let current = this;
        while (current) {
            if (tagNames.includes(current.tagName)) {
                return current;
            }
            current = current.parentElement;
        }
        return null;
    }

    contains(target) {
        return target === this || this.children.some((child) => child.contains(target));
    }

    focus() {
        this.focused = true;
    }

    getAttribute(name) {
        return this.attributes.has(name) ? this.attributes.get(name) : null;
    }

    matches(selector) {
        if (selector.startsWith("[data-") && selector.endsWith("]")) {
            return Object.hasOwn(this.dataset, dataProperty(selector));
        }
        return this.tagName === selector.toUpperCase();
    }

    pause() {
        this.pauseCount += 1;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }

    querySelectorAll(selector) {
        const matches = [];
        const visit = (element) => {
            element.children.forEach((child) => {
                if (child.matches(selector)) {
                    matches.push(child);
                }
                visit(child);
            });
        };
        visit(this);
        return matches;
    }

    replaceChildren(...children) {
        this.children.forEach((child) => {
            child.parentElement = null;
        });
        this.children = [];
        this.append(...children);
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
    }
}

const makeButton = (name, datasetKey) => {
    const button = new FakeElement("button", name);
    button.dataset[datasetKey] = "";
    return button;
};

const makeSlide = ({ label, mediaType, mediaUrl, posterUrl = "" }, index) => {
    const slide = new FakeElement("figure", `slide-${index + 1}`);
    slide.dataset.caseSlide = "";
    slide.dataset.mediaType = mediaType;
    slide.dataset.mediaUrl = mediaUrl;
    slide.dataset.slideLabel = label;

    const media = new FakeElement(mediaType === "short_video" ? "video" : "img", `media-${index + 1}`);
    media.dataset.caseSlideMedia = "";
    if (mediaType === "short_video") {
        media.dataset.publicCaseVideo = "";
        media.dataset.src = mediaUrl;
        if (posterUrl) {
            media.setAttribute("poster", posterUrl);
        }
    }
    slide.append(media);

    const expand = makeButton(`expand-${index + 1}`, "caseExpand");
    slide.append(expand);
    return { expand, media, slide };
};

const buildRuntime = (direction = "ltr") => {
    const slideParts = [
        makeSlide({ label: "Before 1 of 1", mediaType: "image", mediaUrl: "/before" }, 0),
        makeSlide({
            label: "Video 1 of 1",
            mediaType: "short_video",
            mediaUrl: "/video",
            posterUrl: "/video-cover",
        }, 1),
        makeSlide({ label: "After 1 of 1", mediaType: "image", mediaUrl: "/after" }, 2),
    ];
    const slides = slideParts.map((part) => part.slide);
    const expandButtons = slideParts.map((part) => part.expand);
    const cardVideo = slideParts[1].media;

    const previousButton = makeButton("card-previous", "casePrev");
    const nextButton = makeButton("card-next", "caseNext");
    const currentLabel = new FakeElement("span", "card-label");
    currentLabel.dataset.caseCurrentLabel = "";
    const currentCounter = new FakeElement("span", "card-counter");
    currentCounter.dataset.caseCounter = "";
    const title = new FakeElement("h2", "card-title");
    title.textContent = "Safe public case title";
    const card = new FakeElement("article", "case-card");
    card.dataset.caseAlbum = "";
    slides.forEach((slide) => card.append(slide));
    card.append(previousButton, nextButton, currentLabel, currentCounter, title);

    const lightboxTitle = new FakeElement("h2", "lightbox-title");
    lightboxTitle.dataset.lightboxTitle = "";
    const lightboxLabel = new FakeElement("span", "lightbox-label");
    lightboxLabel.dataset.lightboxLabel = "";
    const lightboxCounter = new FakeElement("span", "lightbox-counter");
    lightboxCounter.dataset.lightboxCounter = "";
    const lightboxMedia = new FakeElement("div", "lightbox-media");
    lightboxMedia.dataset.lightboxMedia = "";
    const lightboxPrevious = makeButton("lightbox-previous", "lightboxPrev");
    const lightboxNext = makeButton("lightbox-next", "lightboxNext");
    const lightboxClose = makeButton("lightbox-close", "lightboxClose");
    const lightbox = new FakeElement("dialog", "lightbox");
    lightbox.dataset.caseLightbox = "";
    lightbox.open = false;
    lightbox.append(
        lightboxTitle,
        lightboxLabel,
        lightboxCounter,
        lightboxMedia,
        lightboxPrevious,
        lightboxNext,
        lightboxClose,
    );
    lightbox.showModal = () => {
        lightbox.open = true;
    };
    lightbox.close = () => {
        lightbox.open = false;
        lightbox.dispatch("close", { target: lightbox });
    };

    const document = new FakeEventTarget();
    document.body = new FakeElement("body", "body");
    document.documentElement = { dir: direction };
    document.hidden = false;
    document.createElement = (tagName) => new FakeElement(tagName, `created-${tagName}`);
    document.querySelector = (selector) => (
        selector === "[data-case-lightbox]" ? lightbox : null
    );
    document.querySelectorAll = (selector) => ({
        "[data-case-album]": [card],
        "[data-public-case-video]": [cardVideo],
        "[data-review-carousel]": [],
    })[selector] || [];

    const window = new FakeEventTarget();
    window.clearInterval = () => {};
    window.matchMedia = () => {
        const mediaQuery = new FakeEventTarget();
        mediaQuery.matches = false;
        return mediaQuery;
    };
    window.setInterval = () => 1;

    const context = vm.createContext({
        Array,
        document,
        Element: FakeElement,
        getComputedStyle: () => ({ direction }),
        HTMLElement: FakeElement,
        Node: FakeElement,
        Set,
        window,
    });
    vm.runInContext(publicCloseoutScript, context, { filename: publicCloseoutScriptPath });

    return {
        card,
        cardVideo,
        currentCounter,
        currentLabel,
        document,
        expandButtons,
        lightbox,
        lightboxClose,
        lightboxCounter,
        lightboxLabel,
        lightboxMedia,
        lightboxNext,
        nextButton,
        previousButton,
        slideParts,
        slides,
    };
};

{
    const runtime = buildRuntime("ltr");
    assert.equal(runtime.currentLabel.textContent, "Before 1 of 1");
    assert.equal(runtime.currentCounter.textContent, "1 / 3");
    assert.equal(runtime.slides[0].hidden, false);
    assert.equal(runtime.slides[1].hidden, true);
    assert.equal(runtime.cardVideo.getAttribute("src"), null, "hidden video must remain unhydrated");

    runtime.nextButton.dispatch("click");
    assert.equal(runtime.lightbox.open, false, "card next must only change the slide");
    assert.equal(runtime.currentLabel.textContent, "Video 1 of 1");
    assert.equal(runtime.currentCounter.textContent, "2 / 3");
    assert.equal(runtime.cardVideo.getAttribute("src"), "/video");
    assert.ok(runtime.cardVideo.pauseCount > 0, "slide changes must pause card videos");

    const cardNextKey = runtime.card.dispatch("keydown", {
        key: "ArrowRight",
        target: runtime.card,
    });
    assert.equal(cardNextKey.defaultPrevented, true);
    assert.equal(runtime.currentLabel.textContent, "After 1 of 1");
    runtime.card.dispatch("keydown", { key: "ArrowLeft", target: runtime.card });
    assert.equal(runtime.currentLabel.textContent, "Video 1 of 1");

    runtime.card.dispatch("click", { target: runtime.cardVideo });
    assert.equal(runtime.lightbox.open, false, "native video controls must not open the lightbox");

    runtime.expandButtons[1].dispatch("click");
    assert.equal(runtime.lightbox.open, true);
    assert.equal(runtime.lightboxLabel.textContent, "Video 1 of 1");
    assert.equal(runtime.lightboxCounter.textContent, "2 / 3");
    assert.equal(runtime.lightboxMedia.children[0].tagName, "VIDEO");
    assert.equal(runtime.lightboxMedia.children[0].muted, true);
    assert.equal(runtime.lightboxMedia.children[0].getAttribute("poster"), null);
    assert.equal(runtime.lightboxMedia.children[0].poster, "/video-cover");
    assert.equal(runtime.lightboxClose.focused, true);

    const expandedVideo = runtime.lightboxMedia.children[0];
    runtime.lightbox.dispatch("keydown", { key: "ArrowRight", target: runtime.lightbox });
    assert.equal(runtime.lightboxLabel.textContent, "After 1 of 1");
    assert.ok(expandedVideo.pauseCount > 0, "leaving a lightbox video must pause it");

    runtime.lightboxClose.dispatch("click");
    assert.equal(runtime.lightbox.open, false);
    assert.equal(runtime.lightboxMedia.children.length, 0);
    assert.equal(runtime.expandButtons[1].focused, true, "close must restore focus to the opener");

    runtime.previousButton.dispatch("click");
    assert.equal(runtime.lightbox.open, false, "card previous must only change the slide");
}

{
    const runtime = buildRuntime("rtl");
    runtime.card.dispatch("keydown", { key: "ArrowLeft", target: runtime.card });
    assert.equal(runtime.currentLabel.textContent, "Video 1 of 1", "RTL ArrowLeft must move next");
    runtime.card.dispatch("keydown", { key: "ArrowRight", target: runtime.card });
    assert.equal(runtime.currentLabel.textContent, "Before 1 of 1", "RTL ArrowRight must move previous");

    runtime.expandButtons[0].dispatch("click");
    runtime.lightbox.dispatch("keydown", { key: "ArrowLeft", target: runtime.lightbox });
    assert.equal(runtime.lightboxLabel.textContent, "Video 1 of 1", "RTL lightbox keys must match the card");
    const expandedVideo = runtime.lightboxMedia.children[0];
    runtime.lightboxClose.dispatch("click");
    assert.ok(expandedVideo.pauseCount > 0, "closing an expanded video must pause it");
}

process.stdout.write("public case carousel runtime behavior passed\n");
