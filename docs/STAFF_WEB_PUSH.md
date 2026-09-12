# Staff phone notifications

Issue #54 adds direct standards-based Web Push for active authenticated staff.
On the dashboard overview, choose **تفعيل إشعارات الهاتف / Enable phone
notifications**, then allow the browser permission. Permission is never requested
on page load. Each browser/device opts in separately; the notification language is
the dashboard language used when enabling. To change it, disable and enable again
from the other language. **إيقاف إشعارات الهاتف / Disable phone notifications**
removes the current user's server subscription and unsubscribes that browser.

Android Chrome and installed PWAs use the standard Push API. On iPhone/iPad with
iOS/iPadOS 16.4 or newer, add the site to the Home Screen, launch it from that icon,
sign in as staff, and use the enable control. The site must use HTTPS (localhost
is permitted for development). The dashboard includes the existing web manifest
and approved icons. Delivery while the site is closed is handled by the browser
and OS and remains subject to permission, connectivity and device notification
settings. See [WebKit's platform guidance](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/).

## Required Render environment variables

Set these on the existing Django **web service** in Render's Environment panel;
save and deploy with the normal migration and collectstatic steps. No additional
Render service, queue or hosted notification account is required.

| Variable | Operator value |
| --- | --- |
| `WEB_PUSH_ENABLED` | `true` to enable; omitted/blank/`false` disables all delivery and new subscriptions. |
| `WEB_PUSH_VAPID_PUBLIC_KEY` | The matching P-256 public key: uncompressed 65-byte point, base64url encoded without padding. This value may reach staff browsers. |
| `WEB_PUSH_VAPID_PRIVATE_KEY` | The secret P-256 private scalar: 32 bytes, base64url encoded without padding. Store only as a protected environment value. File paths and PEM values are not accepted. |
| `WEB_PUSH_VAPID_SUBJECT` | A monitored operator contact URI in `mailto:` form, such as `mailto:clinic-operator@example.com`; replace the example with the real contact. |

Generate one VAPID P-256 keypair with trusted local key-generation tooling outside
the repository, enter it directly into Render's protected environment settings,
and retain it in the operator's secret manager. Never put private key material in
Git, documentation, shell history, logs, screenshots or tickets. Do not generate
a new pair on every deployment. There are no actual keys in `.env.example` or
tests; tests generate ephemeral synthetic keys in memory.

All four values are required for delivery. Incomplete, malformed or mismatched
keys fail closed and the dashboard shows unavailable. Apply the new table with
`python manage.py migrate --noinput` and publish static files using
`python manage.py collectstatic --noinput`. Keep the existing HTTPS, staff login,
database, CSRF and secure-cookie settings. No existing credentials change.

## Event, privacy and delivery contract

Only these existing creation services schedule delivery inside their transaction:

- Registered patient consultation: `create_consultation`.
- Verified guest consultation: `create_guest_consultation`, after the verified
  grant is checked and attached to the saved consultation.
- Public appointment: `create_public_appointment`, after its history/audit writes.

Callbacks run after the **outermost successful database commit**. A rollback
discards the callback. No model signals are used; replies, read/unread updates,
profile edits, status changes, navigation and routine CRUD remain silent. Existing
in-site consultation notifications and badge counts are unchanged.

The encrypted JSON contains exactly `event` (`new-consultation` or `new-booking`)
and `language` (`ar` or `en`). No patient identifiers, names, phone numbers, text,
medical content, booking notes, attachment information or dynamic URLs are sent.
The worker supplies only this fixed copy:

| Category | Arabic title / body | English title / body |
| --- | --- | --- |
| Consultation | استشارة جديدة / لديك استشارة جديدة في العيادة. | New consultation / You have a new consultation at the clinic. |
| Booking | موعد جديد / تم حجز موعد جديد عبر الموقع. | New appointment / A new appointment has been booked through the website. |

Both the provider `Topic` and browser notification `tag` are stable:
`kbc-new-consultation` and `kbc-new-booking`. Pending pushes collapse by category;
displayed notifications replace the earlier category notification where supported
by the platform. `requireInteraction` and `renotify` are false. There are no custom
sounds, vibration patterns, action buttons or app badge changes.

The root-scoped worker at `/sw.js` uses no offline cache. Taps navigate/focus an
existing staff window, or open `/dashboard/consultations/` or `/staff/appointments/`
with `?lang=en` for English. Destinations retain their existing staff checks and
normal login/next flow. Incoming notification URLs/text/options are ignored.

Subscriptions are private credentials, associated with the authenticated user,
unique per endpoint, and capped at ten devices per user. Another user cannot claim,
inspect or remove that user's subscription. JSON writes use POST and Django CSRF.
The status lookup also uses a CSRF-protected POST so endpoint credentials never
appear in query strings. These rows are intentionally absent from Django admin.
Inactive users and users whose staff access was revoked receive no delivery;
deleting the user cascades subscriptions. Signing out does not cancel an explicit
device opt-in; use the disable control before leaving a shared device.

Outbound endpoints are restricted to `fcm.googleapis.com`, `web.push.apple.com`
and `updates.push.services.mozilla.com`, using HTTPS with no credentials, custom
port or redirects. These are the browsers' native Web Push transports, not an
integration with a Firebase SDK/account, OneSignal, Meta or a hosted notification
product. `pywebpush==2.5.0` is the sole added direct dependency; its required
cryptography/transport dependencies are installed transitively. See the
[upstream library documentation](https://github.com/web-push-libs/pywebpush).

Delivery is synchronous **after commit**, best effort, with a three-second HTTP
timeout per subscription, a one-hour provider TTL, and no application retries or
durable outbox. Each opted-in device adds an outbound request to submission
latency; this deliberately small implementation targets the clinic's staff phones.
A failed device does not prevent attempts to other devices, and delivery failures
never roll back the saved consultation/appointment or replace its success response.
404/410 subscriptions are deleted unless refreshed during delivery; transient
failures retain them. Push is a prompt to check the dashboard, not a delivery
guarantee or unread counter.

The app never logs endpoint/auth/p256dh/private-key/payload/provider-body data.
The configured log filter suppresses transport logs during delivery, subscription
SQL debug records and API request error reports. Keep external APM/proxy body
capture disabled for these endpoints; do not enable third-party HTTP wire tracing.

## Validation and operator acceptance

Run `python manage.py test apps.notifications` for API ownership/CSRF validation,
commit/rollback/provider-failure tests, AR/EN copy, real Chromium layout checks and
Node worker/control tests. Run the complete repository checks:

```text
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py test --noinput
python -m pip check
python -m pip_audit -r requirements.txt --progress-spinner off
```

The browser tests require Node and Chromium; `KBC_QA_BROWSER` can specify the
browser executable. They use isolated synthetic pages and a temporary profile.
No automated test contacts a push provider or requires production keys.

After deploying and configuring Render, verify on an Android phone and an iOS
Home Screen app: page load does not prompt; explicit enable does; close the site,
submit one synthetic registered consultation, verified guest consultation and
public appointment; confirm only neutral AR/EN copy; repeat a category and check
replacement; tap while signed out and confirm staff login is required; disable
and verify no subsequent delivery. Read/unread/reply/status actions must stay
silent. Automated browser tests cannot prove delivery to a physical phone or OS
lock-screen rendering.

To pause rollout, set `WEB_PUSH_ENABLED=false`; existing subscriptions can still
be removed through the disable action. Key rotation requires affected staff to
disable and enable again. No consultation or booking data changes are needed.
