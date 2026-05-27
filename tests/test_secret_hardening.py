from __future__ import annotations

import asyncio
import io
import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.async_file_io import (
    copy_fileobj_to_temp_async,
    read_json_file_async,
    read_file_bytes_async,
    remove_files_best_effort_async,
    write_async_iter_bytes_to_file,
)
from common.audio_effects import get_audio_filter
from common.async_process import AsyncProcessError, run_process_checked
from common.html_utils import escape_html
from common.secret_redaction import (
    install_logging_redaction,
    redact_secrets,
    secret_fingerprint,
)
from async_blocking_audit import build_async_blocking_report
from cookie_artifact_audit import build_cookie_artifact_report
from env_contract_audit import build_env_contract
from env_example_validator import validate_env_example
from gitignore_policy_audit import build_gitignore_policy_report
from import_graph_audit import build_import_graph_report
from local_artifact_audit import build_local_artifact_report
from python_quality_audit import build_python_quality_report
from repository_health import build_repository_health
from secret_scan import (
    TOKEN_PATTERN,
    count_secret_patterns,
    count_token_patterns,
    has_excluded_suffix,
    is_secret_env_file,
    should_scan,
    should_scan_all,
)
from secret_artifact_inventory import build_inventory, classify_artifact
from secret_artifact_redactor import redact_inventory
from secret_remediation_plan import build_plan, severity_for_count
from secret_findings_baseline import compare_to_baseline, normalize_inventory
from security_paths import PYTHON_QUALITY_REPORT, SECURITY_REPORTS_DIR, SECURITY_STATUS_REPORT
from security_report_validator import count_text_secret_patterns, schema_missing_keys
from security_report_utils import atomic_write_json
from security_status import build_status
from source_integrity_audit import build_source_integrity_report


SYNTHETIC_TELEGRAM_TOKEN = "1234567890:" + ("A" * 35)
SYNTHETIC_BEARER_TOKEN = "Bearer " + ("a" * 36)
SYNTHETIC_HF_TOKEN = "hf_" + ("A" * 30)
SYNTHETIC_GITHUB_TOKEN = "ghp_" + ("B" * 30)
SYNTHETIC_OPENAI_TOKEN = "sk-" + ("C" * 30)
SYNTHETIC_GROQ_TOKEN = "gsk_" + ("D" * 30)


class SecretRedactionTests(unittest.TestCase):
    def test_redacts_telegram_and_bearer_values(self) -> None:
        text = (
            f"https://api.telegram.org/file/bot{SYNTHETIC_TELEGRAM_TOKEN}/file.dat "
            f"{SYNTHETIC_BEARER_TOKEN} "
            f"{SYNTHETIC_HF_TOKEN} "
            f"{SYNTHETIC_GITHUB_TOKEN} "
            f"{SYNTHETIC_OPENAI_TOKEN} "
            f"{SYNTHETIC_GROQ_TOKEN}"
        )

        redacted = redact_secrets(text)

        self.assertNotIn(SYNTHETIC_TELEGRAM_TOKEN, redacted)
        self.assertNotIn(SYNTHETIC_BEARER_TOKEN, redacted)
        self.assertNotIn(SYNTHETIC_HF_TOKEN, redacted)
        self.assertNotIn(SYNTHETIC_GITHUB_TOKEN, redacted)
        self.assertNotIn(SYNTHETIC_OPENAI_TOKEN, redacted)
        self.assertNotIn(SYNTHETIC_GROQ_TOKEN, redacted)
        self.assertIn("<telegram-token-redacted>", redacted)
        self.assertIn("Bearer <redacted>", redacted)
        self.assertIn("<api-token-redacted>", redacted)

    def test_logging_filter_preserves_numeric_format_args(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logging.basicConfig(
            level=logging.INFO,
            handlers=[handler],
            force=True,
            format="%(message)s",
        )
        install_logging_redaction()

        logging.info("token=%s count=%d", SYNTHETIC_TELEGRAM_TOKEN, 7)
        output = stream.getvalue()

        self.assertNotIn(SYNTHETIC_TELEGRAM_TOKEN, output)
        self.assertIn("<telegram-token-redacted>", output)
        self.assertIn("count=7", output)

    def test_secret_fingerprint_is_stable_and_non_reversible_text(self) -> None:
        first = secret_fingerprint(SYNTHETIC_TELEGRAM_TOKEN)
        second = secret_fingerprint(SYNTHETIC_TELEGRAM_TOKEN)

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("secret-"))
        self.assertNotIn(":", first)
        self.assertNotIn(SYNTHETIC_TELEGRAM_TOKEN[:8], first)


