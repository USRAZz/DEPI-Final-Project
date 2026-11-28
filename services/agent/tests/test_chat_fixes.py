import app.main as main
from app.router import Route, RouteDecision, detect_language, route_request
from fastapi.testclient import TestClient

client = TestClient(main.app)


class _Fake:
    def structured(self, messages, schema, **kw):
        return schema.model_validate({"route": "finance_question", "confidence": 0.9, "language": "unknown"})


def test_empty_message_does_not_call_the_llm():
    d = route_request("   ")
    assert d.route == Route.unclear and d.clarifying_question


def test_language_is_detected_in_code():
    assert detect_language("ايه سبب تنبيه INV-003 ?") == "ar"
    assert detect_language("Which invoices are flagged?") == "en"
    assert detect_language("12345") == "en"


def test_model_language_value_is_overridden():
    assert route_request("كم فاتورة عليها تنبيه؟", llm=_Fake()).language == "ar"


def test_report_request_runs_the_report_writer_not_the_agent(monkeypatch):
    monkeypatch.setattr(main, "route_request", lambda msg: RouteDecision(
        route=Route.report_request, confidence=0.9, language="ar"))

    def boom(*args, **kwargs):
        raise AssertionError("the agent must not run for reports")

    seen = {}

    def fake_report(request, ctx, **kw):
        seen["request"] = request
        from datetime import date

        from securefin_contracts import Language, Report
        return Report(title="تقرير", language=Language.AR, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30),
                      summary="ملخص", rounds=1, quality="passed", markdown="# تقرير\n\nملخص")

    monkeypatch.setattr(main, "run_agent", boom)
    monkeypatch.setattr(main, "generate_report", fake_report)
    r = client.post("/v1/chat", json={"message": "ابعتلي تقرير سبتمبر"})
    assert r.status_code == 200 and r.json()["proposed_actions"] == [] and r.json()["answer"].startswith("# تقرير")
    assert seen["request"] == "ابعتلي تقرير سبتمبر"
