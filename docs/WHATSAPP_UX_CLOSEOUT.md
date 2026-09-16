# WhatsApp UX closeout

This note records the owner-approved Commercial Delivery v1 corrections that supersede older WhatsApp setup wording where the two conflict.

## Current behavior

- The main WhatsApp list remains Arabic-first and exposes booking, consultation, patient account, published cases, clinic location, staff handoff, and a visible language entry.
- Booking first asks whether the user is a new patient or already has a patient record. New patients use the existing public login-free booking flow; existing patients use the existing protected patient-portal booking route.
- Consultation keeps the existing registered-patient and guest flows and provides a Main Menu escape.
- Staff handoff suppresses normal bot replies as before, but the acknowledgement contains a Main Menu button so the user can explicitly resume automation without typing a command. Normal free-text follow-ups remain suppressed while handoff is active.
- Arabic and English clinic-location actions use the approved Google Maps destination through a direct CTA URL. The old Arabic LOCATION-template workaround is obsolete; `WHATSAPP_META_LOCATION_TEMPLATE` is not required by the application configuration check.
- The guest-consultation phone field reuses the existing international phone picker, with Jordan `+962` as the default and the same server-side E.164 normalization.
- The clinic public phone and WhatsApp contact number are unified on `+962 7 9889 8510` (`+962798898510`).
- The website's primary/floating WhatsApp bot entry links open the dedicated clinic number without a prefilled `ابدأ` / `start` message so Meta conversational components can appear cleanly.
- `حالات علاجية منشورة` / `Published Cases` opens the existing consent-gated public cases page. No patient media is sent directly by the bot.
- Unknown free text such as `.`, `مرحبا`, or `Hi` does not open the Arabic menu by default. Outside staff handoff it returns a bilingual two-button chooser: `العربية` / `English`. Selecting a language immediately opens the main menu in that language.
- Explicit `menu`, `start`, `القائمة`, and `ابدأ` commands continue to open the main menu directly using the saved/default language.

## Meta conversational components

The production WhatsApp business phone uses two Ice Breakers only:

- `العربية`
- `English`

Selecting either language is treated as an inbound user message, stores the language choice for the normal conversation window, and returns the corresponding main menu. Opening a chat by itself does not create a server-side webhook, so no unsupported automatic outbound welcome is assumed.

## Browser behavior

Clinic CTAs use normal HTTPS URLs. The WhatsApp client decides whether those URLs open in its in-app browser or the device's default browser; the application does not use Android-only intent hacks or other unsupported forcing behavior.
