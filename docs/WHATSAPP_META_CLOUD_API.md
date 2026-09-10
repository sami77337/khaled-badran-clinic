# Meta WhatsApp Cloud API - Production Setup

The current implementation and operator instructions are maintained in
[Meta WhatsApp Cloud API operations](WHATSAPP_META_SETUP.md).
Use that guide for environment setting names, the five required templates,
webhook routing, reminder scheduling, logging, and live acceptance.

Before onboarding the active clinic number, follow the
[existing-number coexistence requirement](WHATSAPP_EXISTING_NUMBER_COEXISTENCE.md).
The clinic must retain its existing WhatsApp Business app access and chat history.

The former setup examples on this page described the initial PR implementation.
They are superseded by the tested adapter and canonical setup guide. In particular,
the current booking/reminder templates use date and time only, and the Arabic
location action uses its own template. Do not configure templates or callable
paths using an older revision of this page.

[Synthetic validation evidence](WHATSAPP_META_VALIDATION.md) records the local
checks and the distinction between repository completion and live Meta activation.
