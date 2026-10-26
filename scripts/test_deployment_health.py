import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "deployment_health", Path(__file__).with_name("deployment-health.py"))
assert SPEC and SPEC.loader
health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health)


class PolicyReadinessTests(unittest.TestCase):
    def test_both_versions_required_even_when_active_is_v32(self):
        for versions in ([], ["v3.1"], ["v3.2"]):
            with self.assertRaisesRegex(RuntimeError, "both v3.1 and v3.2"):
                health.require_policy_versions({"indexedPolicyVersions": versions}, "v3.2")

    def test_old_and_new_versions_pass(self):
        health.require_policy_versions({"indexedPolicyVersions": ["v3.1", "v3.2"]}, "v3.2")


if __name__ == "__main__":
    unittest.main()
