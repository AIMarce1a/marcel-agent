import json
import unittest
from pathlib import Path

from tools.marcel_routing import RoutingError, resolve_route, route_request


FIXTURES = Path(__file__).parent.parent / "fixtures"


class MarcelRoutingTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((FIXTURES / "marcel_routing_config.json").read_text())
        self.catalog = json.loads((FIXTURES / "marcel_router_catalog.json").read_text())

    def test_activity_selects_worker_and_primary_model(self):
        route = resolve_route(self.config, self.catalog, {
            "activity": "coding", "toolsets": ["filesystem"], "enabled_toolsets": ["filesystem", "terminal"],
            "context_tokens": 5000,
        })
        self.assertEqual(("coding", "openai/gpt-4.1-mini"), (route.worker_id, route.model_id))

    def test_general_worker_and_cheapest_capable_are_deterministic(self):
        route = resolve_route(self.config, self.catalog, {"activity": "research", "context_tokens": 200})
        self.assertEqual("general", route.worker_id)
        self.assertEqual("mistral/ministral-8b", route.model_id)

    def test_explicit_pins_and_fallback_models(self):
        fallback_config = json.loads(json.dumps(self.config))
        fallback_config["delegation"]["workers"]["coding"]["model"] = "unavailable/primary"
        fallback = resolve_route(fallback_config, self.catalog, {
            "worker": "coding", "enabled_toolsets": ["filesystem", "terminal"], "output_tokens": 4000,
        })
        # The fallback is considered after a configured primary that is absent.
        self.assertEqual("anthropic/claude-haiku-4-5", fallback.model_id)
        explicit = resolve_route(self.config, self.catalog, {
            "worker": "coding", "model": "anthropic/claude-haiku-4-5",
            "enabled_toolsets": ["filesystem", "terminal"],
        })
        self.assertEqual("anthropic/claude-haiku-4-5", explicit.model_id)

    def test_disabled_toolset_and_unsatisfied_pin_have_clear_failures(self):
        disabled = route_request(self.config, self.catalog, {"activity": "coding", "enabled_toolsets": ["filesystem"]})
        self.assertFalse(disabled.ok)
        self.assertIn("disabled toolset terminal", disabled.reason)
        missing = route_request(self.config, self.catalog, {"worker": "general", "model": "missing/model"})
        self.assertIn("not in catalog", missing.reason)
        with self.assertRaisesRegex(RoutingError, "not in catalog"):
            resolve_route(self.config, self.catalog, {"worker": "general", "model": "missing/model"})

    def test_capability_modality_and_context_filtering(self):
        route = resolve_route(self.config, self.catalog, {
            "activity": "general", "capabilities": ["tools"], "modalities": ["image"], "context_tokens": 250000,
        })
        self.assertEqual("openai/gpt-4.1-mini", route.model_id)


if __name__ == "__main__":
    unittest.main()