"""Opt-in transaction-only tests against the local Compose demo database."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "scripts/seed-demo-participants.sql").read_text()
BODY = "\n".join(line for line in SQL.splitlines() if line not in ("BEGIN;", "COMMIT;"))


@unittest.skipUnless(os.environ.get("LIVEGUARD_TEST_LOCAL_SEED") == "1",
                     "Opt in only on the local demo DB with LIVEGUARD_TEST_LOCAL_SEED=1")
class ParticipantSeedTests(unittest.TestCase):
    def execute(self, sql):
        return subprocess.run(
            ["docker", "compose", "exec", "-T", "db", "sh", "-c",
             'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
            cwd=ROOT, input=sql, text=True, capture_output=True, timeout=30)

    def test_exact_200_and_idempotency_in_rolled_back_transaction(self):
        result = self.execute("BEGIN;\n" + BODY + "\n" + BODY
            + "\nSELECT 'seed-count:' || count(*) FROM platform.users "
              "WHERE id BETWEEN '10000000-0000-4000-8001-000000000001'::uuid "
              "AND '10000000-0000-4000-8001-000000000200'::uuid;\nROLLBACK;\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("seed-count:200", result.stdout)
        self.assertIn("INSERT 0 0", result.stdout)

    def test_missing_viewer_fails_not_silent_zero_insert(self):
        result = self.execute(
            "BEGIN; UPDATE platform.users SET username='seed-test-viewer' WHERE username='viewer';\n"
            + BODY + "\nROLLBACK;")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Local viewer seed is required", result.stderr)

    def test_existing_conflict_is_not_overwritten(self):
        result = self.execute("BEGIN;\n" + BODY
            + "\nUPDATE platform.users SET nickname='conflicting-test-value' WHERE username='p001';\n"
            + BODY + "\nROLLBACK;")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Participant seed conflict", result.stderr)


if __name__ == "__main__":
    unittest.main()
