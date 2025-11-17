# DEV.md — Power Cost System Upgrade

## Purpose

Riftbound power costs can contain:
- Multiple power icons
- Quantities (e.g. 2 BODY power)
- Mixed domains (e.g. FURY + CHAOS)

The current schema only supports a single string (`"BODY"` or `null"`).  
The system must be upgraded to support a structured, accurate representation.

---

# 1. Update JSON Schema (SYSTEM_PROMPT and prompts.py)

Replace the old section:

```
"cost": {
  "energy": integer,
  "power": "FURY | CALM | MIND | BODY | CHAOS | ORDER | null"
}
```

With:

```
"cost": {
  "energy": integer,
  "power": [
    {
      "domain": "FURY | CALM | MIND | BODY | CHAOS | ORDER",
      "amount": integer
    }
  ]
}
```

New cost rules:

```
- "cost.energy" is the number in the top-left corner.

- "cost.power" is a list of power icons extracted exactly as shown.
  Each entry in the list MUST contain:
    - "domain": the icon's domain
    - "amount": how many times that domain appears

- If a card has no power icons, "cost.power" = [].

- If the card shows two identical domain icons (e.g. BODY BODY),
  return one item with:
    { "domain": "BODY", "amount": 2 }

- If the card shows mixed domains (e.g. FURY + CHAOS),
  return two items, in visual left-to-right order:
    [
      { "domain": "FURY", "amount": 1 },
      { "domain": "CHAOS", "amount": 1 }
    ]
```

---

# 2. Update Pydantic Models (models.py and duplicates)

Add:

```
class PowerCostItem(BaseModel):
    domain: str
    amount: int = Field(..., ge=1)
```

Replace old CardCost:

```
class CardCost(BaseModel):
    energy: int = Field(..., ge=0)
    power: Optional[str] = None
```

With:

```
class CardCost(BaseModel):
    energy: int = Field(..., ge=0)
    power: List[PowerCostItem] = Field(default_factory=list)
```

---

# 3. Update SYSTEM_PROMPT text

Replace all:
```
"power": "FURY | CALM | MIND | BODY | CHAOS | ORDER | null"
```

With:
```
"power": [
  {
    "domain": "FURY | CALM | MIND | BODY | CHAOS | ORDER",
    "amount": integer
  }
]
```

Add the new cost rules.

---

# 4. Update post_process.py

Remove assumptions that power is:
- a string
- null for multi-domain

Ensure:
- `power` remains a list
- Each item's `domain` is canonicalized with DOMAIN_SYNONYMS
- Do NOT collapse or rewrite entries

---

# 5. No changes to domain identification

Domains remain independent from power costs.  
Do not infer domains from power.

---

# 6. Update example JSON files

Convert old form:
```
"power": "BODY"
```

To new form:
```
"power": [
  { "domain": "BODY", "amount": 1 }
]
```

And:
```
"power": null
```

Becomes:
```
"power": []
```

---

# 7. Migration utility (optional)

Convert old JSON to new schema:
- If power is string -> list with amount 1
- If power is null -> empty list

---

# 8. Summary of required modifications

1. Update SYSTEM_PROMPT in:
   - prompts.py
   - extract_riftbound_card.py
2. Update CardCost model in all files
3. Add PowerCostItem model
4. Update post_process.py to accept lists
5. Canonicalize domain inside each power item
6. Update JSON examples everywhere
