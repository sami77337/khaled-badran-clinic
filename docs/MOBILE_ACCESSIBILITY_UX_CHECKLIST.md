# Mobile Accessibility UX Checklist

This checklist defines final UX review expectations for Dr. Khaled Badran
Clinic. It does not change CSS or visual design.

## Mobile-First Public Site

- Clinic identity is visible early on mobile.
- Primary booking CTA is visible without excessive scrolling.
- Header navigation wraps or collapses without horizontal overflow.
- Language switch is reachable and understandable.
- Home, doctor, services, contact, booking, legal, and portal pages render in
  Arabic/default and English.
- Contact phone/address/map content does not overflow.
- Footer legal links remain reachable.

## Tap Targets

- Primary and secondary CTAs are comfortable to tap.
- Slot buttons are large enough for mobile tapping.
- Form controls are easy to focus.
- Staff/dashboard actions on mobile/tablet are not accidentally tappable
  beside destructive actions.
- Future carousel controls are large enough and reachable.

## Typography and Readability

- Arabic and English text remain readable on small screens.
- Long Arabic labels wrap cleanly.
- Long English labels wrap cleanly.
- Button text does not overflow.
- Status labels do not overlap adjacent content.
- Date/time text remains understandable.
- No content relies only on tiny muted text for critical instructions.

No typography changes are authorized by this checklist; any visual changes need
human/Figma approval.

## Forms

- Labels are visible for every input.
- Required fields are understandable.
- Error messages appear near the relevant field or form summary.
- Error messages are visible after submit.
- Keyboard type is appropriate where implementation supports it.
- Password fields use appropriate browser behavior.
- CSRF-protected forms still submit normally.
- Back/refresh/stale slot behavior is understandable.
- Portal login/register/linking do not reveal account existence.

## Error Visibility

- Form-wide errors use `role="alert"` or equivalent where appropriate.
- Field errors are visually and semantically associated with fields where
  practical.
- Rate-limit errors are calm and actionable.
- Booking unavailable/no slots states have a next action.
- Legal/emergency warnings do not hide actionable errors.

## Horizontal Overflow

- Public pages have no horizontal page overflow.
- Booking slot grids fit mobile.
- Patient appointment lists avoid unusable horizontal scrolling where possible.
- Staff tables may scroll horizontally, but controls must remain usable.
- RTL and LTR layouts both need overflow checks.

## Contrast and Accessibility Review

- Contrast must be reviewed against approved design tokens before launch.
- Focus states must be visible.
- Links must be distinguishable from body text where needed.
- Disabled states must be understandable.
- Status colors must not be the only source of meaning.
- Error states must include text, not color alone.

## Future Authorized Showcase Carousel

If a carousel is implemented later:

- autoplay must be optional and dashboard-controlled only after approval;
- pause/stop controls must be available;
- keyboard navigation must work;
- screen-reader labels must describe controls and current item;
- images/videos must have approved alt text or captions;
- reduced-motion preference must be respected;
- no unapproved patient identity can appear;
- no private media can be loaded from protected/internal storage directly.

## Autoplay Controls

Autoplay, if ever approved, must:

- be off by default unless explicitly approved;
- have a visible pause/stop control;
- respect reduced motion;
- avoid flashing or rapid motion;
- be configurable only within approved bounds.

## Keyboard and Focus Behavior

- Skip link works.
- Header/nav links are reachable by keyboard.
- Booking CTAs and slot buttons are reachable by keyboard.
- Forms can be completed by keyboard.
- Modal/dialog behavior, if added later, traps and restores focus correctly.
- Staff/dashboard action confirmations, if added later, are keyboard usable.

## Reduced Motion

- Existing CSS includes reduced-motion handling.
- Future animations must respect `prefers-reduced-motion`.
- No essential information may depend on animation.

## Screen Reader Labels

- Page language and direction are correct.
- Navigation has labels.
- Booking steps have labels.
- Form labels are programmatically connected where practical.
- Icon-only future controls require accessible names.
- Status labels include text.
- Tables have meaningful headers.
- Public and portal pages avoid raw technical identifiers in accessible text.

## Privacy Accessibility

- Success pages and portal pages must remain no-cache.
- Sensitive fields must not be exposed through hidden visible text or labels.
- Public success should expose only patient-safe details.
- Portal pages must not expose staff-only data to assistive technology.

## Final Review Evidence

Before launch, record review evidence for:

- mobile public home;
- mobile booking flow;
- mobile success page;
- mobile portal login/register/link/detail;
- mobile public legal pages;
- desktop/tablet staff dashboard or staff operations;
- Arabic and English routes;
- keyboard-only navigation;
- reduced-motion behavior;
- no horizontal overflow.
