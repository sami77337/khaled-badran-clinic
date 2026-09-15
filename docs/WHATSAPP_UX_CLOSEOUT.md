# WhatsApp UX closeout

This note records the owner-approved Commercial Delivery v1 corrections that supersede older WhatsApp setup wording where the two conflict.

## Current behavior

- The main WhatsApp list remains Arabic-first and exposes booking, consultation, patient account, clinic location, staff handoff, and a visible language entry.
- Booking first asks whether the user is a new patient or already has a patient record. New patients use the existing public login-free booking flow; existing patients use the existing protected patient-portal booking route.
- Consultation keeps the existing registered-patient and guest flows and provides a Main Menu escape.
- Staff handoff suppresses normal bot replies as before, but the acknowledgement now contains a Main Menu button so the user can explicitly resume automation without typing a command. The existing `menu`, `start`, `القائمة`, and `ابدأ` commands remain fallbacks.
- Arabic and English clinic-location actions use the approved Google Maps destination through a direct CTA URL. The old Arabic LOCATION-template workaround is obsolete; `WHATSAPP_META_LOCATION_TEMPLATE` is not required by the application configuration check.
- The guest-consultation phone field reuses the existing international phone picker, with Jordan `+962` as the default and the same server-side E.164 normalization.
- The website's primary/floating WhatsApp bot entry links use the dedicated bot number `+962798898510` with a localized prefilled `ابدأ` / `start` message. The clinic's ordinary public telephone/contact number remains unchanged.

## Meta conversational components

Configure four Ice Breakers on the production WhatsApp business phone when the Meta UI/API exposes conversational components:

- `حجز موعد` / `Book an Appointment`
- `استشارة طبية` / `Medical Consultation`
- `حساب المريض` / `Patient Account`
- `التحدث مع العيادة` / `Talk to the Clinic`

The webhook recognizes these approved labels, but application correctness does not depend on Ice Breakers. Opening or locally deleting a WhatsApp conversation does not itself produce an application webhook, so no server-side automatic welcome is assumed.

## Browser behavior

Clinic CTAs use normal HTTPS URLs. The WhatsApp client decides whether those URLs open in its in-app browser or the device's default browser; the application does not use Android-only intent hacks or other unsupported forcing behavior.
