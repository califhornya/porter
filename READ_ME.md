# READ_ME.md
### Riftbound Card JSON Generator Utility  
### Standalone Script — Developer Specification

This document defines the full technical specification for a standalone Python utility that converts **Riftbound card images (.webp)** into **normalized CardSpec JSON files** compatible with the rbsim simulator.

This tool does NOT interact with rbsim directly.  
It outputs JSON files that rbsim can load later via its existing `load_cards_json` function.

The ONLY input to this utility is a collection of `.webp` card images.

---

# 1. Purpose

The utility must:

1. Traverse a directory of `.webp` card images.  
2. For each image, extract:
   - card name  
   - card type (Unit, Spell, Gear, Rune, Legend, Battlefield)  
   - subtype(s) / tags  
   - domain  
   - energy cost  
   - power cost (domain + amount)  
   - might (for units)  
   - damage (for spells, when printed)  
   - keywords  
   - rules text  
3. Convert extracted raw data into **CardSpec JSON** following rbsim conventions.  
4. Write one JSON file per card to an output folder.  
5. Provide clean logs and structured error handling.

The utility must not rely on rbsim, only match its schema.

---

# 2. Execution

Command-line example:

```bash
python run_import.py --input ./input_images/ --output ./cards_json/
```

Parameters:

- `--input` : Directory containing `.webp` files.  
- `--output` : Directory where JSON files will be created.

No HTML or other auxiliary inputs are used.

---

# 3. Directory Structure (Suggested)

```text
utility/
    run_import.py
    image_reader.py
    normalizer.py
    effect_parser.py
    keyword_schemas.py
    domain_icons.py
    json_writer.py
    utils.py
    /input_images/
    /cards_json/
```

Codex may reorganize as long as functionality is preserved.

---

# 4. Data Flow Overview

For each `.webp` file:

1. **ImageReader**  
   - Load and process the image using Vision OCR.
   - Extract structured raw fields into a `RawCardData` dictionary.

2. **Normalizer**  
   - Convert `RawCardData` into normalized fields:
     - name  
     - category  
     - domain  
     - cost_energy  
     - cost_power  
     - might  
     - damage  
     - keywords  
     - tags  
     - rules_text  

3. **EffectParser**  
   - Convert rules text + keywords into a list of effect dictionaries following rbsim format.

4. **JSONWriter**  
   - Output `{sanitized_name}.json` into the output directory.

---

# 5. Required Internal Modules

Below is what each module must implement.

---

## 5.1 image_reader.py

Responsibilities:
- Load each `.webp` file.
- Prompt Vision OCR to extract:
  - Name  
  - Card type line  
  - Cost elements (energy, power)  
  - Domain icon  
  - Might or damage values  
  - Keywords  
  - Rules text  
  - Subtypes / tags  

Output a structure:

```python
RawCardData = {
    "name": str,
    "type_line": str,
    "cost_energy": int | None,
    "cost_power_icon": str | None,
    "might": int | None,
    "damage": int | None,
    "domain_icon": str | None,
    "keywords_raw": list[str],
    "rules_text_raw": str,
    "tags_raw": list[str]
}
```

The module does not normalize or interpret semantics.

---

## 5.2 domain_icons.py

Provide static mapping from icon identifiers (as produced by Vision prompts) to Riftbound domains:

```python
ICON_TO_DOMAIN = {
    "red_icon": "FURY",
    "blue_icon": "CALM",
    "purple_icon": "MIND",
    "yellow_icon": "ORDER",
    "green_icon": "BODY",
    "pink_icon": "CHAOS"
}
```

Vision prompts must be designed so that the model returns deterministic identifiers that can be matched in this dictionary (for example: `"red_icon"`, `"blue_icon"`, etc.).

---

## 5.3 keyword_schemas.py

Define the universe of Riftbound keyword abilities and how they map to effect records.

Example:

```python
KEYWORD_SCHEMAS = {
    "DEFLECT": {
        "effect": "deflect",
        "parameters": ["amount", "domain"]
    },
    "BRUTAL": {
        "effect": "brutal",
        "parameters": []
    },
    "ELUSIVE": {
        "effect": "elusive",
        "parameters": []
    },
    "GANKING": {
        "effect": "ganking",
        "parameters": []
    },
    "CHANNEL": {
        "effect": "channel",
        "parameters": ["amount"]
    }
}
```

This file defines how to interpret keywords during normalization and effect parsing.

Codex may extend this list by examining multiple examples and following card standards.

---

## 5.4 normalizer.py

Takes:

- `RawCardData`
- Domain/icon mappings  
- Keyword schemas  

