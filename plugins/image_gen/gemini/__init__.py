"""Google Gemini native image generation backend."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    success_response,
)
from agent.secret_scope import get_secret
from marcel_cli.config import load_config

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash-image"
_ASPECT_RATIOS = {"landscape": "16:9", "square": "1:1", "portrait": "9:16"}


class GeminiImageGenProvider(ImageGenProvider):
    provider_id = "gemini"
    label = "Google Gemini"

    def name(self) -> str:
        return self.label

    def is_available(self) -> bool:
        return bool(get_secret("GEMINI_API_KEY"))

    def list_models(self) -> List[Dict[str, Any]]:
        return [{
            "id": DEFAULT_MODEL,
            "name": "Gemini Flash Image",
            "speed": "fast",
            "strengths": "text-to-image and image understanding",
            "modalities": ["text"],
        }]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Google Gemini Image", "badge": "paid",
            "tag": "Gemini native image generation",
            "env_vars": [{
                "name": "GEMINI_API_KEY", "prompt": "Google Gemini API key",
                "url": "https://aistudio.google.com/apikey",
            }],
        }

    def capabilities(self) -> Dict[str, Any]:
        return {"modalities": ["text"], "max_reference_images": 0}

    def generate(
        self, prompt: str, aspect_ratio: str = DEFAULT_ASPECT_RATIO, *,
        image_url: Optional[str] = None, reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)
        model = str(kwargs.get("model") or "").strip()
        if not model:
            try:
                model = str(
                    ((load_config() or {}).get("image_gen") or {}).get("model") or DEFAULT_MODEL)
            except Exception:
                model = DEFAULT_MODEL
        if not prompt:
            return error_response(
                error="An image description is required.", error_type="invalid_prompt",
                provider="gemini", model=model, prompt=prompt, aspect_ratio=aspect)
        if image_url or reference_image_urls:
            return error_response(
                error="The selected Gemini image backend currently supports creation from text only.",
                error_type="unsupported_modality", provider="gemini", model=model,
                prompt=prompt, aspect_ratio=aspect)
        api_key = get_secret("GEMINI_API_KEY")
        if not api_key:
            return error_response(
                error="Google Gemini is not connected.", error_type="auth_required",
                provider="gemini", model=model, prompt=prompt, aspect_ratio=aspect)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": _ASPECT_RATIOS[aspect]},
            },
        }
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key}, json=payload, timeout=180)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            logger.debug("Gemini image generation failed", exc_info=True)
            return error_response(
                error=f"Gemini image generation failed: {exc}", error_type="api_error",
                provider="gemini", model=model, prompt=prompt, aspect_ratio=aspect)
        parts = (
            (((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            if isinstance(body, dict) else []
        )
        image_part = next(
            (part for part in parts if isinstance(part, dict)
             and isinstance(part.get("inlineData") or part.get("inline_data"), dict)),
            None,
        )
        inline = (image_part or {}).get("inlineData") or (image_part or {}).get("inline_data") or {}
        data = inline.get("data")
        if not data:
            return error_response(
                error="Gemini returned no image data.", error_type="empty_response",
                provider="gemini", model=model, prompt=prompt, aspect_ratio=aspect)
        path = save_b64_image(data, prefix=f"gemini_{model.replace('/', '_')}")
        return success_response(
            image=str(path), model=model, prompt=prompt, aspect_ratio=aspect,
            provider="gemini", extra={"mime_type": inline.get("mimeType") or inline.get("mime_type")})


def register(ctx: Any) -> None:
    ctx.register_image_gen_provider(GeminiImageGenProvider())