# Security Notes

## Current Repository Visibility

The repository is currently public. Until it is private, do not commit:

- API keys.
- WhatsApp tokens.
- Database passwords.
- Real patient data.
- Clinic internal documents that should not be public.
- Medical uploads or reports.

## Required Practices

- Use .env locally.
- Keep .env out of Git.
- Use .env.example only for placeholder names.
- Use private media storage for patient files.
- Do not expose patient files through public URLs.
- Keep WhatsApp credentials in environment variables only.

## Private Consultation Upload Format Checks

New **registered and guest consultation attachments** and **clinical audio
replies** must match an allowlisted filename extension, declared MIME,
bounded byte length, and a minimal container/header signature before private
storage. The check reads only the initial 4 KiB, verifies stream length and
restores the original file pointer. Unreadable or unseekable uploads fail closed.
Validation failures do not log raw bytes, patient names, or storage paths.

This is a targeted content-type spoofing mitigation, **not** antivirus, full
decoder validation, media transcoding, or proof that a polyglot cannot exist.
No existing stored records, public-case media, private medical media outside
consultations, or historical patient files are scanned or modified by this
change. Separate private RecordMedia upload checks and comprehensive security
retesting remain independently scoped.

## Future Work

Before production:

- Run Django deploy checks.
- Review HTTPS/security settings.
- Review backup policy.
- Review access permissions.
- Review privacy policy and terms.
