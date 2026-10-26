import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("deploy_main", Path(__file__).with_name("deploy-main.py"))
assert SPEC and SPEC.loader
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


class SourceSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.origin = self.root / "origin"
        self.source = self.root / "deployment"
        self.git("init", "--initial-branch=main", str(self.origin))
        self.git("-C", str(self.origin), "config", "user.name", "Test")
        self.git("-C", str(self.origin), "config", "user.email", "test@example.invalid")
        self.commit("one")

    def git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, content):
        (self.origin / "source").write_text(content)
        self.git("-C", str(self.origin), "add", "source")
        self.git("-C", str(self.origin), "commit", "-m", content)
        return self.git("-C", str(self.origin), "rev-parse", "HEAD")

    def test_clone_and_fast_forward_main_without_switching_original_branch(self):
        first = deploy.sync_source(self.source, str(self.origin))
        self.assertEqual(first, self.git("-C", str(self.origin), "rev-parse", "main"))
        new = self.commit("two")
        self.git("-C", str(self.origin), "checkout", "-b", "work")
        (self.origin / "source").write_text("uncommitted")
        self.assertEqual(deploy.sync_source(self.source, str(self.origin)), new)
        self.assertEqual(self.git("-C", str(self.origin), "branch", "--show-current"), "work")
        self.assertEqual((self.origin / "source").read_text(), "uncommitted")

    def test_dirty_deployment_is_not_reset(self):
        deploy.sync_source(self.source, str(self.origin))
        (self.source / "untracked").write_text("keep")
        with self.assertRaisesRegex(deploy.DeploymentError, "Dirty deployment checkout"):
            deploy.sync_source(self.source, str(self.origin))
        self.assertEqual((self.source / "untracked").read_text(), "keep")

    def test_ahead_main_is_rejected(self):
        deploy.sync_source(self.source, str(self.origin))
        self.git("-C", str(self.source), "config", "user.name", "Test")
        self.git("-C", str(self.source), "config", "user.email", "test@example.invalid")
        (self.source / "local").write_text("keep")
        self.git("-C", str(self.source), "add", "local")
        self.git("-C", str(self.source), "commit", "-m", "local")
        with self.assertRaisesRegex(deploy.DeploymentError, "ahead"):
            deploy.sync_source(self.source, str(self.origin))

    def test_wrong_origin_is_rejected(self):
        deploy.sync_source(self.source, str(self.origin))
        with self.assertRaisesRegex(deploy.DeploymentError, "origin differs"):
            deploy.sync_source(self.source, str(self.root / "other"))

    def test_divergent_main_is_rejected(self):
        deploy.sync_source(self.source, str(self.origin))
        self.git("-C", str(self.source), "config", "user.name", "Test")
        self.git("-C", str(self.source), "config", "user.email", "test@example.invalid")
        (self.source / "local").write_text("keep")
        self.git("-C", str(self.source), "add", "local")
        self.git("-C", str(self.source), "commit", "-m", "local")
        self.commit("remote")
        with self.assertRaises(deploy.DeploymentError):
            deploy.sync_source(self.source, str(self.origin))
        self.assertEqual((self.source / "local").read_text(), "keep")


