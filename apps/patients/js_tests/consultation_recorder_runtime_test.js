"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(process.argv[2], "utf8");
const settle = () => new Promise(resolve => setImmediate(resolve));

class Element extends EventTarget {
    constructor() {
        super();
        this.dataset = {};
        this.hidden = false;
        this.disabled = false;
        this.files = [];
        this.paused = true;
    }
    set value(value) { this._value = value; if (value === "") this.files = []; }
    get value() { return this._value; }
    removeAttribute(name) { delete this[name]; }
    load() {}
    pause() { this.paused = true; }
    play() { this.paused = false; return Promise.resolve(); }
    click() { this.dispatchEvent(new Event("click")); }
}

function harness() {
    const elements = Object.fromEntries([
        "input", "start", "stop", "listen", "record-again", "remove", "timer", "status",
        "local-preview", "existing-preview",
    ].map(name => [name, new Element()]));
    elements["local-preview"].hidden = true;
    const removeInput = new Element();
    const root = new Element();
    root.dataset = { hasExistingAudio: "false", permissionMessage: "Permission failed", readyMessage: "Ready" };
    root.querySelector = selector => selector.startsWith("input") ? removeInput
        : elements[selector === "[data-consultation-audio-input]" ? "input" : selector.slice(12, -1)];
    const form = new Element();
    const submissions = [];
    form.requestSubmit = submitter => submissions.push({ submitter, files: [...elements.input.files] });
    const requests = [], recorders = [], streams = [], stopEvents = [], revoked = [];
    const timers = new Map();
    let timerId = 0;
    class Recorder extends EventTarget {
        static isTypeSupported() { return true; }
        constructor(stream, options) {
            super(); this.stream = stream; this.mimeType = options.mimeType; this.state = "inactive";
            recorders.push(this);
        }
        start() { this.state = "recording"; }
        stop() {
            assert.notEqual(this.state, "inactive", "recorder must be stopped only once");
            this.state = "inactive";
            stopEvents.push(() => {
                const event = new Event("dataavailable");
                event.data = new Blob(["synthetic audio"], { type: this.mimeType });
                this.dispatchEvent(event);
                this.dispatchEvent(new Event("stop"));
            });
        }
    }
    class Transfer {
        constructor() { this.files = []; this.items = { add: file => this.files.push(file) }; }
    }
    const window = new EventTarget();
    Object.assign(window, {
        MediaRecorder: Recorder, DataTransfer: Transfer, File,
        setInterval: fn => { timers.set(++timerId, fn); return timerId; },
        setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
        clearInterval: id => timers.delete(id), clearTimeout: id => timers.delete(id),
    });
    vm.runInNewContext(source, {
        window, document: { querySelector: selector => selector.includes("reply-form") ? form : root },
        navigator: { mediaDevices: { getUserMedia: () => new Promise((resolve, reject) => requests.push({ resolve, reject })) } },
        MediaRecorder: Recorder, DataTransfer: Transfer, File, Blob, Date,
        URL: { createObjectURL: () => `blob:synthetic-${recorders.length}`, revokeObjectURL: url => revoked.push(url) },
    });
    return {
        elements, window, requests, recorders, streams, timers, submissions, revoked,
        resolve(index) {
            const tracks = [0, 1].map(() => ({ stopped: false, stop() { this.stopped = true; } }));
            const stream = { getTracks: () => tracks };
            streams.push(stream); requests[index].resolve(stream); return stream;
        },
        flushStop() { while (stopEvents.length) stopEvents.shift()(); },
        submit() {
            const event = new Event("submit", { cancelable: true });
            event.submitter = elements.start;
            form.dispatchEvent(event); return event;
        },
        assertStopped() {
            assert(streams.every(stream => stream.getTracks().every(track => track.stopped)));
            assert(recorders.every(recorder => recorder.state === "inactive"));
            assert.equal(timers.size, 0);
        },
    };
}

async function main() {
    let cases = 0;
    {
        const h = harness();
        h.elements.start.click();
        assert.equal(h.elements.start.disabled, true);
        h.elements.start.click(); h.elements["record-again"].click();
        assert.equal(h.requests.length, 1, "duplicate starts must not acquire another stream");
        h.resolve(0); await settle();
        assert.equal(h.recorders.length, 1);
        h.elements.stop.click();
        h.assertStopped();
        assert.equal(h.elements.start.disabled, true, "wait for final recording data");
        h.elements.start.click();
        assert.equal(h.requests.length, 1);
        h.flushStop();
        assert.equal(h.elements.start.disabled, false);
        assert.equal(h.elements.input.files.length, 1);
        cases++;
    }
    {
        const h = harness(); h.elements.start.click();
        h.requests[0].reject(new Error("permission denied")); await settle();
        assert.equal(h.elements.start.disabled, false);
        assert.equal(h.elements.status.textContent, "Permission failed");
        h.assertStopped();
        h.elements.start.click(); assert.equal(h.requests.length, 2);
        h.elements.stop.click(); h.resolve(1); await settle(); h.assertStopped(); cases++;
    }
    for (const staleFirst of [true, false]) {
        const h = harness(); h.elements.start.click(); h.elements.stop.click(); h.elements.start.click();
        assert.equal(h.requests.length, 2);
        if (staleFirst) { h.resolve(0); await settle(); assert.equal(h.recorders.length, 0); }
        h.resolve(1); await settle();
        const current = h.recorders[0];
        if (!staleFirst) { h.resolve(0); await settle(); }
        assert.equal(h.recorders.length, 1);
        assert(current.stream.getTracks().every(track => !track.stopped));
        h.elements.stop.click(); h.flushStop(); h.assertStopped(); cases++;
    }
    for (const eventName of ["beforeunload", "pagehide"]) {
        const h = harness(); h.elements.start.click();
        h.window.dispatchEvent(new Event(eventName)); h.resolve(0); await settle();
        assert.equal(h.recorders.length, 0); h.assertStopped(); cases++;
    }
    {
        const h = harness(); h.elements.start.click(); h.resolve(0); await settle();
        h.elements.stop.click(); h.flushStop();
        h.elements["record-again"].click();
        assert.equal(h.revoked.length, 1);
        assert.equal(h.elements.input.files.length, 0);
        h.resolve(1); await settle(); h.elements.stop.click(); h.flushStop();
        assert.equal(h.elements.input.files.length, 1); h.assertStopped(); cases++;
    }
    for (const alreadyStopping of [true, false]) {
        const h = harness(); h.elements.start.click(); h.resolve(0); await settle();
        if (alreadyStopping) h.elements.stop.click();
        assert.equal(h.submit().defaultPrevented, true);
        assert.equal(h.submissions.length, 0);
        h.flushStop(); h.assertStopped();
        assert.equal(h.submissions.length, 1);
        assert.equal(h.submissions[0].files.length, 1);
        assert.equal(h.submit().defaultPrevented, false); cases++;
    }
    {
        const h = harness(); h.elements.start.click(); h.resolve(0); await settle();
        h.window.dispatchEvent(new Event("pagehide")); h.flushStop(); h.assertStopped();
        assert.equal(h.elements.input.files.length, 0, "cleanup must ignore old stop callbacks"); cases++;
    }
    {
        const h = harness(); h.elements.start.click();
        assert.equal(h.submit().defaultPrevented, false);
        h.resolve(0); await settle(); h.assertStopped();
        assert.equal(h.recorders.length, 0); cases++;
    }
    console.log(`PASS: consultation recorder runtime (${cases} lifecycle cases; no physical microphone)`);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
