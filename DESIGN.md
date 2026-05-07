---
version: alpha
name: TokenBank Local Dashboard
description: A readable local audit surface for Private Agent Capacity Network usage.
colors:
  primary: "#075985"
  secondary: "#617086"
  surface: "#ffffff"
  surface-raised: "#f8fafc"
  on-surface: "#1c2430"
  on-surface-muted: "#617086"
  border: "#dfe3ea"
  border-subtle: "#edf0f4"
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: 700
    lineHeight: 1.15
  headline-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 700
    lineHeight: 1.25
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 700
    lineHeight: 1.2
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  page-x: 32px
rounded:
  sm: 4px
  md: 8px
  full: 9999px
components:
  metric-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    border: "1px solid #dfe3ea"
  table:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    border: "1px solid #edf0f4"
---

# TokenBank Design

## Overview

TokenBank Phase 0 is a Private Agent Capacity Network. Its local dashboard is
a work surface for inspecting accounts, usage, route audit evidence, receipts,
and capacity health. It should feel quiet, dense, and operational rather than
marketing-led.

## Colors

Use neutral page and surface colors with a restrained blue accent for links and
actions. Do not use decorative gradients, orbs, or saturated one-note themes.

## Typography

Use compact dashboard typography. Headings identify sections; tables carry the
actual work. Keep letter spacing at zero and avoid viewport-based font sizes.

## Layout

The dashboard uses full-width bands and repeated tables. Cards are reserved for
summary metrics and individual dashboard sections. No nested cards.

## Elevation And Depth

Use borders and subtle surface contrast instead of heavy shadows.

## Shapes

Cards use an 8px radius. Status chips use pill radius. Tables keep stable
column widths and wrap long ids instead of expanding layout.

## Components

- Metrics show count or micros values.
- Tables show accounts, usage, route audit, receipts, and capacity health.
- Privacy boundary appears as a footer band with a clear redacted export link.

## Do's And Don'ts

- Do show local-first and redaction status in the first viewport.
- Do distinguish estimated usage from provider-reported usage.
- Do show hashes and ids for audit evidence.
- Do not render raw credentials, raw prompts, or raw outputs.
- Do not add cloud dashboard framing or marketplace/yield language.
