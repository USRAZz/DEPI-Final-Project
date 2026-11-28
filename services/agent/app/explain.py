"""Risk alerts in plain words, in the user's language (POST /v1/explain, prompt P-03 risk_explain_v1).

The risk service decides the codes; this only phrases them. Every code has a fixed meaning below, so the answer
is always correct even without an LLM ("template"). The LLM may reword it ("llm"), but its reply is used only when
it covers exactly the same codes in the same order, in the right script; anything else falls back to the
templates. The explanation never changes a decision: the gateway and the approvers decide.
"""
import json
import logging
import os
import re

from pydantic import BaseModel, Field
from securefin_contracts import Language, RiskExplanation, RiskLevel, RiskReason, RiskScore

from ai_core.llm import get_llm
from ai_core.prompts import load_prompt, untrusted

log = logging.getLogger(__name__)

# Codes produced by services/risk (app/main.py). Add a code here when the risk service adds one.
MEANINGS: dict[str, dict[str, str]] = {
    "DUPLICATE_INVOICE": {
        "en": "This invoice has the same vendor and invoice number as an earlier one, so it may be paid twice.",
        "ar": "الفاتورة دي ليها نفس المورد ونفس رقم فاتورة سابقة، فممكن تتدفع مرتين.",
    },
    "VENDOR_ACCOUNT_MISMATCH": {
        "en": "The bank account written on the invoice is not the vendor's verified account.",
        "ar": "الحساب البنكي المكتوب على الفاتورة مش هو الحساب الموثّق للمورد.",
    },
    "VENDOR_BANK_CHANGE_PENDING": {
        "en": "The vendor's bank details were changed recently and are still on hold until the change is confirmed.",
        "ar": "بيانات المورد البنكية اتغيرت مؤخرًا ولسه متعلّقة لحد ما التغيير يتأكد.",
    },
    "INVOICE_TOTAL_MISMATCH": {
        "en": "The invoice amounts do not add up: subtotal plus tax is not equal to the total.",
        "ar": "أرقام الفاتورة مش مظبوطة: الإجمالي قبل الضريبة زائد الضريبة مش بيساوي الإجمالي.",
    },
    "HIGH_VALUE_REVIEW": {
        "en": "The amount is high, so it gets an extra review.",
        "ar": "المبلغ كبير، فبياخد مراجعة إضافية.",
    },
    "LOW_OCR_CONFIDENCE": {
        "en": "The invoice scan was hard to read, so some values may be wrong; compare them with the original.",
        "ar": "صورة الفاتورة مش واضحة، فممكن يكون فيه قيم غلط؛ راجعها على الفاتورة الأصلية.",
    },
    # Issue codes from the invoice reader (services/extractor/app/pipeline.py ISSUE_MESSAGES, convert.py)
    "TOTAL_MISMATCH": {
        "en": "The invoice amounts do not add up: subtotal plus tax is not equal to the total.",
        "ar": "أرقام الفاتورة مش مظبوطة: الإجمالي قبل الضريبة زائد الضريبة مش بيساوي الإجمالي.",
    },
    "LINE_ITEMS_MISMATCH": {
        "en": "The invoice lines do not add up to the subtotal.",
        "ar": "مجموع بنود الفاتورة مش بيساوي الإجمالي قبل الضريبة.",
    },
    "NON_POSITIVE_TOTAL": {
        "en": "The invoice total is zero or negative.",
        "ar": "إجمالي الفاتورة صفر أو بالسالب.",
    },
    "DUE_BEFORE_INVOICE": {
        "en": "The due date is before the invoice date.",
        "ar": "تاريخ الاستحقاق قبل تاريخ الفاتورة.",
    },
    "IBAN_CHECKSUM_INVALID": {
        "en": "The IBAN printed on the invoice is not a valid bank account number (its check digits are wrong).",
        "ar": "رقم الـ IBAN المكتوب على الفاتورة مش رقم حساب صحيح (أرقام التحقق فيه غلط).",
    },
    "SUSPICIOUS_INSTRUCTIONS": {
        "en": "The invoice contains hidden instructions aimed at the AI or the approval process, a sign of fraud.",
        "ar": "الفاتورة فيها تعليمات مخفية موجّهة للذكاء الاصطناعي أو لخطوات الموافقة، ودي علامة احتيال.",
    },
    "POSSIBLE_DUPLICATE": {
        "en": "An invoice with the same vendor, number and total was already received.",
        "ar": "فيه فاتورة بنفس المورد والرقم والإجمالي وصلت قبل كده.",
    },
    "SCHEMA_INVALID": {
        "en": "Some invoice fields could not be read reliably (for example the date), so a person must check them.",
        "ar": "فيه بيانات في الفاتورة ماتقريتش كويس (زي التاريخ)، فلازم حد يراجعها.",
    },
    "LOW_CATEGORY_CONFIDENCE": {
        "en": "The expense category is uncertain.",
        "ar": "فئة المصروف مش أكيدة.",
    },
    "CATEGORIZATION_FAILED": {
        "en": "The expense category could not be chosen.",
        "ar": "ماقدرناش نحدد فئة المصروف.",
    },
}
FLAGGED_NO_CODE = {
    "en": "This invoice is flagged for manual review, but no reason was recorded; ask the finance team.",
    "ar": "الفاتورة دي عليها تنبيه للمراجعة اليدوية بس مفيش سبب متسجّل؛ اسأل فريق المالية.",
}
RISK_NO_CODE = {
    "en": "The risk check rated this payment {level} but recorded no specific rule; review it before paying.",
    "ar": "تقييم المخاطر حط الدفعة دي في {level} من غير قاعدة محددة؛ راجعها قبل الدفع.",
}


