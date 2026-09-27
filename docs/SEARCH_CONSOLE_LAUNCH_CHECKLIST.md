# Google Search Console Launch Checklist

This checklist covers the technical indexing launch for `https://drkhaledbadran.com`.
It does not authorize marketing copy changes, paid ads, or changes to private/authenticated routes.

## Before submission

- Confirm `https://drkhaledbadran.com/` returns the intended public site.
- Confirm public canonical URLs use `https://drkhaledbadran.com` even when the same application is reached through the Render hostname.
- Confirm `https://drkhaledbadran.com/robots.txt` references `https://drkhaledbadran.com/sitemap.xml`.
- Confirm the sitemap contains only intended public routes and does not contain patient portal, dashboard, auth, or private-media URLs.
- Confirm private/auth/dashboard/patient templates retain their existing `noindex` directives.

## Search Console

1. Add a **Domain property** for `drkhaledbadran.com`.
2. Verify ownership through the DNS record requested by Google Search Console.
3. Submit `https://drkhaledbadran.com/sitemap.xml`.
4. Request indexing for the main public pages:
   - homepage
   - doctor
   - services
   - contact
   - reviews
5. After Google recrawls the site, inspect those URLs and verify the Google-selected canonical is on `https://drkhaledbadran.com`, not the Render hostname.

Do not paste DNS credentials, provider tokens, patient data, or private application URLs into repository evidence.
