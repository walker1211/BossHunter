"""Read company-owned schedule claims without mixing in recommended jobs."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit


JS_EXTRACT_COMPANY_SCHEDULE = """
(() => {
    const texts = [];
    const add = node => {
        if (!node || node === document.body || node === document.documentElement) return;
        const text = node?.textContent?.trim();
        if (text && !texts.includes(text)) texts.push(text);
    };
    add(document.querySelector('.job-sec.work-time'));
    for (const heading of document.querySelectorAll('h2, h3, h4')) {
        if (heading.closest('footer, .links-content, .recommendations')) continue;
        const label = heading.textContent.trim();
        if (label === '工作时间及福利') {
            add(heading.closest('.job-sec') || heading.parentElement);
        } else if (label === '公司简介' || label === '公司介绍') {
            const section = heading.closest('.job-sec') || heading.parentElement;
            if (!section || section === document.body || section === document.documentElement) continue;
            add(section?.querySelector('.text, .fold-text') || section);
        }
    }
    return JSON.stringify({
        company_url: location.href,
        company_work_schedule: texts.join('\\n').slice(0, 4000)
    });
})()
"""


def normalize_company_url(value: Any) -> str:
    """Accept only public BOSS company profiles and discard tracking queries."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(urljoin("https://www.zhipin.com", text))
        valid = (parsed.scheme == "https" and parsed.hostname in {"www.zhipin.com", "zhipin.com"}
                 and not parsed.username and not parsed.password and parsed.port is None
                 and re.fullmatch(r"/gongsi/[A-Za-z0-9_~-]+\.html", parsed.path))
    except ValueError:
        return ""
    return f"https://www.zhipin.com{parsed.path}" if valid else ""


class CompanyScheduleStopped(RuntimeError):
    """A cancellation or confirmed platform risk must stop further navigation."""

    def __init__(self, reason: str, evidence: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence


class BossCompanyScheduleReader:
    """One extra tab, a per-run company cache, and the existing access budget."""

    def __init__(
        self,
        *,
        browser: Any,
        throttle: Any,
        risk_script: str,
        guard: Any = None,
        detail_limit: int = 900,
        stop_event: Any = None,
        delay_multiplier: float = 1.5,
        sleep: Callable[[float], None] = time.sleep,
        on_event: Callable[..., None] = lambda **_values: None,
    ):
        self.browser = browser
        self.throttle = throttle
        self.risk_script = risk_script
        self.guard = guard
        self.detail_limit = detail_limit
        self.stop_event = stop_event
        self.delay_multiplier = delay_multiplier
        self.sleep = sleep
        self.on_event = on_event
        self.target: str | None = None
        self.cache: dict[str, str] = {}

    def _wait(self, seconds: float) -> None:
        if self.stop_event is not None:
            if self.stop_event.wait(seconds):
                raise CompanyScheduleStopped("user_stopped")
        else:
            self.sleep(seconds)

    def _risk(self) -> dict[str, str] | None:
        raw = self.browser.evaluate(self.target, self.risk_script)
        try:
            value = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict) or not value.get("risk"):
            return None
        return {"kind": str(value["risk"]), "evidence": str(value.get("evidence") or "unspecified")}

    def _unavailable(self, url: str) -> str:
        self.cache[url] = ""
        self.on_event(message="BOSS 公司页未读到可用资料，休息安排保留未说明")
        return ""

    def read(self, company_url: str) -> str:
        url = normalize_company_url(company_url)
        if not url:
            return ""
        if self.stop_event is not None and self.stop_event.is_set():
            raise CompanyScheduleStopped("user_stopped")
        if url in self.cache:
            return self.cache[url]
        if self.throttle.wait(self.stop_event):
            raise CompanyScheduleStopped("user_stopped")
        if self.guard is not None:
            self.guard.reserve("detail_page", daily_limit=self.detail_limit)
        if self.target is None:
            opened = self.browser.new_tab(url, background=True)
            if opened:
                self.target = str(opened)
        else:
            opened = self.browser.navigate(self.target, url)
        if not opened or not self.target:
            return self._unavailable(url)
        self._wait(2.0 * self.delay_multiplier)
        if not self.browser.wait_for_load(self.target, timeout=10):
            return self._unavailable(url)
        first = self._risk()
        if first:
            self._wait(1.0 * self.delay_multiplier)
            second = self._risk()
            if second and second["kind"] == first["kind"]:
                raise CompanyScheduleStopped(second["kind"], second["evidence"])
        raw = self.browser.evaluate(self.target, JS_EXTRACT_COMPANY_SCHEDULE)
        try:
            value = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            return self._unavailable(url)
        if not isinstance(value, dict) or normalize_company_url(value.get("company_url")) != url:
            return self._unavailable(url)
        text = str(value.get("company_work_schedule") or "").strip()[:4000]
        self.cache[url] = text
        return text

    def close(self) -> None:
        if self.target:
            self.browser.close_tab(self.target)
            self.target = None
