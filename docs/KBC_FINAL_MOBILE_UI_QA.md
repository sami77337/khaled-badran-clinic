# Final mobile picker owner QA

Physical Android status: **PENDING OWNER VERIFICATION**. Automated Chromium
layout checks and synthetic viewport changes do not establish physical keyboard
behavior. Use the final local commit on the approved branch.

## Automated verification — 2026-09-06

Resumed the staged mobile picker batch from `f923ef3` on
`feat/batch-17-01-public-ui-foundation`. The Portal menu now stays in document
flow throughout the fixed-header breakpoint, including landscape. In very
short viewports, the whole menu can scroll inside the available space. Closing
the menu or crossing to desktop clears the temporary height constraints.

Verified locally using Python 3.14.2, Django 5.2.15, Node 24.16.0, and headless
Chrome 152.0.7977.76 with isolated test database fixtures:

- `python manage.py check`: passed, no issues.
- `python manage.py makemigrations --check --dry-run`: no changes detected.
- `python manage.py deployment_smoke`: 16 passes, zero failures or strict
  blockers; four expected local-development warnings for DEBUG, SQLite,
  LocMemCache, and disabled HTTPS redirect.
- `node apps/booking/js_tests/phone_picker_runtime_test.js static/js/booking.js`:
  passed.
- `node apps/booking/js_tests/phone_picker_runtime_test.js static/js/auth-login.js`:
  passed.
- `python manage.py test apps.patients.test_phone_picker_layout --verbosity 2`:
  passed all 60 mobile/form cases and 28 Portal landscape cases. Coverage
  includes AR/EN, computed Login style parity, resolved style tokens, surrounding
  form isolation, compact checkbox with a 44px label target, field errors,
  document flow, fixed-header/navigation clearance, filtering, scrolling,
  selection focus, menu dismissal, and E.164 form-data serialization.
- `python manage.py test --exclude-tag=browser --verbosity 1`: all 741 tests
  passed in 201.970 seconds, including the rendered browser test. No tests
  currently use the `browser` tag, so the exclusion did not omit any tests.
- Git whitespace checks passed for the complete batch.

The landscape cases cover 640/667/720/740/800/844/900px widths at 360px and
260px heights, including reaching and selecting the last country. These are
automated browser results; the physical Android matrix below remains pending.
Public Booking is covered here by its runtime regression test, not by the
rendered-page matrix. No device acceptance or production release is claimed.

## Device matrix

Run every surface and every state below for each row. Record device, Android
version, browser/version, orientation, approximate CSS viewport width, language,
PASS/FAIL, and screenshots for any discrepancy.

| Width / orientation | Language / direction | Surfaces | States |
| --- | --- | --- | --- |
| Narrow portrait, about 360px | Arabic / RTL | 1–5 | A–E |
| Narrow portrait, about 360px | English / LTR | 1–5 | A–E |
| Normal portrait, about 390–412px | Arabic / RTL | 1–5 | A–E |
| Normal portrait, about 390–412px | English / LTR | 1–5 | A–E |
| Phone landscape | Arabic / RTL | 1–5 | A–E |
| Phone landscape | English / LTR | 1–5 | A–E |

Landscape browser checks additionally cover widths 640, 667, 720, 740, 800,
844, and 900px. On the physical device, rotate with the menu already open,
repeat with search focused, then rotate back to portrait.

## Surfaces

1. **Login: approved reference.** Open `/login/` or `/en/login/`, select Patient.
2. **Link Appointment.** Sign in to the test patient account, open Appointments,
   then Link Appointment.
3. **Change Account Phone.** Open Account, then Change Password; scroll to the
   separate Change Account Phone form.
4. **Registration: regression only.** Open `/portal/register/` or
   `/en/portal/register/` while signed out.
5. **Public Booking: regression only.** While signed out, choose a visit type
   and available appointment slot, then open the patient-details step. Exercise
   both primary phone and separate WhatsApp phone when enabled.

Compare 2 and 3 against 1 at the same orientation, browser zoom, country, and
language. Keep Registration and Public Booking's established appearance.

