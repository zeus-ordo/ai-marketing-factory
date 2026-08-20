from app.prompt_utils import fit_minimax_prompt


def test_fit_minimax_prompt_keeps_short_prompt_unchanged():
    prompt = "Campaign: demo\nCreate a campaign key visual."
    assert fit_minimax_prompt(prompt) == prompt


def test_fit_minimax_prompt_keeps_prompt_under_provider_limit_and_preserves_edges():
    prompt = "Campaign: final testing 001\n" + ("reference context " * 200) + "\nCreate a campaign key visual aligned with the brief."
    fitted = fit_minimax_prompt(prompt)

    assert len(fitted) <= 1400
    assert fitted.startswith("Campaign: final testing 001")
    assert fitted.endswith("Create a campaign key visual aligned with the brief.")
