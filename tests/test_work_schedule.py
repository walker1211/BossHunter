"""Posting claims must not be confused with verified working hours."""

import tempfile
import sqlite3
from pathlib import Path
from unittest import TestCase

from bosshunter.db import (
    _migrate_work_schedule, get_db, insert_job, update_job_work_schedule_from_company,
)
from bosshunter.work_schedule import infer_work_schedule


class WorkScheduleTests(TestCase):
    def test_explicit_claims_and_unclear_text(self):
        cases = (
            ("五点半下班，双休", "", "double"),
            ("后端开发", "周末双休，法定节假日放假", "double"),
            ("后端开发", "年底前实行大小周", "alternate"),
            ("后端开发", "做六休一", "single"),
            ("后端开发", "周末加班按双倍工资计算", "unknown"),
            ("后端开发", "不双休，具体安排面议", "unclear"),
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

    def test_posting_priority_and_company_fallback(self):
        cases = (
            ("单休", "", "双休", "single", "job_posting"),
            ("", "大小周", "双休", "alternate", "job_posting"),
            ("", "双休或单休", "双休", "unclear", "job_posting"),
            ("", "不保证双休", "周休两天", "unclear", "job_posting"),
            ("", "双休，但不保证双休", "周末双休", "unclear", "job_posting"),
            ("", "不双休，做六休一", "双休", "single", "job_posting"),
            ("", "否定单休，实际做五休二", "", "double", "job_posting"),
            ("", "不实行大小周", "双休", "unclear", "job_posting"),
            ("", "9:00-18:00，五险一金", "每周休息2天", "double", "company_profile"),
            ("", "9:00-18:00，五险一金", "", "unknown", ""),
            ("", "", "做五休二", "double", "company_profile"),
        )
        for title, jd, company, expected, source in cases:
            with self.subTest(title=title, jd=jd, company=company):
                actual, actual_source, evidence = infer_work_schedule(title, jd, company)
                self.assertEqual((actual, actual_source), (expected, source))
                self.assertEqual(bool(evidence), bool(source))

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
                self.assertTrue(insert_job(conn, {
                    "id": "company-job", "title": "Go 后端", "company": "示例公司",
                    "jd": "负责API开发。", "company_url": "https://example.test/company",
                    "company_work_schedule": "周末双休", "work_schedule": "single",
                }))
                company_row = conn.execute(
                    "SELECT company_url, company_work_schedule, work_schedule, work_schedule_source "
                    "FROM jobs WHERE id = 'company-job'"
                ).fetchone()
                self.assertEqual(tuple(company_row), (
                    "https://example.test/company", "周末双休", "double", "company_profile",
                ))
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
            _migrate_work_schedule(conn)
            self.assertEqual(conn.execute("SELECT score FROM jobs WHERE id = 'old'").fetchone()[0], 82)
        finally:
            conn.close()

    def test_migration_preserves_existing_claims_and_only_adds_company_columns(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, title TEXT, jd TEXT, "
                         "work_schedule TEXT, work_schedule_source TEXT, work_schedule_evidence TEXT, "
                         "score INTEGER, status TEXT, greeting TEXT)")
            conn.executemany("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                ("manual", "Go", "双休", "single", "manual", "人工确认", 91, "ready", "你好"),
                ("unknown", "Go", "双休", "unknown", "", "", 42, "pending", "等待"),
            ))
            _migrate_work_schedule(conn)
            _migrate_work_schedule(conn)
            rows = conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()
            self.assertEqual((rows[0]["work_schedule"], rows[0]["work_schedule_source"],
                              rows[0]["work_schedule_evidence"]), ("single", "manual", "人工确认"))
            self.assertEqual((rows[1]["work_schedule"], rows[1]["company_work_schedule"]), ("unknown", ""))
            self.assertEqual((rows[0]["score"], rows[0]["status"], rows[0]["greeting"]), (91, "ready", "你好"))
        finally:
            conn.close()

    def test_company_update_only_for_visible_unknown_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = get_db(Path(tmp) / "jobs.db")
            try:
                for job_id, jd in (("unknown", "API开发"), ("single", "单休"),
                                   ("unclear", "不保证双休"), ("deleted", "API开发"),
                                   ("annotated", "API开发")):
                    insert_job(conn, {"id": job_id, "title": "Go", "company": "公司", "jd": jd})
                conn.execute("UPDATE jobs SET score = 88, status = 'ready', greeting = '你好', "
                             "updated_at = '2020-01-01' WHERE id = 'unknown'")
                conn.execute("UPDATE jobs SET deleted_at = '2020-01-01' WHERE id = 'deleted'")
                conn.execute("UPDATE jobs SET work_schedule_evidence = '人工待核验' WHERE id = 'annotated'")
                conn.commit()
                self.assertTrue(update_job_work_schedule_from_company(conn, "unknown", "url", "团队氛围好"))
                self.assertEqual(tuple(conn.execute(
                    "SELECT work_schedule, company_work_schedule, score, status, greeting, updated_at "
                    "FROM jobs WHERE id = 'unknown'").fetchone()),
                    ("unknown", "团队氛围好", 88, "ready", "你好", "2020-01-01"))
                self.assertTrue(update_job_work_schedule_from_company(conn, "unknown", "url", "周末双休"))
                self.assertEqual(tuple(conn.execute(
                    "SELECT work_schedule, work_schedule_source, company_url, score, status, greeting, updated_at "
                    "FROM jobs WHERE id = 'unknown'").fetchone()),
                    ("double", "company_profile", "url", 88, "ready", "你好", "2020-01-01"))
                for job_id in ("unknown", "single", "unclear", "deleted", "annotated", "missing"):
                    self.assertFalse(update_job_work_schedule_from_company(conn, job_id, "other", "双休"))
            finally:
                conn.close()
