MINIMAX_PROMPT_LIMIT = 1400
_TRUNCATION_MARKER = "\n...[context truncated for MiniMax limit]...\n"
_TAIL_CHARS = 320


def fit_minimax_prompt(prompt: str, max_chars: int = MINIMAX_PROMPT_LIMIT) -> str:
    if len(prompt) <= max_chars:
        return prompt

    tail = prompt[-_TAIL_CHARS:]
    head_length = max(0, max_chars - len(_TRUNCATION_MARKER) - len(tail))
    return f"{prompt[:head_length]}{_TRUNCATION_MARKER}{tail}"
