from fastapi import FastAPI

from .schemas import DecisionPlanRequest, DecisionPlanResponse, DecisionTask


def _is_comparison_image_request(payload: DecisionPlanRequest) -> bool:
    text = " ".join([
        payload.brief.campaign_name,
        payload.brief.product_name,
        payload.brief.description,
        " ".join(payload.brief.mandatory_elements),
    ]).lower()
    return any(term in text for term in ["比較", "對比", "comparison", "compare", "vs", "versus", "排行", "排名"])


app = FastAPI(
    title="Marketing AI Factory - Decision Service",
    version="0.1.0",
    description="MVP decision planning service (DeepSeek-R1 placeholder logic).",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/internal/decision/plan", response_model=DecisionPlanResponse)
def create_plan(payload: DecisionPlanRequest) -> DecisionPlanResponse:
    copy_task_id = f"tsk_copy_{payload.campaign_id[-6:]}"
    image_task_id = f"tsk_image_{payload.campaign_id[-6:]}"
    video_task_id = f"tsk_video_{payload.campaign_id[-6:]}"
    ads_task_id = f"tsk_ads_{payload.campaign_id[-6:]}"
    deliverables = payload.brief.deliverables
    copy_count = int(deliverables.get("copy_variants", 0) or 0)
    image_count = int(deliverables.get("image_assets", 0) or 0)
    video_count = int(deliverables.get("short_video_assets", 0) or 0)
    ads_count = int(deliverables.get("ads_strategy", 0) or 0)

    tasks: list[DecisionTask] = []
    if copy_count > 0:
        tasks.append(DecisionTask(
            task_id=copy_task_id,
            task_type="copywriting",
            depends_on=[],
            priority=1,
            acceptance=["至少3個版本", "需有CTA", "符合品牌語氣"],
        ))

    if image_count > 0:
        image_acceptance = ["1:1 與 4:5 尺寸", "符合活動名稱與使用者需求", "可通過視覺驗證"]
        if _is_comparison_image_request(payload):
            image_acceptance = ["比較表/資訊圖版型", "呈現多項選擇的差異", "標題、欄位與標籤清楚可讀"]
        tasks.append(DecisionTask(
            task_id=image_task_id,
            task_type="image_generation",
            depends_on=[copy_task_id] if copy_count > 0 else [],
            priority=2,
            acceptance=image_acceptance,
        ))

    if video_count > 0:
        tasks.append(DecisionTask(
            task_id=video_task_id,
            task_type="video_generation",
            depends_on=[image_task_id] if image_count > 0 else [],
            priority=3,
            acceptance=["15秒內", "字幕版", "適合Reels"],
        ))

    if ads_count > 0:
        ads_dependencies = []
        if copy_count > 0:
            ads_dependencies.append(copy_task_id)
        if image_count > 0:
            ads_dependencies.append(image_task_id)
        tasks.append(DecisionTask(
            task_id=ads_task_id,
            task_type="ads_strategy",
            depends_on=ads_dependencies,
            priority=2,
            acceptance=["平台別投放設定", "受眾假設", "預算拆分"],
        ))

    return DecisionPlanResponse(
        campaign_id=payload.campaign_id,
        plan_version=1,
        summary=f"{payload.brief.product_name} conversion-focused campaign plan",
        tasks=tasks,
    )