Responsibilities:

1. Clean and normalize `name`.  
2. Parse `type_line`:
   - Determine `"category"` (UNIT, SPELL, GEAR, RUNE, LEGEND, BATTLEFIELD).  
   - Parse subtype(s) → tags.  
3. Normalize:
   - `cost_energy`  
   - `cost_power` (from power icons and/or text near cost)  
   - `might`  
   - `damage`  
4. Determine `domain` from `domain_icon`.  
5. Normalize keyword list (`keywords_raw` → `keywords`).  
6. Normalize `rules_text_raw` → `rules_text`.  
7. Construct a `NormalizedCard`:

```python
NormalizedCard = {
    "name": str,
    "category": str,
    "domain": str | None,
    "cost_energy": int,
    "cost_power": str | None,
    "might": int | None,
    "damage": int | None,
    "keywords": list[str],
    "tags": list[str],
    "rules_text": str
}
```

This structure is consumed by `effect_parser.py`.

---

## 5.5 effect_parser.py

Responsible for translating normalized fields into a list of **effect dictionaries** matching rbsim’s `EffectSpec` format.

Rules:

- Use `keyword_schemas.py` to detect which keywords automatically produce effects.  
- Use simple pattern search in `rules_text` to detect numeric parameters where required (for instance, Deflect amounts, damage values, buff amounts).  
- Do not attempt deep natural-language interpretation.  
- Always return a list (possibly empty):

```python
effects = [
    {"effect": "deflect", "amount": 1, "domain": "FURY"},
    {"effect": "deal_damage", "amount": 2, "target": "opponent"}
]
```

If unknown behaviors appear:
- Log a warning.  
- Add `"raw_rules_text"` to the output JSON so a human can inspect later.

---

## 5.6 json_writer.py

Accepts a fully formed `CardSpec` dictionary and writes:

```text
{output_dir}/{sanitized_name}.json
```

Sanitization rules:
- Replace or strip characters that are invalid in file names.  
- Prefer preserving case and spaces where the filesystem supports it, but avoid problematic characters like `:`, `/`, `\`, `?`, `*`, etc.

---

# 6. JSON Format Requirements

Each output file must follow this structure:

```json
{
  "name": "Pouty Poro",
  "category": "UNIT",
  "domain": "FURY",
  "cost_energy": 2,
  "cost_power": null,
  "might": 2,
  "damage": null,
  "keywords": ["DEFLECT"],
  "tags": ["PORO"],
  "effects": [
    {"effect": "deflect", "amount": 1, "domain": "FURY"}
  ]
}
```

Notes:

- Fields that do not apply should be `null` (or omitted only if absolutely necessary and documented clearly in the code).  
- `effects` is always present as a list (may be empty).  
- The JSON should be pretty-printed with consistent indentation (e.g. 2 or 4 spaces).

---

# 7. Error Handling and Logging

For each card:

- If required data is missing or ambiguous:
  - Log a warning with the card filename and nature of the issue.  
  - Still write a JSON file whenever possible.  
  - Include `"raw_rules_text"` and optionally `"raw_data"` fields to aid manual debugging.  
- The tool must not stop on OCR or parsing errors for a single card; it should continue processing the rest.

At the end, print a short summary, e.g.:

- Total cards processed  
- Successful JSONs  
- Cards with warnings/errors  

---

# 8. Non-Goals

The utility must NOT:

- Implement or simulate card mechanics  
- Validate gameplay or rules interactions  
- Modify or import rbsim as a dependency  
- Connect to any database  
- Perform deep or probabilistic NLP interpretations of rules text  

It is purely a data extraction + normalization + JSON generation tool.

---

# 9. Testing Structure

Codex should include a simple self-test mode or script that:

- Processes 1–3 example `.webp` images placed in `/input_images/`.  
- Prints intermediate `RawCardData`, `NormalizedCard`, and final JSON for at least one sample card.  
- Confirms all required fields are present before writing JSON.  
- Runs without rbsim installed.

Example:

```bash
python run_import.py --input ./input_images/ --output ./cards_json/ --debug-sample 1
```

`--debug-sample` is optional but recommended.

---

# 10. Final Deliverable

Codex must deliver:

1. A fully functional script directory.  
2. All modules described above (or equivalents with clear responsibilities).  
3. Clear instructions embedded in `run_import.py` (help text, `--help`).  
4. A working OCR → normalize → JSON pipeline based solely on `.webp` files as input.  
5. Ready-to-use CLI:

```bash
python run_import.py --input ./input_images/ --output ./cards_json/
```

End of file.
