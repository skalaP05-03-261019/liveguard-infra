"""Real browser/BE/DB checks. No route mocks, model calls, sanctions or approval bypass.

Run against a disposable local DB after applying seed-observer.sql.
pip install playwright==1.58.0 && playwright install chromium
python scripts/browser-smoke.py --base-url http://localhost:3000
"""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base-url", default="http://localhost:3000")
parser.add_argument("--chromium-path")
parser.add_argument("--output", default="evidence/browser")
args = parser.parse_args()
out = Path(args.output)
out.mkdir(parents=True, exist_ok=True)
password = os.getenv("SMOKE_LOCAL_PASSWORD", "liveguard-local")
report = {"baseUrl": args.base_url, "mockedRequests": 0, "checks": [], "blockers": []}
nonce = uuid4().hex[:12]
normal = f"통합검증 정상 채팅 {nonce}"
held = f"씨발 통합검증 격리 {nonce}"

def checked(name):
    report["checks"].append(name)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=args.chromium_path,
                                args=["--no-sandbox", "--disable-dev-shm-usage"])
    contexts = []

    def login(account, button):
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        contexts.append(context)
        page = context.new_page()
        page.goto(args.base_url)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=button, exact=True).click()
        page.get_by_label("아이디", exact=True).fill(account)
        page.locator("#password").fill(password)
        with page.expect_response(lambda r: r.url.endswith("/api/auth/login")) as response:
            page.get_by_role("button", name="로그인", exact=True).click()
        assert response.value.status == 200
        expect(page.get_by_role("dialog")).to_have_count(0)
        return context, page

    try:
        viewer_context, viewer = login("viewer", "시청자로 시작하기")
        me = viewer_context.request.get(args.base_url + "/api/auth/me")
        channel = me.json()["data"]["channelIds"][0]
        assert me.json()["data"]["role"] == "VIEWER"
        checked("browser login, session cookie and CSRF-protected login")
        denied = viewer_context.request.post(args.base_url + f"/api/channels/{channel}/messages",
                    data={"clientMessageId": str(uuid4()), "text": "csrf must reject"})
        assert denied.status == 403
        checked("message POST without CSRF is rejected (403)")
        operator_context, operator = login("moderator", "스트리머로 시작하기")
        observer_context, observer = login("integration-observer", "시청자로 시작하기")
        checked("independent operator and non-author viewer sessions")
        observer.evaluate("""channel => {
          window.smokeEvents = [];
          window.smokeStream = new EventSource(`/api/channels/${channel}/events`);
          for (const name of ['CHAT', 'MESSAGE_VISIBILITY_CHANGED'])
            window.smokeStream.addEventListener(name, e => window.smokeEvents.push(e.data));
        }""", channel)
        observer.wait_for_function("window.smokeStream.readyState === 1")

        viewer.get_by_role("textbox", name="채팅 메시지").fill(normal)
        with viewer.expect_response(lambda r: r.request.method == "POST" and "/messages" in r.url) as sent:
            viewer.get_by_role("button", name="보내기", exact=True).click()
        assert sent.value.status in (200, 201)
        assert sent.value.json()["data"]["visibility"] == "PUBLIC"
        expect(observer.get_by_text(normal, exact=True)).to_be_visible(timeout=15000)
        expect(operator.get_by_text(normal, exact=True)).to_be_visible(timeout=15000)
        checked("UI send → real DB → SSE → other viewer and operator UI")

        viewer.reload()
        expect(viewer.get_by_text(normal, exact=True)).to_be_visible(timeout=15000)
        checked("message persists across browser reload")

        viewer.get_by_role("textbox", name="채팅 메시지").fill(held)
        with viewer.expect_response(lambda r: r.request.method == "POST" and "/messages" in r.url) as sent:
            viewer.get_by_role("button", name="보내기", exact=True).click()
        message = sent.value.json()["data"]
        assert message["visibility"] in ("HELD", "HIDDEN"), message["visibility"]
        expect(operator.get_by_text(held, exact=True)).to_be_visible(timeout=15000)
        body = observer_context.request.get(args.base_url + f"/api/channels/{channel}/messages?limit=50").json()
        assert held not in json.dumps(body, ensure_ascii=False)
        expect(observer.get_by_text(held, exact=True)).to_have_count(0)
        checked("HELD/HIDDEN text available to operator, absent from non-author history and UI")
        marker = f"격리 검증 뒤 정상 채팅 {nonce}"
        viewer.get_by_role("textbox", name="채팅 메시지").fill(marker)
        viewer.get_by_role("button", name="보내기", exact=True).click()
        observer.wait_for_function("marker => window.smokeEvents.some(e => e.includes(marker))", arg=marker)
        assert held not in json.dumps(observer.evaluate("window.smokeEvents"), ensure_ascii=False)
        observer.evaluate("window.smokeStream.close()")
        checked("raw non-author SSE stream excludes hidden original through subsequent public event")

        # Record unimplemented capabilities explicitly; 404 is NOT a successful case flow.
        cases = operator_context.request.get(args.base_url + f"/api/cases?channelId={channel}")
        if cases.status != 200:
            report["blockers"].append({"path": "/api/cases", "status": cases.status,
                "impact": "Case/review/Agent E2E is not implemented by current Backend"})
        for name, page in (("viewer", viewer), ("operator", operator), ("observer", observer)):
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)

        admin_context, admin = login("admin", "시스템 운영자 전용")
        assert admin_context.request.get(args.base_url + "/api/auth/me").json()["data"]["role"] == "PLATFORM_ADMIN"
        checked("admin login uses real Backend role")
        # Admin aggregate dashboard is still mock-backed; do not count its data as integrated.
        report["blockers"].append({"path": "SystemPage", "impact": "Aggregate dashboard still uses systemMock"})
        admin.screenshot(path=str(out / "admin.png"), full_page=True)
        viewer.get_by_role("button", name="로그아웃", exact=True).click()
        expect(viewer.get_by_role("button", name="시청자로 시작하기", exact=True)).to_be_visible()
        assert viewer_context.request.get(args.base_url + "/api/auth/me").status == 401
        checked("logout invalidates server session")
        report["status"] = "PASS_WITH_BACKEND_BLOCKERS"
    except Exception:
        report["status"] = "FAILED"
        for i, context in enumerate(contexts):
            for page in context.pages:
                page.screenshot(path=str(out / f"failure-{i}.png"), full_page=True)
        raise
    finally:
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        browser.close()
print(json.dumps(report, ensure_ascii=False, indent=2))
