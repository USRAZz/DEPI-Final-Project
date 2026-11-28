"""Reports (pattern ④ orchestrator-workers + evaluator-optimizer, F6): POST /v1/reports on services/agent."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from .common import Language

ReportSectionKey = Literal["spending_summary", "top_vendors", "categories", "anomalies", "unpaid_invoices", "trend"]


class ReportRequest(BaseModel):
    request: str = Field(min_length=1, max_length=2000)  # the user's words, e.g. "تقرير مصروفات أكتوبر"


class ReportSection(BaseModel):
    key: ReportSectionKey
    heading: str = Field(max_length=200)
    body: str = Field(max_length=4000)
    facts: dict = Field(default_factory=dict)  # the numbers the section was written from (computed by code)


class Report(BaseModel):
    title: str = Field(max_length=200)
    language: Language
    date_from: date
    date_to: date
    summary: str = Field(max_length=2000)
    sections: list[ReportSection] = Field(default_factory=list)
    rounds: int = Field(ge=0)  # evaluator rounds used (max 3)
    # "passed": every number matches the data AND the evaluator approved it;
    # "numbers_checked": every number matches the data, but the evaluator still had feedback after 3 rounds (in notes);
    # "fallback": the LLM text never matched the data, so the sections are the fixed wording built from the data.
    quality: Literal["passed", "numbers_checked", "fallback"]
    notes: list[str] = Field(default_factory=list)  # last evaluator feedback, limits reached, ...
    models: dict[str, int] = Field(default_factory=dict)  # model that answered -> calls (chosen by Jev when enabled)
    markdown: str = ""  # the whole report as Markdown, for the dashboard and the PDF export
