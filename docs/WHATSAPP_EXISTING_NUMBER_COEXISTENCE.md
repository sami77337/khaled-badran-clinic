# Existing Clinic WhatsApp Number — Onboarding Gate

The owner-approved clinic number is already in active WhatsApp use. Production
onboarding must therefore preserve day-to-day clinic access to that number.

## Required rule

Do **not** remove, deregister, or migrate the current clinic number away from the
WhatsApp Business app as an incidental setup step.

Before enabling Cloud API for the real clinic number, confirm the Meta-supported
existing-number / WhatsApp Business App coexistence onboarding path is available
for the clinic account and region. The target operational behavior is:

- the clinic team keeps using the existing WhatsApp Business app for human
  conversations;
- Cloud API handles the approved automated menu, OTP, booking notifications,
  consultation notifications, and reminders;
- `التحدث مع العيادة` hands control to the clinic's existing human WhatsApp
  workflow rather than creating a new medical inbox inside Django.

If coexistence is not available for the clinic's Meta account, stop onboarding
before changing the existing number. The owner must then choose between a
separate API number or another approved onboarding/provider route. Do not make
that choice automatically.

## Live verification

Before production go-live, verify with the real account that:

1. the existing WhatsApp Business app remains usable;
2. inbound messages reach the Cloud API webhook;
3. automated replies appear correctly to the patient;
4. after selecting `التحدث مع العيادة`, normal patient messages receive no bot
   loop and can be answered by clinic staff through the retained human channel;
5. returning to `القائمة` or `ابدأ` resumes the automated menu;
6. no existing clinic chat history is intentionally deleted as part of setup.

No account credentials, phone identifiers, access tokens, or chat history belong
in this document or in Git.
