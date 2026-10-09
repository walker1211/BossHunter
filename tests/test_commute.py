"""Verified map routes update only commute fields on existing jobs."""

import sqlite3

import pytest

from bosshunter.db import _migrate_work_location, get_db, insert_job, update_job_commute


ROUTE_URL = "https://uri.amap.com/navigation?from=1,2,start&to=3,4,end&mode=bus"
ROUTE = {
    "origin": "地铁站",
    "minutes": 33,
    "distance_m": 12500,
    "mode": "transit",
    "source_url": ROUTE_URL,
    "checked_at": "2026-10-09T12:30:00Z",
}


def test_legacy_migration_keeps_existing_minutes_and_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "CREATE TABLE jobs (id TEXT PRIMARY KEY, work_location TEXT, commute_origin TEXT, "
            "commute_minutes INTEGER, commute_mode TEXT, commute_checked_at TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO jobs VALUES ('old', '南山', '地铁站', 33, 'transit', '2026-10-08T10:00:00')"
        )
        _migrate_work_location(conn)
        _migrate_work_location(conn)
        row = conn.execute("SELECT * FROM jobs WHERE id = 'old'").fetchone()
        assert row["commute_minutes"] == 33
        assert row["commute_distance_m"] is None
        assert row["commute_source_url"] is None
        assert row["commute_origin"] == "地铁站"
        assert row["commute_mode"] == "transit"
    finally:
        conn.close()


@pytest.fixture
def jobs(tmp_path):
    conn = get_db(tmp_path / "jobs.db")
    for job_id in ("target", "other", "deleted"):
        assert insert_job(conn, {"id": job_id, "title": "Go", "company": "示例", "jd": "开发"})
    conn.execute(
        "UPDATE jobs SET score = 87, status = 'ready', greeting = '你好', updated_at = '2020-01-01', "
        "work_location = '南山' WHERE id = 'target'"
    )
    conn.execute("UPDATE jobs SET deleted_at = '2020-01-01' WHERE id = 'deleted'")
    conn.commit()
    yield conn
    conn.close()


def test_update_preserves_workflow_and_other_rows(jobs):
    before_other = dict(jobs.execute("SELECT * FROM jobs WHERE id = 'other'").fetchone())
    assert update_job_commute(jobs, "target", **ROUTE)
    row = jobs.execute("SELECT * FROM jobs WHERE id = 'target'").fetchone()
    assert (row["commute_origin"], row["commute_minutes"], row["commute_distance_m"],
            row["commute_mode"], row["commute_source_url"], row["commute_checked_at"]) == (
        "地铁站", 33, 12500, "transit", ROUTE_URL, "2026-10-09T12:30:00Z"
    )
    assert (row["score"], row["status"], row["greeting"], row["updated_at"], row["work_location"]) == (
        87, "ready", "你好", "2020-01-01", "南山"
    )
    assert dict(jobs.execute("SELECT * FROM jobs WHERE id = 'other'").fetchone()) == before_other
    assert update_job_commute(jobs, "target", **{**ROUTE, "minutes": None, "distance_m": 0})
    assert jobs.execute("SELECT commute_minutes, commute_distance_m FROM jobs WHERE id = 'target'").fetchone()[:] == (None, 0)


def test_missing_and_deleted_jobs_return_false(jobs):
    assert not update_job_commute(jobs, "missing", **ROUTE)
    assert not update_job_commute(jobs, "deleted", **ROUTE)
    assert jobs.execute("SELECT commute_minutes FROM jobs WHERE id = 'deleted'").fetchone()[0] is None


@pytest.mark.parametrize("overrides", [
    {"origin": ""}, {"mode": " "}, {"checked_at": "bad"}, {"checked_at": ""},
    {"minutes": None, "distance_m": None}, {"minutes": True}, {"minutes": -1},
    {"minutes": 1441}, {"minutes": 1.5}, {"distance_m": False},
    {"distance_m": -1}, {"distance_m": 1000001}, {"distance_m": "12"},
])
def test_invalid_values_do_not_write(jobs, overrides):
    before = dict(jobs.execute("SELECT * FROM jobs WHERE id = 'target'").fetchone())
    with pytest.raises(ValueError):
        update_job_commute(jobs, "target", **{**ROUTE, **overrides})
    assert dict(jobs.execute("SELECT * FROM jobs WHERE id = 'target'").fetchone()) == before


@pytest.mark.parametrize("url", [
    "http://www.amap.com/dir?from=a&to=b", "https://evil.amap.com/dir",
    "https://user:pass@www.amap.com/dir", "https://www.amap.com:443/dir",
    "https://www.amap.com:bad/dir", "https://www.amap.com/dir#route",
    "https://uri.amap.com/other", "https://ditu.amap.com/other",
    "https://www.amap.com/dir?key=secret", "https://www.amap.com/dir?token=secret",
    "https://www.amap.com/dir?from=a&access_token=secret",
    "https://www.amap.com/dir?unknown=1", "https://www.amap.com/?from",
    "https://www.amap.com/account", "https://www.amap.com/route?r=abc",
    "not a url", "",
])
def test_invalid_urls_do_not_write_or_echo_url(jobs, url):
    before = dict(jobs.execute("SELECT * FROM jobs WHERE id = 'target'").fetchone())
    with pytest.raises(ValueError) as error:
        update_job_commute(jobs, "target", **{**ROUTE, "source_url": url})
    assert str(error.value) == "无效的地图路线链接"
    assert dict(jobs.execute("SELECT * FROM jobs WHERE id = 'target'").fetchone()) == before


@pytest.mark.parametrize("url", [
    "https://www.amap.com/",
    "https://uri.amap.com/navigation?from%5Bname%5D=A&to%5Blnglat%5D=1,2&src=app",
    "https://ditu.amap.com/dir?r=1&policy=0&callnative=0&type=bus&innersrc=map",
])
def test_allowed_public_route_urls(jobs, url):
    assert update_job_commute(jobs, "target", **{**ROUTE, "source_url": url})
    assert jobs.execute("SELECT commute_source_url FROM jobs WHERE id = 'target'").fetchone()[0] == url
