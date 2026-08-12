# ============================================================
# FLIPFLOW™ API
# Reseller Intelligence & Opportunity Scoring Engine
# ============================================================

from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum


app = FastAPI(
    title="FLIPFLOW™ API",
    description="Reseller Intelligence and Opportunity Scoring Engine",
    version="1.0.0",
)


# ============================================================
# HELPERS
# ============================================================

def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def pct(value: float) -> float:
    return round(clamp(value), 1)


# ============================================================
# ENUMS
# ============================================================

class Condition(str, Enum):
    NEW = "new"
    LIKE_NEW = "like_new"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


class Verdict(str, Enum):
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    NEGOTIATE = "NEGOTIATE"
    CAUTION = "CAUTION"
    PASS = "PASS"


# ============================================================
# MODELS
# ============================================================

class FlipRequest(BaseModel):
    title: str = Field(..., min_length=2)
    asking_price: float = Field(..., ge=0)
    estimated_resale_price: float = Field(..., ge=0)

    condition: Condition = Condition.UNKNOWN

    estimated_fees: float = Field(0, ge=0)
    estimated_shipping: float = Field(0, ge=0)
    estimated_repairs: float = Field(0, ge=0)
    other_costs: float = Field(0, ge=0)

    demand_score: float = Field(50, ge=0, le=100)
    sell_speed_score: float = Field(50, ge=0, le=100)
    confidence_score: float = Field(50, ge=0, le=100)

    notes: Optional[str] = None


class FlipAnalysis(BaseModel):
    title: str
    asking_price: float
    resale_price: float

    total_cost: float
    projected_profit: float
    roi_percent: float
    margin_percent: float

    profit_score: float
    roi_score: float
    demand_score: float
    sell_speed_score: float
    confidence_score: float
    condition_score: float

    opportunity_score: float
    verdict: Verdict
    max_buy_price: float

    reasons: List[str]
    risk_flags: List[str]


# ============================================================
# SCORING
# ============================================================

CONDITION_SCORES: Dict[Condition, float] = {
    Condition.NEW: 100,
    Condition.LIKE_NEW: 90,
    Condition.GOOD: 75,
    Condition.FAIR: 55,
    Condition.POOR: 25,
    Condition.UNKNOWN: 50,
}


def score_profit(profit: float) -> float:
    if profit <= 0:
        return 0
    if profit >= 500:
        return 100
    return pct((profit / 500) * 100)


def score_roi(roi: float) -> float:
    if roi <= 0:
        return 0
    if roi >= 100:
        return 100
    return pct(roi)


def choose_verdict(score: float, profit: float, roi: float) -> Verdict:
    if profit <= 0:
        return Verdict.PASS
    if score >= 80 and roi >= 50:
        return Verdict.STRONG_BUY
    if score >= 65 and roi >= 30:
        return Verdict.BUY
    if score >= 50:
        return Verdict.NEGOTIATE
    if score >= 35:
        return Verdict.CAUTION
    return Verdict.PASS


def calculate_max_buy_price(
    resale_price: float,
    fees: float,
    shipping: float,
    repairs: float,
    other_costs: float,
    target_roi: float = 0.40,
) -> float:
    fixed_costs = fees + shipping + repairs + other_costs

    # Solve:
    # profit / total_cost = target_roi
    # resale - fixed - buy = target_roi * (fixed + buy)
    numerator = resale_price - fixed_costs * (1 + target_roi)
    denominator = 1 + target_roi

    return round(max(0, numerator / denominator), 2)


# ============================================================
# ENGINE
# ============================================================

def analyze_flip(item: FlipRequest) -> FlipAnalysis:
    total_cost = (
        item.asking_price
        + item.estimated_fees
        + item.estimated_shipping
        + item.estimated_repairs
        + item.other_costs
    )

    profit = item.estimated_resale_price - total_cost

    roi = (profit / total_cost * 100) if total_cost > 0 else 0
    margin = (
        profit / item.estimated_resale_price * 100
        if item.estimated_resale_price > 0
        else 0
    )

    profit_score = score_profit(profit)
    roi_score = score_roi(roi)
    condition_score = CONDITION_SCORES[item.condition]

    opportunity_score = pct(
        profit_score * 0.30
        + roi_score * 0.25
        + item.demand_score * 0.15
        + item.sell_speed_score * 0.10
        + item.confidence_score * 0.10
        + condition_score * 0.10
    )

    verdict = choose_verdict(opportunity_score, profit, roi)

    reasons: List[str] = []
    risk_flags: List[str] = []

    if profit >= 200:
        reasons.append("Strong projected dollar profit.")
    elif profit > 0:
        reasons.append("Projected to be profitable.")
    else:
        risk_flags.append("Projected resale does not cover total cost.")

    if roi >= 50:
        reasons.append("Strong projected return on investment.")
    elif roi < 20:
        risk_flags.append("Low projected ROI.")

    if item.demand_score >= 70:
        reasons.append("Demand appears strong.")
    elif item.demand_score < 40:
        risk_flags.append("Demand may be weak.")

    if item.sell_speed_score >= 70:
        reasons.append("Item may sell quickly.")
    elif item.sell_speed_score < 40:
        risk_flags.append("Item may take longer to sell.")

    if item.confidence_score < 50:
        risk_flags.append("Resale estimate confidence is low.")

    if item.condition in {Condition.FAIR, Condition.POOR, Condition.UNKNOWN}:
        risk_flags.append("Condition adds resale uncertainty.")

    max_buy = calculate_max_buy_price(
        resale_price=item.estimated_resale_price,
        fees=item.estimated_fees,
        shipping=item.estimated_shipping,
        repairs=item.estimated_repairs,
        other_costs=item.other_costs,
    )

    return FlipAnalysis(
        title=item.title,
        asking_price=round(item.asking_price, 2),
        resale_price=round(item.estimated_resale_price, 2),
        total_cost=round(total_cost, 2),
        projected_profit=round(profit, 2),
        roi_percent=round(roi, 1),
        margin_percent=round(margin, 1),
        profit_score=profit_score,
        roi_score=roi_score,
        demand_score=pct(item.demand_score),
        sell_speed_score=pct(item.sell_speed_score),
        confidence_score=pct(item.confidence_score),
        condition_score=pct(condition_score),
        opportunity_score=opportunity_score,
        verdict=verdict,
        max_buy_price=max_buy,
        reasons=reasons,
        risk_flags=risk_flags,
    )


# ============================================================
# ROUTES
# ============================================================

@app.get("/")
def root():
    return {
        "name": "FLIPFLOW™ API",
        "version": "1.0.0",
        "status": "online",
        "message": "Reseller Intelligence and Opportunity Scoring Engine",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=FlipAnalysis)
def analyze(item: FlipRequest):
    return analyze_flip(item)


# Run locally with:
# uvicorn flipflow:app --reload
