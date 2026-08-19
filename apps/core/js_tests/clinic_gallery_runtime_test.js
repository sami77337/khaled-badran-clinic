"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const siteScriptPath = process.argv[2];

if (!siteScriptPath) {
    throw new Error("Expected the site.js path as the first argument.");
}

const siteScript = fs.readFileSync(siteScriptPath, "utf8");

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
            key: "",
            pointerType: "mouse",
            relatedTarget: null,
            preventDefault() {},
            ...properties,
            type,
        };
        (this.listeners.get(type) || []).forEach((callback) => callback(event));
    }
}

class FakeClassList {
    constructor() {
        this.values = new Set();
    }

    add(value) {
        this.values.add(value);
    }

    remove(value) {
        this.values.delete(value);
    }

    contains(value) {
        return this.values.has(value);
    }

    toggle(value, force) {
        if (force === true) {
            this.add(value);
            return true;
        }
        if (force === false) {
            this.remove(value);
            return false;
        }
        if (this.contains(value)) {
            this.remove(value);
            return false;
        }
        this.add(value);
        return true;
    }
}

class FakeNode extends FakeEventTarget {
    constructor(name) {
        super();
        this.name = name;
        this.attributes = new Map();
        this.children = [];
        this.classList = new FakeClassList();
        this.hidden = false;
        this.offsetWidth = 1080;
        this.parentElement = null;
        this.textContent = "";
        this.lastScrollOptions = null;
    }

    append(child) {
        if (child.parentElement) {
            const previousIndex = child.parentElement.children.indexOf(child);
            if (previousIndex >= 0) {
                child.parentElement.children.splice(previousIndex, 1);
            }
        }
        child.parentElement = this;
        this.children.push(child);
    }

    contains(target) {
        if (target === this) {
            return true;
        }
        return this.children.some((child) => child.contains(target));
    }

    getBoundingClientRect() {
        const index = this.parentElement ? this.parentElement.children.indexOf(this) : 0;
        return {
            left: index * 360,
            right: (index + 1) * 360,
        };
    }

    removeAttribute(name) {
        this.attributes.delete(name);
    }

    scrollIntoView(options) {
        this.lastScrollOptions = options;
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
    }
}

const buildRuntime = ({ desktop = true, reducedMotion = false } = {}) => {
    const intervals = new Map();
    const timeouts = new Map();
    let timerSequence = 0;

    const track = new FakeNode("track");
    const slides = Array.from({ length: 5 }, (_, index) => new FakeNode(`slide-${index + 1}`));
    slides.forEach((slide) => track.append(slide));

    const viewport = new FakeNode("viewport");
    const dots = Array.from({ length: 5 }, (_, index) => new FakeNode(`dot-${index + 1}`));
    const previousButton = new FakeNode("previous");
    const nextButton = new FakeNode("next");
    const controls = new FakeNode("controls");
    const currentPosition = new FakeNode("current");
    currentPosition.textContent = "1";
    const gallery = new FakeNode("gallery");
    viewport.append(track);
    gallery.append(viewport);
    dots.forEach((dot) => gallery.append(dot));
    gallery.append(previousButton);
    gallery.append(nextButton);
    gallery.append(controls);
    gallery.append(currentPosition);

    gallery.querySelector = (selector) => ({
        "[data-gallery-viewport]": viewport,
        "[data-gallery-previous]": previousButton,
        "[data-gallery-next]": nextButton,
        "[data-gallery-controls]": controls,
        "[data-gallery-current]": currentPosition,
    })[selector] || null;
    gallery.querySelectorAll = (selector) => ({
        "[data-gallery-slide]": slides,
        "[data-gallery-dot]": dots,
    })[selector] || [];

    const mediaQueries = new Map();
    const matchMedia = (query) => {
        if (!mediaQueries.has(query)) {
            const mediaQuery = new FakeEventTarget();
            mediaQuery.matches = query.includes("prefers-reduced-motion")
                ? reducedMotion
                : (query.includes("min-width: 768px") ? desktop : false);
            mediaQueries.set(query, mediaQuery);
        }
        return mediaQueries.get(query);
    };

    const document = new FakeEventTarget();
    document.hidden = false;
    document.querySelector = () => null;
    document.querySelectorAll = (selector) => (
        selector === "[data-clinic-gallery]" ? [gallery] : []
    );

    const window = new FakeEventTarget();
    window.cancelAnimationFrame = () => {};
    window.clearInterval = (timerId) => intervals.delete(timerId);
    window.clearTimeout = (timerId) => timeouts.delete(timerId);
    window.getComputedStyle = () => ({ direction: "ltr" });
    window.matchMedia = matchMedia;
    window.requestAnimationFrame = (callback) => {
        callback();
        return ++timerSequence;
    };
    window.setInterval = (callback, milliseconds) => {
        const timerId = ++timerSequence;
        intervals.set(timerId, { callback, milliseconds });
        return timerId;
    };
    window.setTimeout = (callback, milliseconds) => {
        const timerId = ++timerSequence;
        timeouts.set(timerId, { callback, milliseconds });
        return timerId;
    };

    const context = vm.createContext({
        Array,
        document,
        Node: FakeNode,
        Number,
        Set,
        window,
    });
    vm.runInContext(siteScript, context, { filename: siteScriptPath });

    return {
        controls,
        currentPosition,
        document,
        dots,
        gallery,
        intervals,
        nextButton,
        previousButton,
        slides,
        timeouts,
        track,
        viewport,
    };
};

