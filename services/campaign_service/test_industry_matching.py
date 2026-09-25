from datetime import datetime, timezone

from app.industry_matching import (
    industry_terms,
    match_industry_items,
    normalize_industry,
)
from app.main import (
    CampaignReferenceRecord,
    KnowledgeItemRecord,
    build_campaign_prompt_context,
    build_copy_generation_prompt,
    build_image_generation_prompt,
    build_video_generation_prompt,
    campaign_references,
    campaign_reference_files,
    list_campaign_reference_prompt_lines,
    list_campaign_reference_context,
    list_industry_knowledge_context,
    list_industry_knowledge_prompt_lines,
    knowledge_items,
)
from app.schemas import CampaignBrief, CampaignRecord, Deliverables


def campaign() -> CampaignRecord:
    return CampaignRecord(
        company_id="co_1",
        campaign_id="ca_1",
        created_at=datetime.now(timezone.utc),
        brief=CampaignBrief(
            campaign_name="Cocktail launch",
            product_name="New cocktail",
            objective="awareness",
            industry_category="餐酒館",
            target_audience={"age_range": "25-44", "gender": "all", "persona": "diners"},
            platforms=["instagram"],
            budget=1000,
            brand_tone=["warm"],
            deliverables=Deliverables(),
            deadline=datetime(2026, 10, 1, tzinfo=timezone.utc),
        ),
    )


def test_normalizes_industry_and_expands_restaurant_bar_synonyms():
    assert normalize_industry(" 餐酒館 ") == "餐酒館"
    assert {"餐酒館", "酒吧", "調酒", "餐飲", "品酒", "夜生活", "餐廳"} <= industry_terms("餐酒館")


def test_matches_cantonese_restaurant_synonyms():
    items = [{"title": "調酒菜單", "description": "酒吧夜生活", "metadata": {"category": "餐酒館"}}]
    matched = match_industry_items("餐酒館", "新品調酒", "awareness", items)
    assert [item["title"] for item in matched] == ["調酒菜單"]
    assert matched[0]["source_type"] == "industry_matched"


def test_exact_industry_matches_rank_before_synonyms():
    items = [
        {"title": "酒吧靈感", "metadata": {"category": "酒吧"}},
        {"title": "餐酒館品牌指南", "metadata": {"category": "餐酒館"}},
    ]
    matched = match_industry_items("餐酒館", "新品調酒", "awareness", items)
    assert [item["title"] for item in matched] == ["餐酒館品牌指南", "酒吧靈感"]


def test_exact_title_and_folder_match_rank_before_synonyms():
    items = [
        {"title": "酒吧靈感", "metadata": {"folder": "酒吧"}},
        {"title": "餐酒館品牌指南", "metadata": {"keywords": ["餐酒館"]}},
    ]
    matched = match_industry_items("餐酒館", "新品調酒", "awareness", items)
    assert [item["title"] for item in matched] == ["餐酒館品牌指南", "酒吧靈感"]


def test_match_limit_is_applied():
    items = [{"title": f"酒吧 {index}", "metadata": {"category": "酒吧"}} for index in range(10)]
    assert len(match_industry_items("餐酒館", "新品調酒", "awareness", items, limit=3)) == 3


def test_does_not_match_unrelated_industry():
    items = [{"title": "汽車保養", "description": "車輛維修", "metadata": {"category": "汽車"}}]
    assert match_industry_items("餐酒館", "新品調酒", "awareness", items) == []


