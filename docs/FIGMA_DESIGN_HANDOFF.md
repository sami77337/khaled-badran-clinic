# Figma Design Handoff

Batch 10 design-governance note for Dr. Khaled Badran Clinic.

## Rule

Codex does not design this project.

Figma is the source of truth for visual design. Visual changes must be designed
and approved in Figma before Codex implements them.

## What Codex May Implement After Figma Approval

After an approved Figma handoff exists, Codex may implement:

- design tokens/classes mapped from approved Figma tokens,
- component structure required by approved Figma components,
- accessibility semantics,
- ARIA labels and landmarks,
- keyboard behavior,
- responsive behavior specified by Figma,
- Arabic/English layout behavior specified by Figma,
- asset wiring for approved icons/images,
- semantic template structure needed to support approved components.

Implementation must preserve security, privacy, routing, CSRF, no-cache, and
access-control requirements.

## What Codex May Not Invent

Codex may not invent or independently change:

- colors,
- spacing systems,
- typography systems,
- visual hierarchy,
- animations,
- decorative elements,
- brand style,
- shadows,
- borders,
- radius systems,
- hover effects,
- layout density,
- illustration style,
- icon style,
- image direction,
- marketing composition.

Codex must not modify `static/css/site.css` for visual design decisions. Any CSS
change must be strictly functional, security-related, or accessibility-related
and documented in the batch notes.

## Required Figma Handoff Checklist

Before Codex implements visual changes, the handoff should include:

- Figma page names,
- approved components,
- component states,
- desktop breakpoint behavior,
- tablet breakpoint behavior,
- mobile breakpoint behavior,
- color tokens,
- typography tokens,
- spacing tokens,
- icon set and usage rules,
- image assets and crop rules,
- Arabic layout behavior,
- English layout behavior,
- right-to-left and left-to-right notes,
- form error states,
- focus states,
- loading states,
- empty states,
- disabled states,
- accessibility notes,
- content overflow rules,
- any approved animation details,
- explicit notes for what must not change.

## Security and Privacy Gates

Figma approval cannot bypass security or privacy requirements.

Visual designs must preserve:

- public booking without login,
- UUID-only public booking success routes,
- no numeric public success URLs,
- staff-only appointment operations,
- CSRF protection,
- no-cache patient portal pages,
- patient appointment ownership filtering,
- account recovery as static/clinic-assisted until a recovery design is
  approved,
- no uploads until private media design exists,
- no medical records until authorization and visibility rules are designed,
- no WhatsApp API/webhooks until consent/logging/security design exists,
- no payments until provider/refund/reconciliation/privacy design exists,
- no medical AI, diagnosis automation, triage automation, or treatment
  automation.

## Batch 10 Status

Design status:

- No visual design work performed by Codex.
- No new visual styling, colors, spacing, typography, animation, shadows,
  borders, cards, or decorative layout were approved or implemented by this
  document.
