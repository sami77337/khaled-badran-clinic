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

## Future Work

Before production:

- Run Django deploy checks.
- Review HTTPS/security settings.
- Review backup policy.
- Review access permissions.
- Review privacy policy and terms.