class SecretScanTests(unittest.TestCase):
    def test_token_pattern_matches_embedded_telegram_urls(self) -> None:
        line = f"url=https://api.telegram.org/file/bot{SYNTHETIC_TELEGRAM_TOKEN}/x"

        matches = TOKEN_PATTERN.findall(line)

        self.assertEqual(matches, [SYNTHETIC_TELEGRAM_TOKEN])
        self.assertEqual(count_token_patterns(line), 1)
        self.assertEqual(count_token_patterns("plain line without separator"), 0)

    def test_multi_pattern_counter_reports_secret_classes(self) -> None:
        line = " ".join(
            [
                SYNTHETIC_TELEGRAM_TOKEN,
                SYNTHETIC_BEARER_TOKEN,
                SYNTHETIC_HF_TOKEN,
                SYNTHETIC_GITHUB_TOKEN,
                SYNTHETIC_OPENAI_TOKEN,
                SYNTHETIC_GROQ_TOKEN,
            ]
        )

        counts = count_secret_patterns(line)

        self.assertEqual(counts["telegram_bot_token"], 1)
        self.assertEqual(counts["bearer_token"], 1)
        self.assertEqual(counts["huggingface_token"], 1)
        self.assertEqual(counts["github_token"], 1)
        self.assertEqual(counts["openai_token"], 1)
        self.assertEqual(counts["groq_token"], 1)

    def test_default_scan_excludes_env_and_historical_artifacts(self) -> None:
        self.assertFalse(should_scan(Path(".env")))
        self.assertFalse(should_scan(Path(".env.local")))
        self.assertFalse(should_scan(Path(".env.production")))
        self.assertFalse(should_scan(Path("site.log")))
        self.assertFalse(should_scan(Path("recovery.sql")))
        self.assertFalse(should_scan(Path("New Text Document (2).txt")))
        self.assertTrue(should_scan(Path("main.py")))
        self.assertTrue(should_scan(Path(".env.example")))

    def test_all_scan_excludes_env_unless_requested(self) -> None:
        self.assertFalse(should_scan_all(Path(".env"), include_env=False))
        self.assertFalse(should_scan_all(Path(".env.local"), include_env=False))
        self.assertTrue(should_scan_all(Path(".env"), include_env=True))
        self.assertTrue(should_scan_all(Path(".env.local"), include_env=True))
        self.assertFalse(should_scan_all(Path("dvach_bot.db"), include_env=True))
        self.assertFalse(should_scan_all(Path("dvach_bot.db.cleanup_backup_1768700542"), include_env=True))
        self.assertFalse(should_scan_all(Path("TGACH_Backup_2026-04-20_16-09.zip.003"), include_env=True))
        self.assertFalse(should_scan_all(Path("site_tgach/GeoLite2-Country.mmdb"), include_env=True))
        self.assertFalse(should_scan_all(Path("common.rar"), include_env=True))
        self.assertTrue(should_scan_all(Path("логи.txt"), include_env=False))


    def test_env_example_is_not_treated_as_secret_env_file(self) -> None:
        self.assertTrue(is_secret_env_file(Path(".env")))
        self.assertTrue(is_secret_env_file(Path(".env.local")))
        self.assertFalse(is_secret_env_file(Path(".env.example")))

    def test_excluded_suffix_checks_all_suffix_segments(self) -> None:
        self.assertTrue(has_excluded_suffix(Path("backup.db.cleanup_backup_1"), {".db"}))
        self.assertTrue(has_excluded_suffix(Path("archive.zip.003"), {".zip"}))
        self.assertFalse(has_excluded_suffix(Path("script.py"), {".db"}))


