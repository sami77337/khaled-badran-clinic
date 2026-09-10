# Meta WhatsApp Cloud API — Production Setup

This document covers the production-only provider setup for the clinic's
owner-approved WhatsApp UX. It does not contain real credentials.

## Scope

WhatsApp is used for:

- welcome and service routing;
- guest consultation OTP delivery;
- neutral consultation-reply notifications;
- booking confirmation;
- appointment reminders;
- clinic-location routing;
- handoff to clinic staff.

Medical consultation text, images, video, PDF, clinical records, diagnosis,
treatment, and doctor voice replies remain on the website and are not copied
into WhatsApp provider payloads.

## Provider

Use Meta WhatsApp Cloud API directly.

Required production environment values:

```text
WHATSAPP_META_ENABLED=true
WHATSAPP_META_ACCESS_TOKEN=<environment secret>
WHATSAPP_META_PHONE_NUMBER_ID=<Meta phone-number id>
WHATSAPP_META_WABA_ID=<Meta WhatsApp Business Account id>
WHATSAPP_META_APP_SECRET=<environment secret>
WHATSAPP_META_VERIFY_TOKEN=<environment secret>
WHATSAPP_META_GRAPH_VERSION=<deployment-approved Graph version>
WHATSAPP_WEBSITE_ORIGIN=https://<production-domain>
WHATSAPP_DEFAULT_LANGUAGE=ar
```

Do not commit any of these real values.

## Webhook

Production callback URL:

```text
https://<production-domain>/integrations/whatsapp/webhook/
```

Configure the Meta app webhook with the same value stored in
`WHATSAPP_META_VERIFY_TOKEN` and subscribe the WhatsApp Business Account to
message events.

The endpoint:

- answers Meta GET verification only when the verify token matches;
- validates `X-Hub-Signature-256` against the exact raw POST body using the
  configured Meta app secret;
- rejects missing/invalid signatures;
- deduplicates inbound message IDs in cache;
- does not store inbound message bodies as patient records;
- never logs provider payloads, tokens, phone numbers, or response bodies.

## Main interactive menu

Arabic-first menu:

- حجز موعد
- استشارة طبية
- حساب المريض
- موقع العيادة
- التحدث مع العيادة

Stable internal IDs:

```text
kbc_book
kbc_consult
kbc_portal
kbc_location
kbc_staff
kbc_consult_registered
kbc_consult_guest
```

Website destinations are rendered as WhatsApp CTA buttons rather than exposing
long URLs as ordinary message text.

Approved Arabic CTA labels include:

- احجز موعدك
- ابدأ الاستشارة
- دخول حساب المريض
- افتح الموقع على الخريطة
- عرض الرد

## Staff handoff

After `التحدث مع العيادة`, send:

```text
يمكنك كتابة رسالتك هنا وسيقوم فريق العيادة بالرد عليك.
```

The bot does not keep replying to normal text while the handoff state is
active. Sending `القائمة`, `ابدأ`, `menu`, or `start` returns to the automated
menu. The handoff flag is cache-based with a bounded TTL and no message body is
stored by this integration.

## Meta templates

Create and approve the following templates in Meta Business Manager. Template
names are configured through environment variables so they can change without
code changes.

### 1. Guest consultation OTP

Environment setting:

```text
WHATSAPP_META_TEMPLATE_GUEST_OTP=<approved-template-name>
```

Category: `AUTHENTICATION`.

Use Meta's OTP/authentication template with the supported OTP button. The
adapter supplies the code as the body parameter and button parameter. Do not
add medical context to this template.

### 2. Consultation reply notification

Environment setting:

```text
WHATSAPP_META_TEMPLATE_CONSULTATION_REPLY=<approved-template-name>
```

Arabic body:

```text
تم إضافة رد جديد من عيادة الدكتور خالد بدران على استشارتك.
```

Arabic URL button label:

```text
عرض الرد
```

English body:

```text
Dr. Khaled Badran Clinic has added a new reply to your consultation.
```

English URL button label:

```text
View Reply
```

Configure the URL button as:

```text
https://<production-domain>/{{1}}
```

The adapter supplies only the website path suffix as `{{1}}`.

### 3. Booking confirmation

Environment setting:

```text
WHATSAPP_META_TEMPLATE_BOOKING_CONFIRMATION=<approved-template-name>
```

Arabic body:

```text
تم تأكيد موعدك في عيادة الدكتور خالد بدران. رقم التأكيد: {{1}}. الموعد: {{2}}.
```

Arabic URL button label:

```text
عرض الموعد
```

English body:

```text
Your appointment at Dr. Khaled Badran Clinic is confirmed. Reference: {{1}}. Appointment: {{2}}.
```

English URL button label:

```text
View Appointment
```

The body parameters are confirmation reference and appointment date/time. Do
not include booking notes or medical reasons.

Configure the URL button as:

```text
https://<production-domain>/{{1}}
```

### 4. Appointment reminder

Environment setting:

```text
WHATSAPP_META_TEMPLATE_APPOINTMENT_REMINDER=<approved-template-name>
```

Arabic body:

```text
تذكير بموعدك في عيادة الدكتور خالد بدران: {{1}}. رقم التأكيد: {{2}}.
```

Arabic URL button label:

```text
عرض الموعد
```

English body:

```text
Reminder for your appointment at Dr. Khaled Badran Clinic: {{1}}. Reference: {{2}}.
```

English URL button label:

```text
View Appointment
```

The template contains no booking note or medical reason.

## Reminder dispatcher

Appointments already contain:

- `reminder_enabled`;
- `reminder_offset`;
- `reminder_sent_at`.

Run from a production scheduler:

```bash
python manage.py send_whatsapp_reminders --limit 100
```

The command only selects upcoming confirmed/rescheduled appointments whose
configured reminder time is due. It locks each selected appointment while
sending, marks `reminder_sent_at` only after provider acceptance, and leaves a
failed delivery retryable.

A five-minute scheduler interval is a suitable starting operational cadence for
this clinic; the appointment's configured offset remains the source of truth
for when a reminder becomes due.

## Go-live verification

Before enabling production traffic:

1. Meta Business/WABA ownership is confirmed for the clinic.
2. The owner-approved clinic number is added and verified in Meta.
3. The display name is approved by Meta.
4. All four required templates are approved.
5. Production environment variables are configured outside Git.
6. Webhook GET verification succeeds.
7. A signed synthetic inbound message produces the main menu.
8. Each menu action opens the intended website destination.
9. Guest OTP delivery is tested with a controlled test account.
10. Consultation reply notification is tested without medical text in the
    provider payload.
11. Booking confirmation is tested.
12. Reminder command is tested against a synthetic future appointment.
13. Logs are reviewed to confirm that no token, phone number, or provider
    payload is emitted.
