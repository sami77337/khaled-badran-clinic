# WhatsApp UX closeout

This note records the owner-approved Commercial Delivery v1 corrections that supersede older WhatsApp setup wording where the two conflict.

## Current behavior

- The main WhatsApp list remains Arabic-first and exposes booking, consultation, patient account, clinic location, staff handoff, and a visible language entry.
- Booking first asks whether the user is a new patient or already has a patient record. New patients use the existing public login-free booking flow; existing patients use the existing protected patient-portal booking route.
- Consultation keeps the existing registered-patient and guest flows and provides a Main Menu escape.
- Staff handoff suppresses normal bot replies as before, but the acknowledgement contains a Main Menu button so the user can explicitly resume automation without typing a command. The existing `menu`, `start`, `القائمة`, and `ابدأ` commands remain fallbacks.
- Arabic and English clinic-location actions use the approved Google Maps destination through a direct CTA URL.
- The guest-consultation phone field reuses the existing international phone picker, with Jordan `+962` as the default and the same server-side E.164 normalization.
- The website's primary/floating WhatsApp bot entry links use the dedicated bot number `+962798898510` with no prefilled text, so Meta Ice Breakers can remain visible. The clinic's ordinary public telephone/contact number remains unchanged.

## Language-first entry

Production Meta Ice Breakers are intentionally limited to two choices:

- `العربية`
- `English`

Selecting either starter is received as a normal inbound text command. The webhook stores the selected language for the bounded conversation state and immediately sends the main menu in that language.

If a user sends any other text while the bot is active, the application does not reflect or persist that text. Instead it sends a bilingual language-choice message containing only `العربية` and `English`. After selection, the normal main menu is sent in the requested language.

Staff handoff remains isolated from this fallback: arbitrary text sent after `التحدث مع العيادة` stays suppressed from bot automation until the user explicitly resumes with the Main Menu button or one of the existing menu/language commands.

Opening or locally deleting a WhatsApp conversation does not itself produce an application webhook, so no server-side automatic welcome is assumed. Ice Breakers are the client-side first-contact entry when WhatsApp shows them.

## Browser behavior

Clinic CTAs use normal HTTPS URLs. The WhatsApp client decides whether those URLs open in its in-app browser or the device's default browser; the application does not use Android-only intent hacks or other unsupported forcing behavior.