class SecretArtifactInventoryTests(unittest.TestCase):
    def test_inventory_reports_counts_without_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = SYNTHETIC_TELEGRAM_TOKEN
            (root / "leak.txt").write_text(f"first {token}\nsecond {token}\n", encoding="utf-8")
            (root / ".env.local").write_text(f"BOT_TOKEN={token}\n", encoding="utf-8")
            (root / "security_reports").mkdir()
            (root / "security_reports" / "old.json").write_text(f"{token}\n", encoding="utf-8")

            findings = build_inventory(root, include_env=False)
            paths = [item["path"] for item in findings]

            self.assertEqual(paths, ["leak.txt"])
            self.assertEqual(findings[0]["secret_like_count"], 2)
            self.assertNotIn(token, str(findings))

    def test_inventory_can_include_env_on_explicit_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = SYNTHETIC_TELEGRAM_TOKEN
            (root / ".env.local").write_text(f"BOT_TOKEN={token}\n", encoding="utf-8")

            findings = build_inventory(root, include_env=True)

            self.assertEqual(findings[0]["path"], ".env.local")
            self.assertEqual(findings[0]["category"], "env")

    def test_artifact_classification(self) -> None:
        self.assertEqual(classify_artifact(Path(".env.local")), "env")
        self.assertEqual(classify_artifact(Path("recovery.sql")), "sql-dump")
        self.assertEqual(classify_artifact(Path("site.log")), "runtime-log")
        self.assertEqual(classify_artifact(Path("логи.txt")), "text-log")


    def test_redactor_writes_sanitized_copy_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            token = SYNTHETIC_TELEGRAM_TOKEN
            bearer = SYNTHETIC_BEARER_TOKEN
            (root / "leak.txt").write_text(f"{token}\n{bearer}\n", encoding="utf-8")

            manifest = redact_inventory(root, include_env=False)
            item = manifest["redacted_files"][0]
            redacted_path = root / item["redacted_path"]
            redacted_text = redacted_path.read_text(encoding="utf-8")

            self.assertFalse(manifest["contains_secret_values"])
            self.assertEqual(item["secret_like_count"], 2)
            self.assertNotIn(token, redacted_text)
            self.assertNotIn(bearer, redacted_text)
            self.assertIn("<telegram-token-redacted>", redacted_text)
            self.assertIn("Bearer <redacted>", redacted_text)

    def test_redactor_removes_stale_generated_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_root = root / "security_reports" / "redacted_artifacts"
            stale = output_root / "old.db.cleanup_backup_1"
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_text("stale", encoding="utf-8")
            (root / "leak.txt").write_text(f"{SYNTHETIC_TELEGRAM_TOKEN}\n", encoding="utf-8")

            redact_inventory(root, include_env=False, output_root=output_root)

            self.assertFalse(stale.exists())
            self.assertTrue((output_root / "leak.txt").exists())


