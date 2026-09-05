"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const phoneScriptPath = process.argv[2];

if (!phoneScriptPath) {
    throw new Error("Expected a phone-picker script path as the first argument.");
}

const phoneScript = fs.readFileSync(phoneScriptPath, "utf8");

class FakeEventTarget {
    constructor() {
        this.listeners = new Map();
    }

    addEventListener(type, callback) {
        const listeners = this.listeners.get(type) || [];
        listeners.push(callback);
        this.listeners.set(type, listeners);
    }

    dispatch(type, properties = {}) {
        const event = {
            defaultPrevented: false,
            key: "",
            target: this,
            preventDefault() {
                this.defaultPrevented = true;
            },
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

    contains(value) {
        return this.values.has(value);
    }

    remove(value) {
        this.values.delete(value);
    }

    toggle(value, force) {
        const enabled = force === undefined ? !this.values.has(value) : force;
        if (enabled) {
            this.values.add(value);
        } else {
            this.values.delete(value);
        }
        return enabled;
    }
}

class FakeStyle {
    constructor() {
        this.properties = new Map();
    }

    getPropertyValue(name) {
        return this.properties.get(name) || "";
    }

    removeProperty(name) {
        this.properties.delete(name);
    }

    setProperty(name, value) {
        this.properties.set(name, String(value));
    }
}

class FakeElement extends FakeEventTarget {
    constructor(name) {
        super();
        this.attributes = new Map();
        this.checked = false;
        this.classList = new FakeClassList();
        this.dataset = {};
        this.disabled = false;
        this.focusCount = 0;
        this.hidden = false;
        this.id = "";
        this.name = "";
        this.parentElement = null;
        this.placeholder = "";
        this.rect = { top: 0, right: 320, bottom: 0, left: 0, width: 320, height: 0 };
        this.style = new FakeStyle();
        this.textContent = "";
        this.value = "";
        this.debugName = name;
    }

    contains(target) {
        return target === this;
    }

    focus() {
        this.focusCount += 1;
    }

    getBoundingClientRect() {
        return { ...this.rect };
    }

    getClientRects() {
        return this.rect.height > 0 ? [this.getBoundingClientRect()] : [];
    }

    setAttribute(name, value) {
        this.attributes.set(name, String(value));
    }
}

const buildRuntime = () => {
    const heightProperty = "--booking-country-options-max-height";
    const control = new FakeElement("control");
    control.dataset.bookingDefaultDialCode = "+962";
    control.dataset.bookingExampleLabel = "Formatting example";

    const trigger = new FakeElement("trigger");
    const flag = new FakeElement("flag");
    const dial = new FakeElement("dial");
    const menu = new FakeElement("menu");
    menu.hidden = true;
    const search = new FakeElement("search");
    const optionsList = new FakeElement("options-list");
    const empty = new FakeElement("empty");
    const hint = new FakeElement("hint");
    hint.id = "phone-hint";
    const input = new FakeElement("phone-input");
    input.name = "phone";

    const option = new FakeElement("option");
    option.dataset.countryCode = "JO";
    option.dataset.countryDial = "+962";
    option.dataset.countryExample = "7XXXXXXXX";
    option.dataset.countryFlag = "JO";
    option.dataset.countryNationalPrefix = "0";
    option.dataset.countrySearch = "Jordan JO +962";
    option.parentElement = optionsList;

    const alternateOption = new FakeElement("alternate-option");
    alternateOption.dataset.countryCode = "GB";
    alternateOption.dataset.countryDial = "+44";
    alternateOption.dataset.countryExample = "7XXX XXXXXX";
    alternateOption.dataset.countryFlag = "GB";
    alternateOption.dataset.countryNationalPrefix = "0";
    alternateOption.dataset.countrySearch = "United Kingdom GB +44";
    alternateOption.parentElement = optionsList;
    const options = [option, alternateOption];

    const currentOptionsHeight = () => Number.parseFloat(
        control.style.getPropertyValue(heightProperty)
    ) || 240;
    optionsList.getBoundingClientRect = () => {
        const height = currentOptionsHeight();
        return { top: 570, right: 320, bottom: 570 + height, left: 0, width: 320, height };
    };
    menu.getBoundingClientRect = () => {
        const height = 70 + currentOptionsHeight();
        return { top: 500, right: 320, bottom: 500 + height, left: 0, width: 320, height };
    };

    const selectorMap = new Map([
        ["[data-booking-country-trigger]", trigger],
        ["[data-booking-country-flag]", flag],
        ["[data-booking-country-dial]", dial],
        ["[data-booking-country-menu]", menu],
        ["[data-booking-country-search]", search],
        ["[data-booking-country-options]", optionsList],
        ["[data-booking-country-empty]", empty],
        ["[data-booking-phone-hint]", hint],
        ["input[type='text'], input[type='tel']", input],
    ]);
    control.querySelector = (selector) => selectorMap.get(selector) || null;
    control.querySelectorAll = (selector) => (
        selector === "[data-booking-country-option]" ? options : []
    );
    control.contains = (target) => [
        control, trigger, flag, dial, menu, search, optionsList, empty, hint, input, ...options,
    ].includes(target);

    const form = new FakeElement("form");
    form.querySelectorAll = (selector) => (
        selector === "[data-booking-phone-control]" ? [control] : []
    );
    form.querySelector = () => null;

    const authRoot = new FakeElement("auth-root");
    authRoot.dataset.selectedRole = "patient";
    authRoot.querySelectorAll = () => [];
    authRoot.querySelector = (selector) => (
        selector === "[data-patient-login-form], [data-patient-register-form]" ? form : null
    );

    const bottomNavigation = new FakeElement("bottom-navigation");
    bottomNavigation.rect = { top: 280, right: 320, bottom: 340, left: 0, width: 320, height: 60 };
    const compactHeader = new FakeElement("compact-header");
    compactHeader.rect = { top: 0, right: 320, bottom: 64, left: 0, width: 320, height: 64 };

    const document = new FakeEventTarget();
    document.documentElement = { style: {} };
    document.querySelectorAll = () => [];
    document.querySelector = (selector) => ({
        "[data-auth-login], [data-auth-register]": authRoot,
        "[data-booking-patient-form]": form,
        "[data-mobile-bottom-navigation]": bottomNavigation,
        "[data-portal-compact-header]": compactHeader,
    })[selector] || null;

    const mediaQuery = new FakeEventTarget();
    mediaQuery.matches = true;
    const visualViewport = new FakeEventTarget();
    visualViewport.height = 340;
    visualViewport.offsetTop = 0;

    let nextFrameId = 1;
    const frames = new Map();
    const scrolls = [];
    const window = new FakeEventTarget();
    window.cancelAnimationFrame = (frameId) => frames.delete(frameId);
    window.history = null;
    window.innerHeight = 640;
    window.location = { href: "https://example.test/portal/link/" };
    window.matchMedia = () => mediaQuery;
    window.requestAnimationFrame = (callback) => {
        const frameId = nextFrameId;
        nextFrameId += 1;
        frames.set(frameId, callback);
        return frameId;
    };
    window.scrollBy = (optionsObject) => scrolls.push(optionsObject);
    window.visualViewport = visualViewport;

    const context = vm.createContext({
        Array,
        document,
        Math,
        Number,
        String,
        URL,
        window,
    });
    vm.runInContext(phoneScript, context, { filename: phoneScriptPath });

    const flushFrames = () => {
        while (frames.size) {
            const queuedFrames = Array.from(frames.values());
            frames.clear();
            queuedFrames.forEach((callback) => callback());
        }
    };

    return {
        alternateOption,
        control,
        dial,
        flushFrames,
        form,
        heightProperty,
        input,
        menu,
        option,
        scrolls,
        search,
        trigger,
        visualViewport,
    };
};

const runtime = buildRuntime();

runtime.trigger.dispatch("click", { detail: 0, pointerType: "touch" });
runtime.flushFrames();
assert.equal(runtime.menu.hidden, false, "touch must open the country menu");
assert.equal(runtime.search.focusCount, 0, "a touch click with detail=0 must not focus search");
assert.equal(runtime.control.classList.contains("is-open"), true);
assert.equal(
    runtime.control.style.getPropertyValue(runtime.heightProperty),
    "130px",
    "the options viewport must fit between the fixed header and bottom navigation",
);
assert.equal(
    runtime.scrolls.at(-1).top,
    428,
    "the open in-flow menu must be scrolled clear of fixed mobile chrome",
);
assert.equal(runtime.scrolls.at(-1).behavior, "auto");

runtime.trigger.dispatch("click");
assert.equal(runtime.menu.hidden, true);
assert.equal(runtime.control.style.getPropertyValue(runtime.heightProperty), "");

const keyboardOpen = runtime.trigger.dispatch("keydown", { key: "Enter" });
runtime.flushFrames();
assert.equal(keyboardOpen.defaultPrevented, true);
assert.equal(runtime.menu.hidden, false);
assert.equal(runtime.search.focusCount, 1, "explicit keyboard activation must focus search");

runtime.input.value = "0790000000";
runtime.alternateOption.dispatch("click");
assert.equal(runtime.menu.hidden, true, "choosing a country must close the menu");
assert.equal(runtime.dial.textContent, "+44");
assert.equal(runtime.input.value, "790000000");
assert.equal(runtime.input.focusCount, 0, "country selection must not force-open the phone keyboard");
assert.ok(runtime.trigger.focusCount > 0, "country selection must restore focus to the trigger");

runtime.option.dispatch("click");
runtime.input.value = "791234567";
runtime.form.dispatch("submit");
assert.equal(
    runtime.input.value,
    "+962791234567",
    "native submit must write the composed phone value before browser serialization",
);

runtime.trigger.dispatch("click");
runtime.flushFrames();
runtime.visualViewport.height = 240;
runtime.visualViewport.dispatch("resize");
runtime.flushFrames();
assert.equal(
    runtime.control.style.getPropertyValue(runtime.heightProperty),
    "90px",
    "visual viewport resize must keep a reduced-height options list scrollable",
);

process.stdout.write("phone picker runtime behavior passed\n");
