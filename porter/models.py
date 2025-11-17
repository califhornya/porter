from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class PowerCostItem(BaseModel):
    """A single power icon requirement."""

    domain: str
    amount: int = Field(..., ge=1)


class CardCost(BaseModel):
    """Energy and power cost of a card.

    - energy: generic energy cost (top-left number). Can be omitted for Legends.
    - power: list of domain requirements extracted directly from the power icons.
    """

    energy: Optional[int] = Field(default=None, ge=0)
    power: List[PowerCostItem] = Field(default_factory=list)


class CardStats(BaseModel):
    """Combat stats.

    - might: main attack stat for units, or null otherwise.
    - damage / armor: optional extra stats; null if not present.
    """

    might: Optional[int] = None
    damage: Optional[int] = None
    armor: Optional[int] = None


class CardEffect(BaseModel):
    """Normalized effect description."""

    effect: str
    params: Dict[str, Any] = Field(default_factory=dict)


class CardData(BaseModel):
    """Canonical representation of a single Riftbound card."""

    schema_version: int = Field(default=1, ge=1)

    # Name, including champion subtitle if present (e.g. "Volibear Furious").
    name: str

    # Card classification
    supertypes: List[str] = Field(default_factory=list)
    type: str  # UNIT | SPELL | GEAR | RUNE | LEGEND | BATTLEFIELD

    # Domain information
    domain: Optional[str] = None  # primary domain (or None)
    domains: List[str] = Field(default_factory=list)  # all domains (0–2, typically)

    # Cost and stats
    cost: CardCost
    stats: CardStats

    # Gameplay labels
    keywords: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    # Rules text and effects
    rules_text: str
    effects: List[CardEffect] = Field(default_factory=list)

    # Extra info
    flavor: Optional[str] = None
    artist: Optional[str] = None
    card_id: Optional[str] = None

    @model_validator(mode="after")
    def _validate_cost(self) -> "CardData":
        if self.type != "LEGEND" and self.cost.energy is None:
            raise ValueError("energy cost is required for non-legend cards")

        return self
