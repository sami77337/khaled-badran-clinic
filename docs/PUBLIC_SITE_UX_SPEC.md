# Public Site UX Specification

This document defines the final public-site UX for Dr. Khaled Badran Clinic.
It is a product/content specification only. It does not change visual design and
does not create Figma work.

## Current Baseline

The current public site includes Arabic/default and English pages for home,
doctor, services, contact, privacy, terms, medical disclaimer, WhatsApp policy,
robots, and sitemap. It has shared navigation, a language switch, booking CTA,
legal footer links, placeholder assets, and mobile-first CSS.

Current content caveat: some public/legal copy still reflects earlier batches
and says booking or portal features are not available, while current booking
and bounded portal flows are implemented. Future content work must correct this
with legal/privacy review where needed.

## Public Site Goals

- Present the clinic and doctor professionally.
- Make booking the clearest primary action.
- Keep Arabic as the default and English as a polished parallel experience.
- Provide essential trust information without overclaiming credentials,
  outcomes, legal approval, or medical advice.
- Keep all public content patient-safe.
- Prepare for dashboard-managed content and approved Figma/design handoff
  without inventing visual design in code.

## Home Page Sections

Final home page content should include:

- clinic/doctor first-viewport identity;
- primary booking CTA;
- secondary doctor/profile CTA;
- short clinic positioning statement;
- service highlights;
- doctor trust/profile preview;
- location/contact preview;
- optional approved gallery preview;
- future authorized cases/reviews showcase only after consent gates;
- emergency/safety note in an appropriate low-friction location;
- legal/privacy footer links.

The first screen must make the clinic identity and booking action obvious on
mobile and desktop.

## Doctor Profile

The final doctor profile should include:

- verified doctor name and title;
- verified specialty;
- verified professional biography;
- verified credentials/memberships/experience;
- approved official portrait if available;
- service areas;
- booking CTA;
- safety disclaimer that the site is not for diagnosis/emergencies.

All credential claims need owner/source verification before publication.

## Services

The services page should include:

- clear service categories;
- active visit types;
- patient-safe descriptions;
- duration when helpful;
- price only when configured as patient-visible;
- booking CTA from relevant visit/service blocks;
- disclaimer that final clinical assessment happens in clinic.

Service copy must not imply guaranteed outcomes, diagnosis, triage, or
treatment automation.

## Booking Entry Points

Booking entry points should exist from:

- header primary CTA;
- home hero;
- home CTA band;
- services page;
- doctor page;
- contact page;
- booking success "book another appointment";
- future approved WhatsApp menu;
- future approved showcase item.

The primary public CTA should consistently lead to the booking flow, not to
account registration.

## Location and Contact

The final contact page should show:

- verified clinic phone;
- verified address;
- approved map/location link or embedded map;
- clinic hours once approved;
- booking CTA;
- WhatsApp availability only after its real status is clear;
- emergency/safety note.

Contact copy must distinguish between administrative contact and emergency
care.

## Gallery

Final gallery requirements:

- dashboard-managed approved public clinic assets;
- no patient/private media unless explicit publication consent exists;
- alt text in Arabic and English;
- approved ordering and active/inactive states;
- safe fallback when no approved gallery items exist;
- visual behavior covered by human/Figma handoff before implementation.

## Authorized Cases and Reviews Showcase

Public showcase is future-gated and must not be implemented as a simple public
media dump.

Requirements:

- draft/preview/publish workflow;
- explicit publication consent before public display;
- consent source/date/expiry/anonymization/identity visibility fields;
- removal workflow for revoked/expired consent;
- staff/admin-only management;
- audit history for create/edit/publish/unpublish/removal;
- no internal notes, IDs, raw messages, private files, or unapproved patient
  identity.

Carousel or media presentation requires approved design and accessibility
handoff.

## Legal and Privacy Entry Points

Legal links must remain available from the footer on all public pages:

- privacy policy;
- terms;
- medical disclaimer;
- WhatsApp policy.

Before launch, legal pages must:

- accurately describe booking and portal data collection;
- accurately state WhatsApp status;
- identify draft/pending/approved/published review status where relevant;
- avoid legal approval claims until approval exists;
- avoid medical advice claims.

## Arabic/English Behavior

- Arabic/default pages use RTL and Arabic copy.
- English pages live under `/en/` and use LTR.
- Language switch should take the user to the equivalent page where possible.
- Bilingual content should preserve meaning, not literal word order.
- Mixed Arabic/English should be limited to names/brand terms where needed.
- Long labels and CTAs need mobile verification in both languages.

## Mobile-First Behavior

Final mobile review must verify:

- clinic identity and booking CTA visible early;
- navigation remains usable without horizontal overflow;
- service cards remain scannable;
- booking entry is reachable from first screen;
- map/contact details are readable;
- legal links are reachable;
- buttons and links have comfortable tap targets;
- Arabic text wraps correctly.

## CTA Hierarchy

Primary CTA:

- Book appointment.

Secondary CTAs:

- Doctor profile.
- Services.
- Contact details.
- Patient portal only as optional follow-up or account entry, not before
  booking.

Tertiary/support CTAs:

- Legal/privacy links.
- WhatsApp placeholder/contact, only with accurate status language.
- Account recovery.

## Design Handoff Requirements

Before public-site visual changes, the human/Figma handoff must cover:

- home page sections and responsive order;
- doctor page content blocks;
- services page card/list behavior;
- contact/map/gallery behavior;
- booking CTA hierarchy;
- legal footer behavior;
- Arabic and English text expansion;
- mobile first-screen behavior;
- focus and error states;
- empty gallery/showcase states;
- asset crop and alt-text requirements;
- what is intentionally unchanged.