def no_code_reason(level: str | None, lang: str) -> str:
    """The reason to show when nothing more specific is recorded."""
    if level in ("medium", "high"):
        return RISK_NO_CODE[lang].format(level=LEVEL_WORDS[level][lang])
    return FLAGGED_NO_CODE[lang]


LEVEL_WORDS = {"low": {"en": "low risk", "ar": "مخاطر منخفضة"}, "medium": {"en": "medium risk", "ar": "مخاطر متوسطة"},
               "high": {"en": "high risk", "ar": "مخاطر عالية"}}
UNKNOWN = {
    "en": "A risk rule flagged this payment ({code}); ask the finance team what it means before paying.",
    "ar": "فيه قاعدة مخاطر نبّهت على الدفعة دي ({code})؛ اسأل فريق المالية عن معناها قبل الدفع.",
}
SUMMARY = {
    RiskLevel.LOW: {"en": "Low risk: no rule found a problem worth holding this payment for.",
                    "ar": "مخاطر منخفضة: مفيش قاعدة لقت مشكلة تستاهل وقف الدفعة دي."},
    RiskLevel.MEDIUM: {"en": "Medium risk: check the points below before approving this payment.",
                       "ar": "مخاطر متوسطة: راجع النقط اللي تحت قبل ما توافق على الدفعة دي."},
    RiskLevel.HIGH: {"en": "High risk: this payment is held for review; check the points below carefully.",
                     "ar": "مخاطر عالية: الدفعة دي متوقفة للمراجعة؛ راجع النقط اللي تحت كويس."},
}
_ARABIC = re.compile(r"[؀-ۿ]")


class _LLMReason(BaseModel):
    code: str
    text: str = Field(min_length=1, max_length=400)


class _LLMExplanation(BaseModel):
    summary: str = Field(min_length=1, max_length=600)
    reasons: list[_LLMReason] = Field(default_factory=list)


def meaning(code: str, language: str) -> str:
    return MEANINGS.get(code, {}).get(language) or UNKNOWN[language].format(code=code)


def template_explanation(risk: RiskScore, language: Language) -> RiskExplanation:
    lang = language.value
    return RiskExplanation(summary=SUMMARY[risk.level][lang], language=language, source="template",
                           reasons=[RiskReason(code=c, text=meaning(c, lang)) for c in risk.rule_hits])


def _usable(reply: _LLMExplanation, risk: RiskScore, lang: str) -> bool:
    if [r.code for r in reply.reasons] != list(risk.rule_hits):
        return False  # a dropped, added, renamed or reordered code: the model is not explaining these facts
    texts = [reply.summary, *(r.text for r in reply.reasons)]
    in_arabic = [bool(_ARABIC.search(t)) for t in texts]
    return all(in_arabic) if lang == "ar" else not any(in_arabic)


def explain_risk(risk: RiskScore, language: Language = Language.EN, *, llm=None,
                 use_llm: bool | None = None) -> RiskExplanation:
    """Template wording by default when there is nothing to explain; otherwise the LLM, checked, else templates."""
    base = template_explanation(risk, language)
    if use_llm is None:
        use_llm = os.getenv("EXPLAIN_USE_LLM", "true").lower() == "true"
    if not use_llm or not risk.rule_hits:
        return base
    facts = {"level": risk.level.value, "score": round(risk.score),
             "codes": [{"code": r.code, "meaning": meaning(r.code, "en")} for r in base.reasons]}
    try:
        llm = llm or get_llm("explainer")
        system = load_prompt("risk_explain", language=language.value)
        reply = llm.structured([{"role": "system", "content": system},
                                {"role": "user", "content": untrusted(json.dumps(facts, ensure_ascii=False))}],
                               _LLMExplanation)
    except Exception as e:  # provider down, bad JSON twice, no key: the templates are always right
        log.warning("risk explanation fell back to templates: %s: %s", type(e).__name__, e)
        return base
    if not _usable(reply, risk, language.value):
        log.warning("risk explanation fell back to templates: reply did not match the codes or language")
        return base
    return RiskExplanation(summary=reply.summary, language=language, source="llm",
                           reasons=[RiskReason(code=r.code, text=r.text) for r in reply.reasons])
