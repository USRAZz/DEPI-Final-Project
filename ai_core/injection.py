"""Code-level check for instructions hidden in untrusted documents (prompt injection).

An invoice talks about goods, amounts and dates. A line addressed to "the AI", "the system" or "the assistant",
an order to ignore rules, approve a payment or keep something from the user, or a tool call written as text has
no business in one. When any of these shows up the extractor marks the invoice SUSPICIOUS_INSTRUCTIONS and it goes
to a person (NEEDS-REVIEW), whatever the LLM made of it. This is a second wall: the prompts already treat the
text as data, and the agent never sees the raw text at all.

Patterns are deliberately narrow. Normal invoice wording such as "Please pay within 30 days", "Approved by:",
"يرجى السداد" or a printed IBAN must not match (tests/test_injection.py checks the synthetic invoice set).
"""
import re

from .privacy import normalize_digits

CODE = "SUSPICIOUS_INSTRUCTIONS"

_DIACRITICS = re.compile(r"[ً-ْٰـ]")  # Arabic harakat, superscript alef, tatweel

_AI_WORDS_EN = r"(?:ai|a\.i\.|llm|gpt|chatgpt|language model|extractor|assistant|model|bot|system)"
_AI_WORDS_AR = r"(?:مساعد|نظام|ذكاء|نموذج|بوت|مستخرج|روبوت)"  # after لل / ل / إلى ال

PATTERNS: dict[str, re.Pattern] = {
    # English
    "ignore_rules": re.compile(r"\b(?:ignore|disregard|forget|override)\b[^\n]{0,40}"
                               r"\b(?:rules?|instructions?|above|previous|prior|everything|prompt|policy|policies)\b",
                               re.I),
    "role_marker": re.compile(r"(?:^|\n|\]|\))\s*(?:system|assistant|developer|admin(?:istrator)?)\s*:", re.I),
    "note_to_ai": re.compile(rf"\b(?:note|message|instructions?|reminder)s?\s+(?:to|for)\s+(?:the\s+)?{_AI_WORDS_EN}\b",
                             re.I),
    "addressed_to_ai": re.compile(r"\b(?:dear|hey|attention)\s+(?:ai|assistant|llm|gpt|chatgpt|model)\b", re.I),
    "tool_call_text": re.compile(r"create_payment_request|approve_payment|execute_payment|function_call|tool_call"
                                 r"|\"tool\"\s*:", re.I),
    "pre_approved": re.compile(r"\bpre-?approved\b|\balready\s+approved\b", re.I),
    "approve_payment": re.compile(r"\b(?:approve|execute|authori[sz]e|release)\s+(?:the\s+|this\s+|a\s+)?"
                                  r"(?:payment|transfer|funds|invoice)\b", re.I),
    "hide_from_user": re.compile(r"\b(?:do not|don't|never)\s+(?:tell|inform|mention|show|reveal)\b[^\n]{0,40}"
                                 r"\b(?:user|anyone|accountant|approver|manager|finance)\b", re.I),
    "real_value_claim": re.compile(r"\b(?:the\s+)?(?:real|actual|true)\s+(?:total|amount|iban|account)\s+is\b"
                                   r"|\breport\s+\d[\d,.]*\s*(?:instead|as the total)?", re.I),
    # Arabic (diacritics removed first)
    "ar_ignore": re.compile(r"تجاهل|تجاهلي|اتجاهل|انس\s+(?:كل|التعليمات)"),
    "ar_note_to_ai": re.compile(r"(?:ملاحظة|ملاحظه|رسالة|رساله|تعليمات|تعليمة|تنبيه)\s+"
                                rf"(?:لل|ل|(?:إلى|الى)\s+ال){_AI_WORDS_AR}"),
    "ar_hide_from_user": re.compile(r"(?<!\S)و?(?:لا|ما)\s+(?:تذكر|تخبر|تقول|تعرض|تبلغ|تقل)"
                                    r"(?:\s+\S+){0,3}\s+(?:للمستخدم|المستخدم|لأحد|لاحد|للمحاسب|للمدير)"
                                    r"|(?<!\S)و?(?:لا|ما)\s+(?:تذكر|تخبر|تقل)\s+ذلك"),
    "ar_approve_payment": re.compile(r"(?<!\S)(?:وافق|اعتمد|نفذ|اصرف|حول)\s+(?:على\s+)?(?:الدفع|الدفعة|الدفعه|"
                                     r"التحويل|طلب\s+الدفع|المبلغ\s+(?:إلى|الى))"),
    "ar_pre_approved": re.compile(r"(?:موافق|معتمد|تمت\s+الموافقة)\s+(?:عليه|عليها)?\s*مسبق"),
    "ar_use_account": re.compile(r"استخدم\s+(?:\S+\s+){0,3}(?:في|فى)\s+(?:أي|اي|كل)\s+طلب"),
}


def _normalize(text: str) -> str:
    return _DIACRITICS.sub("", normalize_digits(text or ""))


def find_instructions(text: str) -> list[str]:
    """Names of the patterns found in the text, in PATTERNS order; [] for a normal document."""
    s = _normalize(text)
    return [name for name, pattern in PATTERNS.items() if pattern.search(s)]


def looks_injected(text: str) -> bool:
    return bool(find_instructions(text))