class SecurityReportWorkflowTests(unittest.TestCase):
    def test_escape_html_is_shared_without_importing_application_entrypoint(self) -> None:
        self.assertEqual(
            escape_html("<tag attr=\"1\">&"),
            "&lt;tag attr=&quot;1&quot;&gt;&amp;",
        )

    def test_async_process_helper_accepts_success_exit(self) -> None:
        async def run_case() -> None:
            await run_process_checked([sys.executable, "-c", "raise SystemExit(0)"], timeout=5)

        asyncio.run(run_case())

    def test_async_process_helper_reports_non_zero_exit(self) -> None:
        async def run_case() -> None:
            with self.assertRaises(AsyncProcessError) as caught:
                await run_process_checked([sys.executable, "-c", "raise SystemExit(3)"], timeout=5)
            self.assertEqual(caught.exception.returncode, 3)

        asyncio.run(run_case())

    def test_audio_effect_filters_are_shared(self) -> None:
        self.assertIsNotNone(get_audio_filter("anon"))
        self.assertIsNone(get_audio_filter("unknown"))

    def test_async_file_io_helpers_copy_read_and_cleanup(self) -> None:
        async def run_case() -> None:
            path = await copy_fileobj_to_temp_async(io.BytesIO(b"audio-bytes"), suffix=".ogg")
            try:
                self.assertTrue(Path(path).exists())
                self.assertEqual(await read_file_bytes_async(path), b"audio-bytes")
            finally:
                await remove_files_best_effort_async((path,))
            self.assertFalse(Path(path).exists())

        asyncio.run(run_case())

    def test_async_file_io_helpers_read_json_and_stream_bytes(self) -> None:
        async def chunks():
            yield b"left"
            yield b"-right"

        async def run_case() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                json_path = root / "data.json"
                stream_path = root / "stream.bin"
                await asyncio.to_thread(json_path.write_text, '{"value": 7}', encoding="utf-8")

                self.assertEqual(await read_json_file_async(str(json_path)), {"value": 7})
                await write_async_iter_bytes_to_file(chunks(), str(stream_path))
                self.assertEqual(await asyncio.to_thread(stream_path.read_bytes), b"left-right")

        asyncio.run(run_case())

    def test_atomic_write_json_replaces_existing_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "report.json"
            atomic_write_json(path, {"value": 1})
            atomic_write_json(path, {"value": 2})

            data = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(data["value"], 2)
            self.assertFalse(path.with_name("report.json.tmp").exists())

    def test_remediation_plan_contains_actions_without_secret_values(self) -> None:
        inventory = {
            "files": [
                {
                    "path": "leak.txt",
                    "secret_like_count": 12,
                    "pattern_counts": {"telegram_bot_token": 12},
                }
            ]
        }
        manifest = {
            "redacted_files": [
                {
                    "source_path": "leak.txt",
                    "redacted_path": "security_reports/redacted_artifacts/leak.txt",
                }
            ]
        }

        plan = build_plan(inventory, manifest)
        serialized = json.dumps(plan, ensure_ascii=False)

        self.assertFalse(plan["contains_secret_values"])
        self.assertFalse(plan["destructive_action_performed"])
        self.assertEqual(plan["action_count"], 1)
        self.assertEqual(plan["actions"][0]["severity"], "high")
        self.assertIn("rotate every credential", plan["actions"][0]["required_manual_actions"][0])
        self.assertNotIn(SYNTHETIC_TELEGRAM_TOKEN, serialized)

    def test_remediation_severity_thresholds(self) -> None:
        self.assertEqual(severity_for_count(1), "medium")
        self.assertEqual(severity_for_count(10), "high")
        self.assertEqual(severity_for_count(100), "critical")

    def test_baseline_detects_new_artifacts_and_count_growth(self) -> None:
        baseline = normalize_inventory(
            {
                "files": [
                    {
                        "path": "old.txt",
                        "secret_like_count": 1,
                        "pattern_counts": {"telegram_bot_token": 1},
                    }
                ]
            }
        )
        current = normalize_inventory(
            {
                "files": [
                    {
                        "path": "old.txt",
                        "secret_like_count": 2,
                        "pattern_counts": {"telegram_bot_token": 2},
                    },
                    {
                        "path": "new.txt",
                        "secret_like_count": 1,
                        "pattern_counts": {"bearer_token": 1},
                    },
                ]
            }
        )

        issues = compare_to_baseline(current, baseline)

        self.assertIn("total_secret_like_count_increased", issues)
        self.assertIn("secret_count_increased:old.txt", issues)
        self.assertIn("pattern_count_increased:old.txt:telegram_bot_token", issues)
        self.assertIn("new_secret_artifact:new.txt", issues)

    def test_validator_counts_secret_patterns_without_printing_values(self) -> None:
        text = f"safe\n{SYNTHETIC_TELEGRAM_TOKEN}\n{SYNTHETIC_BEARER_TOKEN}\n"

        self.assertEqual(count_text_secret_patterns(text), 2)

    def test_env_example_validator_detects_sensitive_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env.example"
            path.write_text(
                "BOT_TOKEN=value\n"
                "BOT_TOKEN=\n"
                "BROKEN_LINE\n",
                encoding="utf-8",
            )

            issues = validate_env_example(path)

            self.assertIn("sensitive_key_has_default:BOT_TOKEN:1", issues)
            self.assertIn("duplicate_key:BOT_TOKEN:2", issues)
            self.assertIn("malformed_line:3", issues)

    def test_env_example_validator_accepts_blank_sensitive_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env.example"
            path.write_text("BOT_TOKEN=\nHF_TOKEN=\nPYTHONUNBUFFERED=\n", encoding="utf-8")

            self.assertEqual(validate_env_example(path), [])

    def test_env_contract_audit_detects_missing_literal_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.example").write_text(
                "FOO=\n"
                "SECRET_KEY=\n",
                encoding="utf-8",
            )
            (root / "app.py").write_text(
                "import os\n"
                "a = os.getenv('FOO')\n"
                "b = os.environ.get('SECRET_KEY')\n"
                "c = os.environ['BAR']\n",
                encoding="utf-8",
            )

            report = build_env_contract(root)

            self.assertFalse(report["contains_secret_values"])
            self.assertEqual(report["used_count"], 3)
            self.assertEqual(report["missing_keys"], ["BAR"])
            self.assertIn("app.py:2", report["usages"]["FOO"])
            self.assertIn("app.py:3", report["usages"]["SECRET_KEY"])
            self.assertIn("app.py:4", report["usages"]["BAR"])

    def test_env_contract_audit_records_dynamic_references_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.example").write_text("FOO=\n", encoding="utf-8")
            (root / "app.py").write_text(
                "import os\n"
                "name = 'FOO'\n"
                "value = os.getenv(name)\n",
                encoding="utf-8",
            )

            report = build_env_contract(root)

            self.assertEqual(report["missing_keys"], [])
            self.assertEqual(report["dynamic_reference_count"], 1)
            self.assertEqual(report["dynamic_references"], ["app.py:3:os.getenv"])

    def test_source_integrity_audit_accepts_clean_python(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("value = 1\n", encoding="utf-8")

            report = build_source_integrity_report(root)

            self.assertFalse(report["contains_secret_values"])
            self.assertEqual(report["checked_count"], 1)
            self.assertEqual(report["issue_count"], 0)

    def test_source_integrity_audit_detects_nul_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.py").write_bytes(b"value = 1\x00\n")

            report = build_source_integrity_report(root)

            self.assertEqual(report["issue_count"], 1)
            self.assertEqual(report["issues"][0]["path"], "broken.py")
            self.assertEqual(report["issues"][0]["issue"], "nul_byte")

    def test_source_integrity_audit_detects_syntax_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.py").write_text("def nope(:\n", encoding="utf-8")

            report = build_source_integrity_report(root)

            self.assertEqual(report["issue_count"], 1)
            self.assertEqual(report["issues"][0]["path"], "broken.py")
            self.assertEqual(report["issues"][0]["issue"], "syntax_error")

    def test_cookie_artifact_audit_reports_keys_without_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cookie_value = "sensitive-cookie-value"
            (root / "cookies.json").write_text(
                json.dumps(
                    {
                        "cf_clearance": cookie_value,
                        "ageallow": "1",
                        "user_agent": "test-agent",
                    }
                ),
                encoding="utf-8",
            )

            report = build_cookie_artifact_report(root)
            serialized = json.dumps(report, ensure_ascii=False)

            self.assertFalse(report["contains_secret_values"])
            self.assertEqual(report["cookie_file_count"], 1)
            self.assertEqual(report["sensitive_file_count"], 1)
            self.assertEqual(report["files"][0]["sensitive_keys"], ["cf_clearance"])
            self.assertTrue(report["files"][0]["has_user_agent"])
            self.assertNotIn(cookie_value, serialized)
            self.assertNotIn("test-agent", serialized)

    def test_cookie_artifact_audit_excludes_generated_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "security_reports"
            report_dir.mkdir()
            (report_dir / "cookies.json").write_text('{"session": "value"}\n', encoding="utf-8")

            report = build_cookie_artifact_report(root)

            self.assertEqual(report["cookie_file_count"], 0)
            self.assertEqual(report["sensitive_file_count"], 0)

    def test_repository_health_reports_missing_git_without_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_repository_health(Path(tmp))

            self.assertFalse(report["contains_secret_values"])
            self.assertEqual(report["issue_count"], 1)
            self.assertIn("missing_git_dir", report["issues"])
            self.assertFalse(report["git_status_ok"])

    def test_local_artifact_audit_reports_metadata_without_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secret_value = "local-only-value"
            (root / ".env").write_text(f"BOT_TOKEN={secret_value}\n", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "db_backup_2026-01-01_00-00.sql.gz").write_bytes(b"backup")
            (root / "sessions").mkdir()
            (root / "sessions" / "client.session").write_bytes(b"session-bytes")

            report = build_local_artifact_report(root)
            serialized = json.dumps(report, ensure_ascii=False)
            categories = {item["category"] for item in report["artifacts"]}

            self.assertFalse(report["contains_secret_values"])
            self.assertEqual(report["artifact_count"], 3)
            self.assertIn("env", categories)
            self.assertIn("database-backup", categories)
            self.assertIn("session-directory", categories)
            self.assertNotIn(secret_value, serialized)
            self.assertNotIn("session-bytes", serialized)

    def test_gitignore_policy_audit_detects_missing_required_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text(".env\n.env.*\n!.env.example\n", encoding="utf-8")

            report = build_gitignore_policy_report(root)

            self.assertFalse(report["contains_secret_values"])
            self.assertGreater(report["missing_count"], 0)
            self.assertIn("sessions/", report["missing_patterns"])
            self.assertIn("cookies*.json", report["missing_patterns"])

    def test_python_quality_audit_flags_large_file_and_function(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "\n".join(f"    value_{i} = {i}" for i in range(130))
            (root / "large.py").write_text(
                "def oversized():\n"
                f"{body}\n",
                encoding="utf-8",
            )

            report = build_python_quality_report(root)

            self.assertFalse(report["contains_secret_values"])
            self.assertEqual(report["checked_count"], 1)
            self.assertEqual(report["large_file_count"], 0)
            self.assertEqual(report["flagged_function_count"], 1)
            self.assertEqual(report["flagged_functions"][0]["name"], "oversized")

    def test_report_schema_validation_detects_missing_quality_keys(self) -> None:
        data = {
            "generated_utc": "2026-05-09T00:00:00+00:00",
            "contains_secret_values": False,
        }

        missing = schema_missing_keys(PYTHON_QUALITY_REPORT, data)

        self.assertIn("checked_count", missing)
        self.assertIn("critical_file_count", missing)

    def test_import_graph_audit_detects_project_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("import b\n", encoding="utf-8")
            (root / "b.py").write_text("import a\n", encoding="utf-8")

            report = build_import_graph_report(root)

            self.assertFalse(report["contains_secret_values"])
            self.assertEqual(report["module_count"], 2)
            self.assertEqual(report["cycle_count"], 1)
            self.assertEqual(report["cycles"], [["a", "b", "a"]])

    def test_async_blocking_audit_detects_high_risk_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "worker.py").write_text(
                "import time\n"
                "async def run():\n"
                "    time.sleep(1)\n",
                encoding="utf-8",
            )

            report = build_async_blocking_report(root)

            self.assertFalse(report["contains_secret_values"])
            self.assertEqual(report["checked_count"], 1)
            self.assertEqual(report["high_count"], 1)
            self.assertEqual(report["findings"][0]["call"], "time.sleep")

    def test_status_builder_reports_not_strict_ready_when_actions_exist(self) -> None:
        status = build_status(include_summary_validation=False)

        self.assertIn("strict_ready", status)
        self.assertFalse(status["contains_secret_values"])
        self.assertIn("strict_blockers", status)
        self.assertIn("python_quality_critical_count", status)
        self.assertIn("import_graph_cycle_count", status)
        self.assertIn("async_blocking_high_count", status)

    def test_security_paths_stay_under_report_directory(self) -> None:
        self.assertTrue(str(SECURITY_STATUS_REPORT).startswith(str(SECURITY_REPORTS_DIR)))


if __name__ == "__main__":
    unittest.main()