const runOnlyInterval = (runtime) => {
    assert.equal(runtime.intervals.size, 1, "exactly one autoplay timer should be active");
    const [{ callback, milliseconds }] = runtime.intervals.values();
    assert.equal(milliseconds, 6000, "autoplay should use the calm six-second interval");
    callback();
};

const runOnlyTimeout = (runtime) => {
    assert.equal(runtime.timeouts.size, 1, "manual navigation should schedule one resume");
    const [timerId, { callback, milliseconds }] = runtime.timeouts.entries().next().value;
    assert.equal(milliseconds, 7000, "manual pause should remain long enough to inspect the photo");
    runtime.timeouts.delete(timerId);
    callback();
};

{
    const runtime = buildRuntime({ desktop: true });
    assert.equal(runtime.currentPosition.textContent, "1");
    assert.deepEqual(runtime.track.children.map((slide) => slide.name), [
        "slide-1", "slide-2", "slide-3", "slide-4", "slide-5",
    ]);
    assert.equal(
        runtime.slides.filter((slide) => slide.lastScrollOptions !== null).length,
        0,
        "desktop initialization must not turn the grid into a scrolled one-slide viewport",
    );

    runOnlyInterval(runtime);
    assert.equal(runtime.currentPosition.textContent, "2", "autoplay must advance the live index");
    assert.equal(runtime.dots[1].attributes.get("aria-pressed"), "true");
    assert.deepEqual(runtime.track.children.slice(0, 3).map((slide) => slide.name), [
        "slide-2", "slide-3", "slide-4",
    ]);
    assert.equal(
        runtime.slides.filter((slide) => slide.lastScrollOptions !== null).length,
        0,
        "desktop autoplay must change the leading grid composition without scrolling",
    );

    runOnlyInterval(runtime);
    runOnlyInterval(runtime);
    assert.deepEqual(runtime.track.children.slice(0, 3).map((slide) => slide.name), [
        "slide-4", "slide-5", "slide-1",
    ], "desktop must cycle five unique photos through the three visible positions");

    runtime.nextButton.dispatch("click");
    assert.equal(runtime.intervals.size, 0, "manual navigation must pause autoplay");
    assert.equal(runtime.currentPosition.textContent, "5", "next must advance the desktop lead");
    runtime.previousButton.dispatch("click");
    assert.equal(runtime.currentPosition.textContent, "4", "previous must restore the prior desktop lead");
    runtime.dots[0].dispatch("click");
    assert.equal(runtime.currentPosition.textContent, "1", "dots must select their desktop lead");
    assert.deepEqual(runtime.track.children.slice(0, 3).map((slide) => slide.name), [
        "slide-1", "slide-2", "slide-3",
    ], "the reception photo must remain the initial and selectable leading image");
    assert.equal(
        runtime.slides.filter((slide) => slide.lastScrollOptions !== null).length,
        0,
        "desktop manual controls must rotate the grid without horizontal scrolling",
    );
    runOnlyTimeout(runtime);
    assert.equal(runtime.intervals.size, 1, "autoplay must resume after manual navigation settles");

    runtime.gallery.dispatch("pointerenter", { pointerType: "mouse" });
    assert.equal(runtime.intervals.size, 0, "hover must pause autoplay");
    runtime.gallery.dispatch("pointerleave");
    assert.equal(runtime.intervals.size, 1, "autoplay must resume after hover ends");

    runtime.viewport.dispatch("pointerdown", { pointerType: "touch" });
    assert.equal(runtime.intervals.size, 0, "touch/swipe interaction must pause autoplay");
    runtime.viewport.dispatch("pointerup", { pointerType: "touch" });
    assert.equal(runtime.intervals.size, 1, "autoplay must resume after touch/swipe interaction");

    runtime.gallery.dispatch("focusin");
    assert.equal(runtime.intervals.size, 0, "focus inside must pause autoplay");
    runtime.gallery.dispatch("focusout", { relatedTarget: null });
    assert.equal(runtime.intervals.size, 1, "autoplay must resume after focus leaves");

    runtime.document.hidden = true;
    runtime.document.dispatch("visibilitychange");
    assert.equal(runtime.intervals.size, 0, "hidden documents must stop autoplay");
    runtime.document.hidden = false;
    runtime.document.dispatch("visibilitychange");
    assert.equal(runtime.intervals.size, 1, "visible documents must safely resume autoplay");
}

{
    const runtime = buildRuntime({ desktop: false });
    runOnlyInterval(runtime);
    assert.equal(runtime.currentPosition.textContent, "2");
    assert.deepEqual(runtime.track.children.map((slide) => slide.name), [
        "slide-1", "slide-2", "slide-3", "slide-4", "slide-5",
    ], "mobile swipe order must preserve the owner's deterministic sequence");
    assert.equal(runtime.slides[1].lastScrollOptions.behavior, "smooth");
}

{
    const runtime = buildRuntime({ desktop: false, reducedMotion: true });
    assert.equal(runtime.intervals.size, 0, "reduced motion must prevent autoplay");
    runtime.nextButton.dispatch("click");
    assert.equal(runtime.currentPosition.textContent, "2", "manual controls must still work");
    assert.equal(runtime.slides[1].lastScrollOptions.behavior, "auto");
    runOnlyTimeout(runtime);
    assert.equal(runtime.intervals.size, 0, "reduced motion must prevent resumed autoplay too");
}

process.stdout.write("clinic gallery runtime behavior passed\n");
