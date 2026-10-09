"""Run the page extractors against company/job DOMs, including recommendations."""

import json
from pathlib import Path
import shutil
import subprocess
from unittest import TestCase, skipUnless

from bosshunter.collection.platforms.boss import JS_EXTRACT_DETAIL
from bosshunter.collection.platforms.boss_company import JS_EXTRACT_COMPANY_SCHEDULE
from bosshunter.work_schedule import infer_work_schedule


FRONTEND = Path(__file__).resolve().parents[1] / "src/bosshunter/web/frontend"
NODE = shutil.which("node")
RUN_DOM = """
const fs = require('node:fs');
const {JSDOM} = require('jsdom');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const dom = new JSDOM(input.html, {url: input.url, runScripts: 'outside-only'});
process.stdout.write(dom.window.eval(input.script));
dom.window.close();
"""


@skipUnless(NODE and (FRONTEND / "node_modules/jsdom").exists(), "Requires frontend Node/jsdom dependencies")
class BossCompanyDOMTests(TestCase):
    def extract(self, html, script=JS_EXTRACT_COMPANY_SCHEDULE, path="/gongsi/own-company.html"):
        result = subprocess.run(
            [NODE, "-e", RUN_DOM], cwd=FRONTEND,
            input=json.dumps({"html": html, "script": script, "url": "https://www.zhipin.com" + path}),
            text=True, capture_output=True, check=True, timeout=10,
        )
        return json.loads(result.stdout)

    def test_work_time_card_excludes_recommended_employer_claims(self):
        result = self.extract("""
            <div class="job-sec work-time"><h3>工作时间及福利</h3>
              <p>上午09:00 - 下午06:00</p><p>双休</p><ul><li>五险一金</li></ul></div>
            <div class="job-sec"><h3>公司简介</h3><div class="text fold-text">开发业务系统。</div></div>
            <footer>推荐职位：其他公司单休，大小周</footer>
        """)
        text = result["company_work_schedule"]
        self.assertIn("双休", text)
        self.assertNotIn("其他公司", text)
        self.assertEqual(infer_work_schedule("后端", "开发API", text)[:2], ("double", "company_profile"))

    def test_introduction_can_supply_schedule_when_card_is_absent(self):
        result = self.extract("""
            <section><h3>公司简介</h3><div class="text">周休两天，弹性上班。</div></section>
            <div class="recommendations">其他岗位做六休一</div>
        """)
        self.assertEqual(infer_work_schedule("后端", "API", result["company_work_schedule"])[0], "double")

    def test_working_hours_and_unrelated_double_rest_do_not_supply_schedule(self):
        result = self.extract("""
            <div class="job-sec work-time"><h3>工作时间及福利</h3><p>9:00-18:00</p><p>五险一金</p></div>
            <div>热门推荐：PHP（双休）</div>
        """)
        self.assertEqual(infer_work_schedule("后端", "API", result["company_work_schedule"])[0], "unknown")

    def test_heading_alone_never_falls_back_to_body_or_recommendations(self):
        result = self.extract("""
            <h3>公司简介</h3><p>热门推荐：其他岗位双休</p>
            <footer><div><h3>工作时间及福利</h3><p>双休</p></div></footer>
        """)
        self.assertEqual(result["company_work_schedule"], "")

    def test_detail_company_url_uses_company_owned_links_only(self):
        result = self.extract("""
            <title>后端_示例招聘</title><div class="info-primary"><div class="name"><h1>后端</h1></div></div>
            <div class="job-sec-text">API开发</div>
            <div class="sider-company"><div class="company-info">
              <a href="/gongsi/job/own-company.html">查看职位</a>
              <a href="/gongsi/own-company.html?ka=tracking">示例公司</a></div></div>
            <footer><a href="/gongsi/other-company.html">其他公司（双休）</a></footer>
        """, JS_EXTRACT_DETAIL, "/job_detail/example.html")
        self.assertEqual(result["company_url"], "https://www.zhipin.com/gongsi/own-company.html")
