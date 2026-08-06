# Block Mapping Rules

> LLM decision heuristics for identifying block types from headings, content patterns, and visual layout. Read this in Step 2 before writing `analyst_mapping.json`.

## How to Use This Reference

Read this file in Step 2 before writing `analyst_mapping.json`. These rules help you decide which template slot each section of the source page should map to.

## General Principles

1. **Heading text is the strongest signal.** A section headed "Why Choose Us" or "Our Benefits" strongly indicates a features/benefits slot.
2. **Content pattern is the second signal.** Icon + title + description triples suggest a feature grid. A quote with attribution suggests a testimonial.
3. **Visual layout from the screenshot confirms or overrides.** Three columns of cards in the screenshot confirm a feature grid even if the heading is generic.
4. **When uncertain, prefer `about` (generic body) over forcing a structured slot.** A bad fit in `features` is worse than a good fit in `about`.
5. **Exact text only.** Never paraphrase or rewrite source content unless the slot schema explicitly permits adaptation.
6. **Image references must use `__IMG_*__` IDs.** Never write real filesystem paths. The mapping lives in `.run_state.json` → `step1.image_map`.

## Slot-Specific Heuristics

### hero
- Look for: first prominent heading on the page, usually `h1`, paired with a large hero image
- Content: main value proposition or tagline
- Image: largest/first image on the page, or the screenshot's most visually prominent image

### about
- Look for: paragraph(s) of descriptive text, often following the hero
- Content: company/service description, mission statement
- May be spread across multiple sections — combine if semantically cohesive

### features
- Look for: repeating pattern of icon/emoji + short title + description
- Visual clue: grid or card layout in the screenshot
- Headings: "Features", "Benefits", "Why Us", "What We Offer", "Services"
- Max 6 items; prioritize the most impactful

### testimonials
- Look for: quoted text with attribution (name, role, company)
- Visual clue: quote marks, avatar images, card layout
- Headings: "Testimonials", "What Our Clients Say", "Reviews"
- Max 3 items

### cta
- Look for: action-oriented text with a clear button/link
- Visual clue: prominent button or form in the screenshot
- Headings: "Get Started", "Contact Us", "Request a Demo", "Let's Talk"
- Extract button text and URL verbatim

### stats
- Look for: large numbers with short labels
- Visual clue: horizontal bar of number + label pairs
- Headings: "By the Numbers", "Our Impact", "Results"
- Extract values as strings (preserve formatting like "10K+" or "98%")

### contact
- Look for: email addresses, phone numbers, physical addresses
- Visual clue: contact section, often in or near the page footer
- Headings: "Contact", "Get in Touch", "Visit Us"

## Edge Cases

### Section spans multiple DOM elements
If a logical section is split across multiple `<section>` or `<div>` elements, combine them into one slot entry. Use the screenshot to confirm visual grouping.

### No matching slot for a section
If a section doesn't fit any template slot, skip it. The portfolio PDF doesn't need to include every piece of content — it's a curated selection.

### Multiple candidates for one slot
If multiple sections could fill the same slot (e.g., two feature grids), choose the one that best represents the page. Quality over quantity.

### Page has no extractable blocks
If `content.md` is very short or has no clear sections, you may only be able to fill `hero` and `about` from the available content. This is acceptable — the template gracefully handles missing optional slots.
