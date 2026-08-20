from app.main import is_single_asset_generation, next_single_asset_index, single_asset_base_name


def test_manual_single_asset_is_independent_even_with_campaign_run_id():
    assert is_single_asset_generation("manual_copy_abc123") is True


def test_regular_campaign_task_is_not_single_asset():
    assert is_single_asset_generation("tsk_copy_abc123") is False


def test_next_single_asset_uses_new_base_index_without_version_bump():
    assert next_single_asset_index(["星光直播_manual_copy_1", "星光直播_manual_copy_3"], "星光直播_manual_copy_") == 4
    assert next_single_asset_index(["final_testing_Copy_1"], "星光直播_manual_copy_") == 1


def test_single_asset_base_name_includes_campaign_name_before_manual():
    assert single_asset_base_name("星光直播", "image", 1) == "星光直播_manual_image_1"