class DeploymentTests(unittest.TestCase):
    def test_index_keeps_existing_v31_and_runs_v32_once(self):
        with patch.object(deploy, "run", side_effect=['["v3.1"]', ""]) as runner:
            self.assertEqual(deploy.index_policies(["compose"], {}), ["v3.2"])
        commands = [call.args[0] for call in runner.call_args_list]
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[-1][-3:], ["python", "-m", "app.rag_mcp.index"])
        self.assertIn("LIVEGUARD_POLICY_VERSION=v3.2", commands[-1])
        self.assertIn("POLICY_VERSION=v3.2", commands[-1])

    def test_empty_db_indexes_each_version_once(self):
        with patch.object(deploy, "run", side_effect=["[]", "", ""]) as runner:
            self.assertEqual(deploy.index_policies(["compose"], {}), ["v3.1", "v3.2"])
        self.assertEqual(runner.call_count, 3)

    def test_index_failure_is_not_retried_or_hidden(self):
        with patch.object(deploy, "run", side_effect=['["v3.1"]', deploy.DeploymentError("index failed")]) as runner:
            with self.assertRaisesRegex(deploy.DeploymentError, "index failed"):
                deploy.index_policies([], {})
        self.assertEqual(runner.call_count, 2)

    def test_same_source_and_image_for_all_agent_services(self):
        sources = {name: Path("/deploy") / name for name in deploy.REPOSITORIES}
        revisions = {"backend": "a" * 40, "agent": "b" * 40, "frontend": "c" * 40}
        config = deploy.runtime_config(sources, revisions)["services"]
        for name in ("agent", "business-mcp-1", "business-mcp-2", "rag-mcp"):
            self.assertEqual(config[name]["image"], "liveguard-agent:main-" + "b" * 40)
            self.assertEqual(config[name]["build"]["context"], "/deploy/agent")
        self.assertNotIn("volumes", json.dumps(config))

    def test_command_uses_existing_project_and_explicit_files(self):
        command = deploy.compose_command(Path("/safe/.env"), "existing", Path("/runtime.json"), True)
        self.assertIn("existing", command)
        self.assertIn("rabbit", command)
        self.assertEqual(command[-1], "/runtime.json")
        self.assertNotIn("down", command)

    def test_failed_commands_do_not_print_credentials(self):
        result = subprocess.CompletedProcess(["docker"], 1, "private-token", "private-token")
        with patch.object(deploy.subprocess, "run", return_value=result):
            with self.assertRaises(deploy.DeploymentError) as error:
                deploy.run(["docker"])
        self.assertNotIn("private-token", str(error.exception))

    def test_health_errors_are_explicit_without_dumping_other_output(self):
        result = subprocess.CompletedProcess(["docker"], 1,
            "private-token\nHEALTH_ERROR: agent: readyForTasks is not true\n", "private-token")
        with patch.object(deploy.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(deploy.DeploymentError, "readyForTasks") as error:
                deploy.run(["docker"], health_output=True)
        self.assertNotIn("private-token", str(error.exception))

    def test_failed_readiness_never_reports_success(self):
        with patch.object(deploy, "check_containers", side_effect=deploy.DeploymentError("not ready")), \
                patch.object(deploy.time, "monotonic", side_effect=[0, 0, 2, 2]), \
                patch.object(deploy.time, "sleep"):
            with self.assertRaisesRegex(deploy.DeploymentError, "No success recorded"):
                deploy.wait_ready([], {}, {}, 1, {})

    def test_stopped_container_is_rejected(self):
        with patch.object(deploy, "run", side_effect=[
            "container-id", json.dumps([{"State": {"Status": "restarting"}}])]):
            with self.assertRaisesRegex(deploy.DeploymentError, "not running/healthy"):
                deploy.check_containers([], {"services": {"agent": {}}}, {}, {})

    def test_wrong_running_image_is_rejected(self):
        with patch.object(deploy, "run", side_effect=[
            "container-id", json.dumps([{"State": {"Status": "running"}, "Image": "old"}])]):
            with self.assertRaisesRegex(deploy.DeploymentError, "recorded deployment image"):
                deploy.check_containers([], {"services": {"agent": {}}}, {}, {"agent": "new"})


class DeploymentFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.env_file = self.state / ".env"
        self.env_file.write_text("LOCAL_TEST_ONLY=1\n")
        self.args = SimpleNamespace(
            check_only=False, source_dir=None, sync_only=False, env_file=self.env_file,
            project="test", rabbit=True, timeout=10, seed_demo_participants=True)
        self.calls = []
        self.config = {"services": {
            "agent": {"image": "test-agent", "build": {}, "environment": {
                "AGENT_GATEWAY_FACTORY": "configured", "MODEL_NAME": "configured",
                "MODEL_API_KEY": "not-a-real-key", "MODEL_MAX_INPUT_TOKENS": "20000"}},
            "rag-mcp": {"image": "test-agent", "build": {}, "environment": {
                "RAG_DB_URL": "configured", "OPENAI_API_KEY": "not-a-real-key"}},
            "backend": {"image": "test-be", "build": {}},
            "frontend": {"image": "test-fe", "build": {}},
            "business-mcp-1": {"image": "test-agent", "build": {}},
            "business-mcp-2": {"image": "test-agent", "build": {}},
            "db": {"image": "test-db"},
        }}

    def fake_run(self, command, **kwargs):
        self.calls.append(command)
        if command[-3:] == ["config", "--format", "json"]:
            return json.dumps(self.config)
        if command[:3] == ["docker", "image", "inspect"]:
            return json.dumps([{"Id": command[-1] + "-id"}])
        return ""

    def execute(self, health_error=None):
        with patch.object(deploy, "run", side_effect=self.fake_run), \
                patch.object(deploy, "git", side_effect=lambda source, *args: "" if args[0] == "status" else "a" * 40), \
                patch.object(deploy, "sync_source", return_value="b" * 40) as sync, \
                patch.object(deploy, "wait_ready", side_effect=health_error) as ready, \
                patch.object(deploy, "index_policies", return_value=["v3.2"]) as index, \
                patch.object(deploy, "seed_participants") as seed:
            try:
                deploy.execute(self.args, self.state)
            finally:
                self.ready_calls = ready.call_count
                self.seed_calls = seed.call_count
                self.sync_calls = sync.call_count
                self.index_calls = index.call_count

    def test_build_once_record_image_ids_and_seed_after_readiness(self):
        self.execute()
        manifest = json.loads((self.state / "deployment.json").read_text())
        self.assertEqual(manifest["status"], "READY")
        self.assertEqual(manifest["images"]["agent"], "test-agent-id")
        self.assertEqual(self.ready_calls, 1)
        self.assertEqual(self.seed_calls, 1)
        self.assertEqual(self.index_calls, 1)
        builds = [call for call in self.calls if "build" in call]
        self.assertEqual(len(builds), 1)
        self.assertEqual(builds[0][-4:], ["build", "backend", "frontend", "agent"])
        self.assertTrue(any("--no-build" in call for call in self.calls))
        self.assertFalse(any("down" in call or "--volumes" in call for call in self.calls))

    def test_readiness_failure_records_failure_and_never_seeds(self):
        with self.assertRaisesRegex(deploy.DeploymentError, "not ready"):
            self.execute(health_error=deploy.DeploymentError("not ready"))
        manifest = json.loads((self.state / "deployment.json").read_text())
        self.assertEqual(manifest["status"], "FAILED")
        self.assertEqual(self.seed_calls, 0)

    def test_missing_key_fails_before_build_or_up(self):
        self.config["services"]["agent"]["environment"]["MODEL_API_KEY"] = ""
        with self.assertRaisesRegex(deploy.DeploymentError, "MODEL_API_KEY"):
            self.execute()
        manifest = json.loads((self.state / "deployment.json").read_text())
        self.assertEqual(manifest["status"], "PREFLIGHT_FAILED")
        self.assertEqual(self.seed_calls, 0)
        self.assertFalse(any("build" in call or "up" in call for call in self.calls))

    def test_check_only_never_fetches_builds_deploys_or_seeds(self):
        self.execute()
        self.calls.clear()
        self.args.check_only = True
        self.execute()
        self.assertEqual(self.sync_calls, 0)
        self.assertEqual(self.index_calls, 0)
        self.assertEqual(self.seed_calls, 0)
        self.assertFalse(any("build" in call or "up" in call for call in self.calls))


if __name__ == "__main__":
    unittest.main()
