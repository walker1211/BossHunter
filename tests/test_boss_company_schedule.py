"""Company profile reads must respect URL, access and risk boundaries."""

import json
from threading import Event
from unittest import TestCase
from unittest.mock import MagicMock

from bosshunter.collection.platforms.boss_company import (
    BossCompanyScheduleReader,
    CompanyScheduleStopped,
    JS_EXTRACT_COMPANY_SCHEDULE,
    normalize_company_url,
)
from bosshunter.platform_safety import PlatformSafetyStop


class CompanyScheduleReaderTests(TestCase):
    def setUp(self):
        self.browser = MagicMock()
        self.browser.new_tab.return_value = "company-tab"
        self.browser.navigate.return_value = True
        self.browser.wait_for_load.return_value = True
        self.throttle = MagicMock()
        self.throttle.wait.return_value = False
        self.guard = MagicMock()
        self.url1 = "https://www.zhipin.com/gongsi/one.html"
        self.url2 = "https://www.zhipin.com/gongsi/two.html"
        self.current = {"url": self.url1, "text": "周末双休", "risk": None}

        def evaluate(_target, script):
            if script == "risk-script":
                return json.dumps({"risk": self.current["risk"], "evidence": "captcha"})
            if script == JS_EXTRACT_COMPANY_SCHEDULE:
                return json.dumps({"company_url": self.current["url"],
                                   "company_work_schedule": self.current["text"]})
            return "{}"

        self.browser.evaluate.side_effect = evaluate

    def reader(self, **kwargs):
        return BossCompanyScheduleReader(
            browser=self.browser, throttle=self.throttle, risk_script="risk-script",
            guard=self.guard, sleep=lambda _seconds: None, **kwargs,
        )

    def test_url_validation_and_query_removal(self):
        self.assertEqual(normalize_company_url("/gongsi/one.html?ka=job-list#about"), self.url1)
        self.assertEqual(normalize_company_url("https://zhipin.com/gongsi/one.html?tracking=1"), self.url1)
        for bad in ("http://www.zhipin.com/gongsi/one.html",
                    "https://evil.zhipin.com/gongsi/one.html",
                    "https://www.zhipin.com/",
                    "https://www.zhipin.com/job_detail/one.html",
                    "https://www.zhipin.com/gongsi/",
                    "https://user:pass@www.zhipin.com/gongsi/one.html",
                    "https://www.zhipin.com:443/gongsi/one.html",
                    "https://www.zhipin.com:bad/gongsi/one.html"):
            with self.subTest(url=bad):
                self.assertEqual(normalize_company_url(bad), "")

    def test_cache_includes_empty_and_reuses_one_tab_for_two_companies(self):
        reader = self.reader()
        self.assertEqual(reader.read(self.url1 + "?ka=1"), "周末双休")
        self.assertEqual(reader.read(self.url1), "周末双休")
        self.assertEqual(self.browser.new_tab.call_count, 1)
        self.current.update(url=self.url2, text="")
        self.assertEqual(reader.read(self.url2), "")
        self.assertEqual(reader.read(self.url2 + "?ka=2"), "")
        self.browser.navigate.assert_called_once_with("company-tab", self.url2)
        self.assertEqual(self.guard.reserve.call_count, 2)
        self.guard.reserve.assert_any_call("detail_page", daily_limit=900)
        reader.close()
        self.browser.close_tab.assert_called_once_with("company-tab")

    def test_stop_and_budget_prevent_navigation(self):
        stop = Event()
        stop.set()
        with self.assertRaises(CompanyScheduleStopped) as stopped:
            self.reader(stop_event=stop).read(self.url1)
        self.assertEqual(stopped.exception.reason, "user_stopped")
        self.browser.new_tab.assert_not_called()
        self.guard.reserve.assert_not_called()

        self.guard.reserve.side_effect = PlatformSafetyStop("daily_detail_page_limit")
        with self.assertRaises(PlatformSafetyStop):
            self.reader().read(self.url1)
        self.browser.new_tab.assert_not_called()

    def test_confirmed_captcha_blocks_without_profile_extraction(self):
        self.current["risk"] = "captcha"
        reader = self.reader()
        with self.assertRaises(CompanyScheduleStopped) as stopped:
            reader.read(self.url1)
        self.assertEqual(stopped.exception.reason, "captcha")
        self.assertNotIn(self.url1, reader.cache)
        self.assertEqual(self.browser.evaluate.call_count, 2)
        reader.close()
        self.browser.close_tab.assert_called_once_with("company-tab")

    def test_failed_navigation_and_redirected_profile_remain_unknown(self):
        self.browser.new_tab.return_value = None
        reader = self.reader()
        self.assertEqual(reader.read(self.url1), "")
        self.assertEqual(reader.read(self.url1), "")
        self.assertEqual(self.browser.new_tab.call_count, 1)

        self.browser.new_tab.return_value = "company-tab"
        self.current["url"] = self.url1
        reader = self.reader()
        self.browser.wait_for_load.return_value = False
        self.assertEqual(reader.read(self.url1), "")
        self.browser.wait_for_load.return_value = True
        self.current["url"] = "https://www.zhipin.com/gongsi/other.html"
        self.assertEqual(reader.read(self.url2), "")
        self.assertEqual(reader.cache[self.url2], "")
        reader.close()


if __name__ == "__main__":
    import unittest
    unittest.main()