## States and exact checks

### A — Closed

1. Dismiss the keyboard. Select Jordan and leave the picker closed.
2. Compare Login, Link Appointment, and Change Account Phone: trigger thickness,
   trigger/number proportions, single outer phone-row border, separator, radius,
   padding, gap, flag, dial code, chevron, input baseline, and typography.
3. The phone row stays LTR in both languages: trigger on the left, number on the
   right. Arabic menu text follows RTL; English follows LTR. No horizontal page
   scrolling or clipped content.
4. On Change Account Phone, the propagation checkbox box stays about 1.1rem;
   tap its text and surrounding label to confirm a comfortable target of at
   least about 44px. The checkbox itself must not become 44px square.

### B — Open, keyboard closed

1. Tap the country trigger using a finger. The menu opens; search is not
   automatically focused and the keyboard remains closed.
2. Compare the solid menu background, visible border, radius, shadow, padding,
   search border/background, label, country font, row density, and alignment
   against Login. PASS requires matching visual language, not merely no overlap.
3. Confirm the menu occupies document flow and pushes later content downward.
   On Link Appointment, the appointment code remains above the phone field;
   errors and actions remain readable and separate. On Change Account Phone,
   current password remains above, while propagation checkbox, errors, and
   WhatsApp action remain below. Check any visible verification form too.
4. Scroll the page. The menu and following content must remain reachable without
   painting over the fixed header or bottom navigation.

### C — Search focused, keyboard open

1. Deliberately tap inside search. It focuses and the Android keyboard opens.
2. Type `Jordan`, `JO`, `962`, and an Arabic country name in separate searches.
   Confirm filtering, readable names/codes, correct text direction, and the
   existing focus treatment. Clear each search before the next.
3. Check while the keyboard opens, closes, and changes height, including browser
   toolbar movement. The list must stay scrollable and clear of Portal chrome.
4. In very short landscape space, the Portal menu may itself scroll to expose
   search and options. Verify both can be reached; no option may be trapped
   behind navigation. Normal-size menus retain Login's presentation.

### D — Options scrolled near the bottom

1. Clear search and swipe within the options to the final countries. Repeat
   with keyboard closed and open. Scroll the menu itself if the viewport is
   too short for search and an option together.
2. Confirm the final option is visible, its flag/name/code align, long names wrap
   without horizontal overflow, and the option can be tapped above navigation.
3. Rotate to landscape and back with the menu open. Confirm fitting updates and
   the page, list, and later fields remain usable.

### E — Country selected, menu closed

1. Tap a visible country near the bottom. The menu closes, `flag / dial code`
   update, and focus returns to the trigger without forcing the phone keyboard
   open or causing an unexpected focus-driven page jump.
2. Reopen, search for Canada, and select it. Check the flag/code update again.
   Tap the phone input intentionally; verify normal phone entry remains usable.
3. Restore Jordan. The picker shows `7XXXXXXXX`; a local `07…` value normalizes
   without a duplicated domestic prefix or country code.
4. Use an owner-controlled test account/appointment for actual submissions.
   Login with the known Jordan number and password. Link the matching test
   appointment. Complete account-phone verification only with the intended
   test number. Check Registration and Public Booking with test data.
5. In browser remote debugging, verify the native POST's phone field is E.164.
   Example: Jordan `791234567` becomes `+962791234567`; Canada `4165550123`
   becomes `+14165550123`. Verify the same contract for `phone`, `new_phone`,
   and the Booking contact/WhatsApp fields as applicable.
6. Submit invalid/empty test values to display validation errors. Reopen the
   picker and repeat B–D; errors, checkbox, actions, and navigation remain clear.

## Acceptance record

Mark each matrix row only after all five states pass on all applicable pickers.
For Login versus Portal, unexplained differences in thickness, menu surface,
search chrome, option density, radius, shadow, alignment, or spacing are FAIL.
Portal's necessary viewport clearance and short-height scrolling are permitted.
Record physical Android results separately from automated test results.
