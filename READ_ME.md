# README_DEV.md  
### Riftbound Card JSON Generator Utility  
### Standalone Script — Developer Specification

This document defines the **full technical specification** for a standalone Python utility that converts **Riftbound card images (.webp)** into **normalized CardSpec JSON files** compatible with the rbsim simulator.

This tool does NOT interact with rbsim directly.  
It outputs JSON files that rbsim can load later via its existing `load_cards_json` function.

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

```
python run_import.py --input ./input_images/ --output ./cards_json/
```

Parameters:

- `--input` : Directory containing `.webp` files.  
- `--output` : Directory where JSON files will be created.  
- `--html` (optional): Path to the downloaded HTML card library file used as fallback data.

---

# 3. Directory Structure (Suggested)

```
utility/
    run_import.py
    image_reader.py
    html_reader.py
    normalizer.py
    effect_parser.py
    keyword_schemas.py
    domain_icons.py
    json_writer.py
    utils.py
    /input_images/
    /cards_json/
```

GPT-Codex may reorganize as long as functionality is preserved.

---

# 4. Data Flow Overview

For each `.webp` file:

1. **ImageReader**  
   - Load and process the image using Vision OCR.
   - Extract structured raw fields into a `RawCardData` dictionary.

2. **HTMLReader (optional fallback)**  
   - Look up the same card by name.  
   - Merge/override missing or ambiguous OCR fields.

3. **Normalizer**  
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

4. **EffectParser**  
   - Convert rules text + keywords into a list of effect dictionaries following rbsim format.

5. **JSONWriter**  
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

```
RawCardData = {
    "name": str,
    "type_line": str,
    "cost_energy": int or None,
    "cost_power_icon": str or None,
    "might": int or None,
    "damage": int or None,
    "domain_icon": str or None,
    "keywords_raw": [str],
    "rules_text_raw": str,
    "tags_raw": [str]
}
```

The module does not normalize or interpret semantics.

---

## 5.2 html_reader.py (optional)

If HTML file is provided:
- Parse card entries from the HTML page.  
- Extract for each card:
  - domain  
  - type  
  - rules text  
  - subtype  
  - keyword list  
- Matches cards by name (case-insensitive).  
- Returns a dictionary keyed by card name.

Normalizer may pass RawCardData to this module to fill missing fields.

---

## 5.3 domain_icons.py

Provide static mapping:

```
ICON_TO_DOMAIN = {
    "red_icon": "FURY",
    "blue_icon": "CALM",
    "purple_icon": "MIND",
    "yellow_icon": "ORDER",
    "green_icon": "BODY",
    "pink_icon": "CHAOS"
}
```

Vision must produce an icon identifier consistent enough to match keys in this dictionary.

---

## 5.4 keyword_schemas.py

Define the universe of Riftbound keyword abilities.

Example:

```
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

Codex must fill this list by examining multiple examples and following card standards.

---

## 5.5 normalizer.py

Takes:

- `RawCardData`
- Optional HTML fallback data  
- Domain/icon mappings  
- Keyword schemas  

Responsibilities:

1. Clean name.  
2. Parse type line:
   - Determine `"category"` (UNIT, SPELL, GEAR, RUNE, LEGEND, BATTLEFIELD).  
   - Parse subtype(s) → tags.  
3. Normalize energy, power, might, damage.  
4. Determine domain from icon, fallback HTML, or rules text.  
5. Normalize keywords.  
6. Normalize rules text.  
7. Construct a **NormalizedCard**:

```
NormalizedCard = {
    "name": str,
    "category": str,
    "domain": str or None,
    "cost_energy": int,
    "cost_power": str or None,
    "might": int or None,
    "damage": int or None,
    "keywords": [...],
    "tags": [...],
    "rules_text": str
}
```

This structure is consumed by EffectParser.

---

## 5.6 effect_parser.py

Responsible for translating normalized fields into a list of **effect dictionaries** matching rbsim’s `EffectSpec` format.

Rules:
- Use `keyword_schemas.py` to detect which keywords automatically produce effects.  
- Use simple pattern search in `rules_text` to detect numeric parameters.  
- Do not attempt deep natural-language interpretation.  
- Always return a list (possibly empty):

```
effects = [
    {"effect": "deflect", "amount": 1, "domain": "FURY"},
    {"effect": "deal_damage", "amount": 2, "target": "opponent"}
]
```

If unknown behaviors appear:
- Log warning.  
- Add `"raw_rules_text"` to output JSON.

---

## 5.7 json_writer.py

Accepts a fully formed `CardSpec` dictionary and writes:

```
{output_dir}/{sanitized_name}.json
```

Sanitization rules:
- Replace spaces with underscores or leave spaces if supported.  
- Remove forbidden filesystem characters.  
- Preserve case (recommended).

---

# 6. JSON Format Requirements

Each output file must follow this exact structure:

```
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

Fields that do not apply should be `null` or omitted only if absolutely necessary.

---

# 7. Error Handling and Logging

For each card:

- If required data is missing:
  - Show a warning  
  - Write JSON with `"raw_rules_text"` included  
  - Continue processing other cards  

The tool must not stop on OCR errors.

---

# 8. Non-Goals

The utility must NOT:

- Implement card mechanics  
- Validate gameplay  
- Modify rbsim  
- Connect to a database  
- Perform deep NLP interpretation of rules text  

It is purely a data extraction + normalization + JSON generation tool.

---

# 9. Testing Structure

Codex should include a self-test script that:

- Processes 1–3 example images  
- Prints intermediate `RawCardData`, `NormalizedCard`, and final JSON  
- Confirms all required fields exist  
- Runs without rbsim installed  

---

# 10. Final Deliverable

Codex must deliver:

1. Fully functional script directory  
2. All modules described above  
3. Clear instructions in `run_import.py`  
4. Fully working OCR → Normalize → JSON pipeline  
5. Ready to use with:
   ```
   python run_import.py --input ./input_images/ --output ./cards_json/
   ```
