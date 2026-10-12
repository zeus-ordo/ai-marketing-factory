import math

from fastapi import HTTPException

from .schemas import CampaignBrief


def validate_campaign_brief(brief: CampaignBrief) -> None:
    for field in (
        "campaign_name",
        "product_name",
        "objective",
        "industry_category",
        "project_description",
    ):
        if not getattr(brief, field).strip():
            raise HTTPException(status_code=422, detail={field: "must not be blank"})

    if not math.isfinite(brief.budget):
        raise HTTPException(status_code=422, detail={"budget": "must be finite"})

    if brief.deliverables.ads_strategy > 0 and brief.budget <= 0:
        raise HTTPException(status_code=422, detail={"budget": "must be greater than 0 when ads_strategy is selected"})
