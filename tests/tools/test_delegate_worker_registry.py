import unittest

from tools.delegate_worker_registry import WorkerConfigError, parse_workers, resolve_worker


class DelegateWorkerRegistryTests(unittest.TestCase):
    def test_mapping_worker_inherits_defaults_and_call_overrides_win(self):
        config = {
            "provider": "global-provider",
            "model": "global-model",
            "max_iterations": 20,
            "max_concurrent_children": 3,
            "child_timeout_seconds": 90,
            "workers": {
                "code-review": {
                    "activity": "Review a patch",
                    "role": "orchestrator",
                    "model": "review-model",
                    "toolsets": ["filesystem", "git"],
                    "max_iterations": 40,
                    "fallback_models": ["review-backup"],
                    "budget": {"max_cost_usd": 1.25, "max_total_tokens": 9000},
                }
            },
        }

        resolved = resolve_worker(
            "code-review", config,
            {"model": "call-model", "max_concurrency": 7, "budget": {"max_requests": 2}},
        )

        self.assertEqual(resolved["id"], "code-review")
        self.assertEqual(resolved["provider"], "global-provider")
        self.assertEqual(resolved["model"], "call-model")
        self.assertEqual(resolved["max_iterations"], 40)
        self.assertEqual(resolved["max_concurrency"], 7)
        self.assertEqual(resolved["timeout_seconds"], 90.0)
        self.assertEqual(resolved["toolsets"], ["filesystem", "git"])
        self.assertEqual(resolved["fallback_models"], ["review-backup"])
        self.assertEqual(resolved["budget"], {"max_requests": 2})

    def test_list_workers_uses_embedded_id(self):
        workers = parse_workers([
            {"id": "researcher", "activity": "Find sources", "tools": ["web_search"]},
        ])
        self.assertEqual(workers["researcher"]["tools"], ["web_search"])

    def test_rejects_secret_values_without_echoing_them(self):
        with self.assertRaises(WorkerConfigError) as caught:
            resolve_worker(
                "unsafe", {"workers": {"unsafe": {"activity": "nope", "api_key": "super-secret"}}},
            )
        self.assertNotIn("super-secret", str(caught.exception))

    def test_rejects_invalid_ids_and_unknown_fields(self):
        with self.assertRaises(WorkerConfigError):
            parse_workers({"not a worker": {"activity": "x"}})
        with self.assertRaises(WorkerConfigError):
            parse_workers({"valid": {"activity": "x", "typo": True}})


if __name__ == "__main__":
    unittest.main()