def test_prompt_helpers_add_source_type_without_removing_existing_text(monkeypatch, tmp_path):
    item = KnowledgeItemRecord(
        item_id="ki_1", company_id="co_1", title="餐酒館指南", source="manual",
        description="餐廳與調酒", metadata={"category": "餐酒館"}, created_at=datetime.now(timezone.utc)
    )
    reference = CampaignReferenceRecord(
        reference_id="ref_1", campaign_id="ca_1", file_name="brief.txt", file_type="text/plain",
        file_size=5, uploaded_at=datetime.now(timezone.utc).isoformat(), download_url="/brief.txt", folder="即時上傳"
    )
    path = tmp_path / "brief.txt"
    path.write_text("brand facts", encoding="utf-8")
    monkeypatch.setattr("app.main.persistence", None)
    knowledge_items["co_1"] = [item]
    campaign_references["ca_1"] = [reference]
    campaign_reference_files["ca_1"] = {"ref_1": str(path)}
    try:
        knowledge_lines = list_industry_knowledge_prompt_lines(campaign())
        reference_lines = list_campaign_reference_prompt_lines(campaign())
        reference_context = list_campaign_reference_context(campaign())
        knowledge_context = list_industry_knowledge_context(campaign())
        assert "source_type=industry_matched" in knowledge_lines[0]
        assert "source_type=immediate_upload" in reference_lines[0]
        assert "brand facts" in reference_lines[0]
        assert reference_context[0]["reference_id"] == "ref_1"
        assert reference_context[0]["folder"] == "即時上傳"
        assert reference_context[0]["source_type"] == "immediate_upload"
        assert knowledge_context[0]["item_id"] == "ki_1"
        assert knowledge_context[0]["source_type"] == "industry_matched"
    finally:
        knowledge_items.pop("co_1", None)
        campaign_references.pop("ca_1", None)
        campaign_reference_files.pop("ca_1", None)


def test_generation_prompt_contains_structured_reference_traceability(monkeypatch, tmp_path):
    reference = CampaignReferenceRecord(
        reference_id="ref_prompt_1", campaign_id="ca_1", file_name="campaign-brief.txt", file_type="text/plain",
        file_size=12, uploaded_at=datetime.now(timezone.utc).isoformat(), download_url="/brief.txt", folder="即時上傳"
    )
    path = tmp_path / "campaign-brief.txt"
    path.write_text("preferred cocktail style", encoding="utf-8")
    knowledge = KnowledgeItemRecord(
        item_id="ki_prompt_1", company_id="co_1", title="餐酒館風格", source="manual",
        description="餐酒館品牌語氣", metadata={"category": "餐酒館"}, created_at=datetime.now(timezone.utc)
    )
    monkeypatch.setattr("app.main.persistence", None)
    campaign_references["ca_1"] = [reference]
    campaign_reference_files["ca_1"] = {"ref_prompt_1": str(path)}
    knowledge_items["co_1"] = [knowledge]
    try:
        prompt = build_campaign_prompt_context(campaign())
        assert "source_type=immediate_upload" in prompt
        assert "ref_prompt_1" in prompt
        assert "即時上傳" in prompt
        assert "source_type=industry_matched" in prompt
        assert "ki_prompt_1" in prompt
        assert "餐酒館" in prompt
        assert "preferred cocktail style" in prompt
    finally:
        campaign_references.pop("ca_1", None)
        campaign_reference_files.pop("ca_1", None)
        knowledge_items.pop("co_1", None)


def test_copy_prompt_contains_type_length_priority_and_proofreading_policy():
    prompt = build_copy_generation_prompt(campaign())

    assert "宣傳文宣" in prompt
    assert "社群文章" in prompt
    assert "公關稿" in prompt
    assert "100 字內" in prompt
    assert "100-200 字" in prompt
    assert "300-500 字" in prompt
    assert "使用者上傳或選擇的參考資料" in prompt
    assert "生成後校稿" in prompt


def test_image_prompt_contains_type_reference_ratio_and_review_policy():
    prompt = build_image_generation_prompt(campaign())

    assert "主視覺 KV" in prompt
    assert "社群圖文" in prompt
    assert "特殊規則" in prompt
    assert "75:25" in prompt
    assert "使用者上傳或選擇的參考資料" in prompt
    assert "生成後校稿" in prompt


def test_video_prompt_contains_duration_type_reference_and_review_policy():
    prompt = build_video_generation_prompt(campaign())

    assert "短影音" in prompt
    assert "10 秒" in prompt
    assert "宣傳短片" in prompt
    assert "15 秒" in prompt
    assert "網路廣告" in prompt
    assert "30 秒" in prompt
    assert "使用者上傳或選擇的參考資料" in prompt
    assert "生成後校稿" in prompt
