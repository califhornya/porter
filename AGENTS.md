# Optional Improvements for the Riftbound Card Extractor

This document describes optional enhancements that can improve accuracy, consistency, cost-efficiency, and long-term maintainability of the **porter** card-extraction tool and the overall Riftbound card-data pipeline.

These improvements are *not* required for functionality but provide a strong foundation for production-grade use.

---

# 1. Normalizing Tags and Keywords

### Problem
Card images may use inconsistent casing or phrasing such as:
- "EQUIPMENT" vs "Equipment"
- "gear" vs "GEAR"
- "Legend" vs "legend"

### Improvement
Implement canonical normalization rules after extraction.

Example:
```
tags = [tag.upper() for tag in tags]
keywords = [kw.upper() for kw in keywords]
```

Or maintain a mapping table:

```
EQUIPMENT → EQUIPMENT
GEAR → GEAR
UNIT → UNIT
LEGEND → LEGEND
TRIBE NAME → TRIBE NAME
```

This ensures strict consistency across the dataset.

---

# 2. Normalizing Effect Names

### Problem
LLM-extracted effect names will be correct but may vary slightly:
- `score_point`
- `score_vp`
- `gain_point`

### Improvement
Define a canonical effect namespace:

```
deal_damage
buff_might
draw_cards
attach
score_vp
trigger_on_hold
trigger_on_conquer
```

Then map extracted effects through a normalization layer:
```
if effect == "score_point":
    effect = "score_vp"
```

This keeps data machine-friendly and future-proof.

---

# 3. Auto-Compress Images Before Vision Requests

### Problem
Large PNG/webp source files increase cost. Vision models charge partially based on pixel count.

### Improvement
Downscale and compress images before sending:

```
img.thumbnail((1024, 1024))
img.save(buf, format="JPEG", quality=85)
```

This reduces cost significantly with negligible accuracy loss.

---

# 4. Add Schema Versioning

### Problem
As card definitions evolve, older JSON files may become incompatible.

### Improvement
Add a field:
```
"schema_version": 1
```

This enables backward compatibility, migration scripts, and data auditing.

---

# 5. Add a Post-Processor Pass

A post-processor can clean and finalize the JSON:
- normalize types
- unify rules_text formatting
- fix line breaks
- collapse whitespace
- ensure parameters are consistent
- reorder fields predictably

This produces publication-grade JSON.

---

# 6. Add Tests

Add a `tests/` folder with:
- sample card images
- expected JSON outputs
- snapshot tests

Use pytest:
```
uv run pytest
```

This catches accidental regressions.

---

# 7. Add a Dry-Run Mode

Useful for debugging:
```
uv run porter card.webp --dry-run
```

Prints extracted JSON without writing a file.

---

# 8. Add Error-Recovery Pass

If the LLM returns malformed JSON:
1. Attempt parsing.
2. On failure, send back to GPT with a repair prompt.
3. Validate again.

This eliminates rare JSON formatting issues.

---

# 9. Implement Domain-Specific Parsing Rules

Define patterns for Riftbound mechanics:
- "When I hold" → `trigger_on_hold`
- "score X point(s)" → `score_vp`
- "Equip" → `attach`
- "+N armor" → `stats.armor = N`

This enables auto-structured effects.

---

# 10. Maintain a Registry of Known Cards

Example folder:
```
cards/
    Trinity_Force.json
    Ahri_Inquisitive.json
```

Add a batch runner:
```
uv run porter --all cards_in/ --out cards/
```

---

# 11. Logging

Add logs including:
- timestamp
- model used
- tokens consumed
- estimated cost
- extraction warnings

---

# 12. Duplicate Detection via Hashing

Add a SHA-256 hash of the image:
```
"image_hash": "aab4e7f..."
```

Avoids double processing of identical cards.

---

# 13. Stable Field Ordering

Ensure predictable key ordering when writing JSON.

---

# 14. Model Flexibility

Allow switching models:
```
--model gpt-4o
--model gpt-4.1
--model o1
```

This future-proofs the pipeline.

---

These improvements will:
- increase data consistency
- reduce costs
- improve extraction robustness
- support large-scale card ingestion