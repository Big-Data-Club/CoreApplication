"""Offline regressions: an unrelated private submodule must not block a build."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("service_submodules", ROOT / "scripts/checkout-service-submodules.py")
checkout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkout)
INDEX = b"\0".join([
    b"160000 abc 0\tai-gateway", b"160000 abc 0\tfrontend",
    b"160000 abc 0\tdutylog", b"160000 abc 0\tai-service/mcp_skillset",
    b"160000 abc 0\tda-analytics", b"100644 abc 0\tlms-service/go.mod",
]) + b"\0"


class ServiceSubmoduleTests(unittest.TestCase):
    def test_normal_service_does_not_clone_gateway(self):
        self.assertEqual(checkout.required_submodules("./lms-service", INDEX), [])

    def test_frontend_is_ready_before_node_cache_setup(self):
        self.assertEqual(checkout.required_submodules("./frontend", INDEX), ["frontend"])

    def test_nested_build_context_initializes_its_ancestor(self):
        self.assertEqual(checkout.required_submodules("./dutylog/backend", INDEX), ["dutylog"])

    def test_ai_build_initializes_only_its_own_skills(self):
        self.assertEqual(checkout.required_submodules("ai-service", INDEX), ["ai-service/mcp_skillset"])

    def test_sibling_prefix_does_not_match(self):
        self.assertEqual(checkout.required_submodules("frontend-legacy", INDEX), [])

    def test_unsafe_or_root_context_rejected(self):
        for value in (".", "/frontend", "../frontend", "frontend/../ai-gateway"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                checkout.required_submodules(value, INDEX)

    def test_missing_gateway_token_fails_before_network(self):
        with patch.object(checkout.subprocess, "check_output", side_effect=lambda cmd, **kwargs: INDEX if cmd[1] == "ls-files" else b"AUTHORIZATION: basic synthetic-test-value"), patch.object(checkout.subprocess, "run") as run, patch.dict(os.environ, {"SUBMODULE_PAT_CONFIGURED": "false"}), redirect_stderr(io.StringIO()) as error:
            result = checkout.main(["ai-gateway"])
        self.assertEqual(result, 1)
        self.assertIn("SUBMODULE_PAT", error.getvalue())
        run.assert_not_called()

    def test_public_frontend_needs_no_private_gateway_secret(self):
        with patch.object(checkout.subprocess, "check_output", side_effect=lambda cmd, **kwargs: INDEX if cmd[1] == "ls-files" else b"AUTHORIZATION: basic synthetic-test-value"), patch.object(checkout.subprocess, "run") as run, patch.dict(os.environ, {"SUBMODULE_PAT_CONFIGURED": "false"}), redirect_stdout(io.StringIO()):
            self.assertEqual(checkout.main(["frontend"]), 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0], ["git", "submodule", "update", "--init", "--depth=1", "--recursive", "--", "frontend"])

    def test_gateway_with_configured_secret_is_pinned(self):
        with patch.object(checkout.subprocess, "check_output", side_effect=lambda cmd, **kwargs: INDEX if cmd[1] == "ls-files" else b"AUTHORIZATION: basic synthetic-test-value"), patch.object(checkout.subprocess, "run") as run, patch.dict(os.environ, {"SUBMODULE_PAT_CONFIGURED": "true"}), redirect_stdout(io.StringIO()):
            self.assertEqual(checkout.main(["ai-gateway"]), 0)
        self.assertEqual(run.call_args.args[0][-2:], ["--", "ai-gateway"])
        self.assertNotIn("--remote", run.call_args.args[0])

    def test_auth_is_inherited_by_children_without_token_in_command(self):
        with patch.object(checkout.subprocess, "check_output", return_value=b"AUTHORIZATION: basic synthetic-test-value"), patch.dict(os.environ, {}, clear=True):
            environment = checkout.submodule_environment()
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "4")
        self.assertEqual(environment["GIT_CONFIG_VALUE_0"], "git@github.com:")
        self.assertEqual(environment["GIT_CONFIG_VALUE_1"], "ssh://git@github.com/")
        self.assertEqual(environment["GIT_CONFIG_VALUE_3"], "AUTHORIZATION: basic synthetic-test-value")
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")

    def test_native_git_rewrites_ssh_urls_for_child_clones(self):
        with patch.object(checkout.subprocess, "check_output", return_value=b"AUTHORIZATION: basic synthetic-test-value"), patch.dict(os.environ, {}, clear=True):
            environment = checkout.submodule_environment()
        for url in ("git@github.com:example/private.git", "ssh://git@github.com/example/private.git"):
            result = subprocess.run(["git", "ls-remote", "--get-url", url], env=environment, text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), "https://github.com/example/private.git")

    def test_public_checkout_without_auth_header_still_works(self):
        with patch.object(checkout.subprocess, "check_output", side_effect=subprocess.CalledProcessError(1, ["git"])), patch.dict(os.environ, {}, clear=True):
            environment = checkout.submodule_environment()
        self.assertEqual(environment["GIT_CONFIG_COUNT"], "2")

    def test_clone_failure_is_not_silently_ignored(self):
        with patch.object(checkout.subprocess, "check_output", side_effect=lambda cmd, **kwargs: INDEX if cmd[1] == "ls-files" else b"AUTHORIZATION: basic synthetic-test-value"), patch.object(checkout.subprocess, "run", side_effect=subprocess.CalledProcessError(128, ["git"])), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
            self.assertEqual(checkout.main(["frontend"]), 1)
        self.assertIn("organization approval/SSO", error.getvalue())


if __name__ == "__main__":
    unittest.main()
