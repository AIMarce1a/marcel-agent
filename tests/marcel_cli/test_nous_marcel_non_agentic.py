"""Tests for the Nous-Marcel-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"marcel"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``marcel-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "marcel" tag namespace.

``is_nous_marcel_non_agentic`` should only match the actual Nous Research
Marcel-3 / Marcel-4 chat family.
"""

from __future__ import annotations

import pytest

from marcel_cli.model_switch import (
    _MARCEL_MODEL_WARNING,
    _check_marcel_model_warning,
    is_nous_marcel_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "NousResearch/Marcel-3-Llama-3.1-70B",
        "NousResearch/Marcel-3-Llama-3.1-405B",
        "marcel-3",
        "Marcel-3",
        "marcel-4",
        "marcel-4-405b",
        "marcel_4_70b",
        "openrouter/marcel3:70b",
        "openrouter/nousresearch/marcel-4-405b",
        "NousResearch/Marcel3",
        "marcel-3.1",
    ],
)
def test_matches_real_nous_marcel_chat_models(model_name: str) -> None:
    assert is_nous_marcel_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Marcel 3/4"
    )
    assert _check_marcel_model_warning(model_name) == _MARCEL_MODEL_WARNING


