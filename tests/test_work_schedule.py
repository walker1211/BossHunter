"""Posting claims must not be confused with verified working hours."""

import tempfile
import sqlite3
from pathlib import Path
from unittest import TestCase

from bosshunter.db import _migrate_work_schedule, get_db, insert_job
from bosshunter.work_schedule import infer_work_schedule


class WorkScheduleTests(TestCase):
    def test_explicit_claims_and_unclear_text(self):
        cases = (
            ("五点半下班，双休", "", "double"),
            ("后端开发", "周末双休，法定节假日放假", "double"),
            ("后端开发", "年底前实行大小周", "alternate"),
            ("后端开发", "做六休一", "single"),
            ("后端开发", "周末加班按双倍工资计算", "unknown"),
            ("后端开发", "不双休，具体安排面议", "unknown"),
            ("后端开发", "单双休轮换", "alternate"),
            ("后端开发", "双休或大小周，视项目而定", "unclear"),
        )
        for title, jd, expected in cases:
            with self.subTest(title=title, jd=jd):
                schedule, source, evidence = infer_work_schedule(title, jd)
                self.assertEqual(schedule, expected)
                self.assertEqual(source, "job_posting" if expected != "unknown" else "")
                if source:
                    self.assertTrue(evidence)

    def test_new_jobs_store_claim_and_source_without_changing_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = get_db(Path(tmp) / "jobs.db")
            try:
                self.assertTrue(insert_job(conn, {
                    "id": "double-job", "title": "PHP后端（双休）", "company": "示例公司",
                    "jd": "负责API开发。", "city": "深圳",
                }))
                row = conn.execute(
                    "SELECT work_schedule, work_schedule_source, work_schedule_evidence, score "
                    "FROM jobs WHERE id = 'double-job'"
                ).fetchone()
                self.assertEqual(row["work_schedule"], "double")
                self.assertEqual(row["work_schedule_source"], "job_posting")
                self.assertIn("双休", row["work_schedule_evidence"])
                self.assertEqual(row["score"], 0)
            finally:
                conn.close()

    def test_existing_rows_backfill_without_changing_score(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, title TEXT, jd TEXT, score INTEGER)")
            conn.execute("INSERT INTO jobs VALUES ('old', 'Go 后端', '周末双休', 82)")
            _migrate_work_schedule(conn)
            row = conn.execute(
                "SELECT work_schedule, work_schedule_source, work_schedule_evidence, score "
                "FROM jobs WHERE id = 'old'"
            ).fetchone()
            self.assertEqual((row["work_schedule"], row["work_schedule_source"], row["score"]),
                             ("double", "job_posting", 82))
            self.assertIn("双休", row["work_schedule_evidence"])
        finally:
            conn.close()
