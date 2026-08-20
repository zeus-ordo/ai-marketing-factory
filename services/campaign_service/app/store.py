from datetime import datetime
from typing import Literal
from uuid import uuid4

from .persistence import PostgresPersistence
from .schemas import CampaignBrief, CampaignRecord, TaskRecord


class InMemoryStore:
    def __init__(self) -> None:
        self.campaigns: dict[str, CampaignRecord] = {}
        self.tasks: dict[str, list[TaskRecord]] = {}
        self.persistence: PostgresPersistence | None = None

    def set_persistence(self, persistence: PostgresPersistence | None) -> None:
        self.persistence = persistence

    def create_campaign(self, company_id: str, brief: CampaignBrief) -> CampaignRecord:
        campaign_id = f"cmp_{uuid4().hex[:12]}"
        campaign = CampaignRecord(
            company_id=company_id,
            campaign_id=campaign_id,
            status="running",
            created_at=datetime.utcnow(),
            brief=brief,
        )
        self.campaigns[campaign_id] = campaign
        self.tasks[campaign_id] = []
        if self.persistence is not None:
            self.persistence.create_campaign(campaign)
        return campaign

    def get_campaign(self, campaign_id: str) -> CampaignRecord | None:
        if self.persistence is not None:
            from_db = self.persistence.get_campaign(campaign_id)
            if from_db is not None:
                return from_db
        return self.campaigns.get(campaign_id)

    def list_campaigns(self, company_id: str | None = None) -> list[CampaignRecord]:
        if self.persistence is not None:
            rows = self.persistence.list_campaigns(company_id=company_id)
            if rows:
                return rows
        items = list(self.campaigns.values())
        if company_id is not None:
            items = [c for c in items if c.company_id == company_id]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def create_task_plan(self, company_id: str, campaign_id: str) -> list[TaskRecord]:
        planned = [
            TaskRecord(
                company_id=company_id,
                task_id=f"tsk_copy_{uuid4().hex[:8]}",
                campaign_id=campaign_id,
                task_type="copywriting",
                status="planned",
                priority=1,
                depends_on=[],
                acceptance=["至少3個版本", "需有CTA", "符合品牌語氣"],
            ),
            TaskRecord(
                company_id=company_id,
                task_id=f"tsk_image_{uuid4().hex[:8]}",
                campaign_id=campaign_id,
                task_type="image_generation",
                status="planned",
                priority=2,
                depends_on=[],
                acceptance=["1:1 與 4:5 尺寸", "有產品主體", "可通過視覺驗證"],
            ),
            TaskRecord(
                company_id=company_id,
                task_id=f"tsk_video_{uuid4().hex[:8]}",
                campaign_id=campaign_id,
                task_type="video_generation",
                status="pending",
                priority=3,
                depends_on=[],
                acceptance=["15秒內", "字幕版", "適合Reels"],
            ),
            TaskRecord(
                company_id=company_id,
                task_id=f"tsk_ads_{uuid4().hex[:8]}",
                campaign_id=campaign_id,
                task_type="ads_strategy",
                status="planned",
                priority=2,
                depends_on=[],
                acceptance=["平台別投放設定", "受眾假設", "預算拆分"],
            ),
        ]
        self.tasks[campaign_id] = planned
        return planned

    def set_tasks(self, campaign_id: str, tasks: list[TaskRecord]) -> list[TaskRecord]:
        self.tasks[campaign_id] = tasks
        if self.persistence is not None:
            self.persistence.set_tasks(campaign_id, tasks)
        return tasks

    def get_tasks(self, campaign_id: str) -> list[TaskRecord]:
        if self.persistence is not None:
            rows = self.persistence.get_tasks(campaign_id)
            if rows:
                return rows
        return self.tasks.get(campaign_id, [])

    def mark_running(self, campaign_id: str) -> CampaignRecord | None:
        campaign = self.get_campaign(campaign_id)
        if campaign is None:
            return None
        campaign.status = "running"
        self.campaigns[campaign_id] = campaign
        if self.persistence is not None:
            self.persistence.set_campaign_status(campaign_id, "running")
        return campaign

    def set_campaign_status(
        self,
        campaign_id: str,
        status: Literal["draft", "running", "completed", "failed"],
    ) -> CampaignRecord | None:
        campaign = self.get_campaign(campaign_id)
        if campaign is None:
            return None
        campaign.status = status
        self.campaigns[campaign_id] = campaign
        if self.persistence is not None:
            self.persistence.set_campaign_status(campaign_id, status)
        return campaign

    def update_campaign_brief(self, campaign_id: str, brief: CampaignBrief) -> CampaignRecord | None:
        campaign = self.get_campaign(campaign_id)
        if campaign is None:
            return None
        campaign.brief = brief
        self.campaigns[campaign_id] = campaign
        if self.persistence is not None:
            self.persistence.update_campaign_brief(campaign_id, brief)
        return campaign

    def delete_campaign(self, campaign_id: str) -> bool:
        existed = self.get_campaign(campaign_id) is not None
        self.campaigns.pop(campaign_id, None)
        self.tasks.pop(campaign_id, None)
        if self.persistence is not None:
            self.persistence.delete_campaign(campaign_id)
        return existed
