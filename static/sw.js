self.addEventListener("install", (event) => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
});

// Never cache authenticated pages, API responses, or private media.
const PUSH_EVENTS = {
    "new-consultation": {
        tag: "kbc-new-consultation",
        path: "/dashboard/consultations/",
        ar: ["استشارة جديدة", "لديك استشارة جديدة في العيادة."],
        en: ["New consultation", "You have a new consultation at the clinic."],
    },
    "new-booking": {
        tag: "kbc-new-booking",
        path: "/staff/appointments/",
        ar: ["موعد جديد", "تم حجز موعد جديد عبر الموقع."],
        en: ["New appointment", "A new appointment has been booked through the website."],
    },
};

function pushDetails(data) {
    if (!data || !Object.hasOwn(PUSH_EVENTS, data.event) || !["ar", "en"].includes(data.language)) return null;
    return PUSH_EVENTS[data.event];
}

self.addEventListener("push", (event) => {
    let data;
    try { data = event.data.json(); } catch (_) { return; }
    const details = pushDetails(data);
    if (!details) return;
    // Ignore all supplied text/URLs/options; only this fixed neutral copy is shown.
    const [title, body] = details[data.language];
    event.waitUntil(self.registration.showNotification(title, {
        body,
        tag: details.tag,
        lang: data.language,
        dir: data.language === "ar" ? "rtl" : "ltr",
        requireInteraction: false,
        renotify: false,
        data: { event: data.event, language: data.language },
    }));
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const data = event.notification.data;
    const details = pushDetails(data);
    if (!details) return;
    const destination = new URL(details.path + (data.language === "en" ? "?lang=en" : ""), self.location.origin).href;
    event.waitUntil((async () => {
        const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
        for (const client of windows) {
            const url = new URL(client.url);
            if (url.origin !== self.location.origin || !["/dashboard/", "/staff/"].some(path => url.pathname.startsWith(path))) continue;
            try {
                const target = client.url === destination ? client : await client.navigate(destination);
                if (target) { await target.focus(); return; }
            } catch (_) { /* A closing window must not swallow the click. */ }
        }
        await self.clients.openWindow(destination);
    })());
});
