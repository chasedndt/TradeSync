# TradeSync Identity

## Canonical mark

The canonical TradeSync mark for the current product generation is:

![TradeSync TS mark](assets/tradesync-mark.png)

File: `docs/brand/assets/tradesync-mark.png`

Format: 1254 × 1254 RGBA PNG

Subject: white interlocking forward-leaning `TS` monogram

Background: transparent

The product UI consumes the same asset from `services/cockpit-ui/public/brand/tradesync-mark.png`. The documentation copy is the canonical master; the public copy is a build/runtime consumer.

## Meaning

- `T` and `S` are joined to express synchronized market observation and action.
- The forward lean suggests speed without presenting the system as reckless or autonomous.
- White is the primary mark color so the symbol works across the dark navy operator surfaces.
- The mark has no trading arrow, coin, chain, or exchange logo, keeping it usable when the product expands beyond one screen or notification channel.

## Usage rules

- Use the mark on deep navy (`#07111f` to `#0d1928`) or another high-contrast background.
- Keep clear space equal to roughly one quarter of the mark’s visible width.
- Do not stretch, rotate, add shadows/gradients, recolor individual letter segments, or place other letters inside the mark.
- Do not recreate the mark with a text `TS` span. Use the canonical asset.
- At tiny sizes, test 24 px and 32 px legibility before release.
- A future SVG/vector master requires a traced asset, visual comparison, and explicit replacement decision; a manually redrawn approximation is not automatically canonical.

## Provenance

The mark was generated with the built-in image-generation workflow using the selected Mission Control direction as a reference. It was generated as a white flat mark on a removable green background, converted locally to RGBA transparency, and validated for transparent corners and non-empty subject bounds.

Final generation prompt:

> Create a refined, vector-friendly interlocking capital T and S monogram based on the selected dashboard’s small italic TS direction. Produce one compact white mark with forward motion, balanced negative space, clean geometric edges, and legibility at 24 px. Use one symbol only, no words, no tagline, no 3D, gradients, shadows, texture, mockup, watermark, or extra decoration.
