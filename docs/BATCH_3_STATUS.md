# Batch 3 Status — Public Website Foundation

## Scope Implemented

- Public bilingual website routes for Arabic default pages and English `/en/` pages.
- Warm premium medical design system using local CSS tokens:
  - warm ivory `#F8F7F0`
  - soft beige `#C7B6A2`
  - wood brown `#645A4C`
  - dark brown/charcoal `#332C29`
  - deep clinic red `#B75844`
  - dark burgundy `#844E41`
- Django template foundation with reusable partials for header, footer, CTA, page hero, and service cards.
- Home, doctor, services, contact, privacy, terms, medical disclaimer, and WhatsApp policy templates.
- Safe local placeholder SVGs for doctor, clinic, map, and app icon assets.
- SEO basics:
  - page titles and meta descriptions
  - Open Graph placeholders
  - canonical links
  - `robots.txt`
  - `sitemap.xml`
- PWA basics:
  - `static/site.webmanifest`
  - placeholder app icon
  - non-caching `static/sw.js` file, not registered by default
- `seed_public_content` management command for safe public clinic, doctor, and visit-type content.
- Public page smoke/content tests and seed command tests.

## Routes

Arabic/default:

- `/`
- `/doctor/`
- `/services/`
- `/contact/`
- `/privacy/`
- `/terms/`
- `/medical-disclaimer/`
- `/whatsapp-policy/`

English:

- `/en/`
- `/en/doctor/`
- `/en/services/`
- `/en/contact/`
- `/en/privacy/`
- `/en/terms/`
- `/en/medical-disclaimer/`
- `/en/whatsapp-policy/`

Utility:

- `/health/`
- `/robots.txt`
- `/sitemap.xml`

## Seed Command

```bash
python manage.py seed_public_content
```

Behavior:

- Upserts one active clinic profile with official Arabic and English names.
- Upserts one active Dr. Khaled Badran doctor profile.
- Upserts nine initial visit types.
- Leaves prices null and hidden from patients.
- Does not create patients, appointments, WhatsApp messages, files, or booking slots.
- Safe to run more than once.

## Explicitly Left Out

- Real booking submission.
- Appointment slot generation.
- Patient portal.
- WhatsApp webhook or WhatsApp sending.
- File uploads.
- Dashboard operations.
- Real patient data.
- Medical AI, diagnosis automation, or treatment automation.
- Real API keys or secrets.

## Recommended Next Batch

Batch 4 should implement the booking MVP only after confirming schedule and availability rules:

- visit type selection
- available slot display
- patient name and phone capture
- confirmation behavior
- no WhatsApp sending until the WhatsApp batch
- tests for booking validation and appointment creation
