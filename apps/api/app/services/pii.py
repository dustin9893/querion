"""PII detection & anonymisation at the API boundary — powered by Microsoft Presidio.

Bank customers (and staff) type account numbers, ID numbers, phones and OTPs into
chat. None of that is needed to answer a policy / fee / process question, so it is
replaced *before* the text reaches the LLM provider, the conversation table or the
audit log.

Engine
- presidio-analyzer with the spaCy `en_core_web_sm` pipeline for tokenisation and
  context words (Presidio ships no Vietnamese NER model; lemmas of Vietnamese tokens
  equal the tokens, which is all the context enhancer needs).
- Built-in recognizers: EMAIL_ADDRESS, CREDIT_CARD (Luhn), PHONE_NUMBER (libphonenumber,
  region VN).
- Custom PatternRecognizers with Vietnamese context words: CCCD/CMND/passport, bank
  account / long digit runs, CIF, OTP / password / PIN codes.
- presidio-anonymizer replaces each span with a Vietnamese placeholder.

Fallback: if Presidio or the spaCy model is missing (`PII_ENGINE=regex`, or import
error), a conservative regex masker keeps the same guarantees at lower recall.
Set `PII_ENGINE=off` to disable (never in production).
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)

# Entity type → placeholder shown to the LLM, stored in DB, shown in the UI/audit.
PLACEHOLDER = {
    "EMAIL_ADDRESS": "[email đã ẩn]",
    "CREDIT_CARD": "[số thẻ đã ẩn]",
    "PHONE_NUMBER": "[số điện thoại đã ẩn]",
    "OTP_CODE": "[mã đã ẩn]",
    "VN_ID_NUMBER": "[số định danh đã ẩn]",
    "VN_BANK_ACCOUNT": "[số tài khoản đã ẩn]",
    "VN_CIF": "[mã khách hàng đã ẩn]",
    "DEFAULT": "[đã ẩn]",
}
# Entity type → short kind used in the SSE notice
KIND_OF = {
    "EMAIL_ADDRESS": "email", "CREDIT_CARD": "card", "PHONE_NUMBER": "phone",
    "OTP_CODE": "otp", "VN_ID_NUMBER": "id", "VN_BANK_ACCOUNT": "account", "VN_CIF": "cif",
}
KIND_LABELS = {
    "email": "email", "card": "số thẻ", "phone": "số điện thoại", "otp": "mã OTP/mật khẩu",
    "id": "số CCCD/CMND", "account": "số tài khoản", "cif": "mã khách hàng",
}
ENTITIES = list(KIND_OF.keys())
SCORE_THRESHOLD = 0.4


@dataclass
class PiiResult:
    text: str
    kinds: list[str] = field(default_factory=list)
    engine: str = "off"

    @property
    def found(self) -> bool:
        return bool(self.kinds)


# ---------------------------------------------------------------------------
# Presidio engine (built once, thread-safe)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_analyzer = None
_anonymizer = None
_presidio_failed = False


def _build_presidio():
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import CreditCardRecognizer, EmailRecognizer, PhoneRecognizer
    from presidio_anonymizer import AnonymizerEngine

    nlp_engine = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }).create_engine()

    lang = "en"  # the spaCy pipeline language; recognizers below are pattern/context based and language-agnostic
    registry = RecognizerRegistry(supported_languages=[lang])
    registry.add_recognizer(EmailRecognizer(supported_language=lang, context=["email", "mail", "thư"]))
    registry.add_recognizer(CreditCardRecognizer(supported_language=lang, context=["thẻ", "card", "visa", "mastercard", "napas"]))
    registry.add_recognizer(PhoneRecognizer(
        supported_language=lang, supported_regions=("VN",), leniency=1,
        context=["điện", "thoại", "sđt", "sdt", "phone", "gọi", "zalo", "hotline", "di", "động"],
    ))
    # VN mobile numbers written as one run ("0912345678") also match the bank-account pattern below;
    # a dedicated phone pattern scores higher so the label (and the notice) says "số điện thoại".
    registry.add_recognizer(PatternRecognizer(
        supported_entity="PHONE_NUMBER", supported_language=lang, name="vn_phone_recognizer",
        patterns=[Pattern("vn_mobile", r"(?<![\d.,/-])(?:\+84|0)(?:[ .-]?\d){9}(?![.,/-]?\d)", 0.6)],
        context=["điện", "thoại", "sđt", "sdt", "phone", "gọi", "zalo", "hotline", "di", "động", "liên", "hệ"],
    ))
    registry.add_recognizer(PatternRecognizer(
        supported_entity="VN_ID_NUMBER", supported_language=lang, name="vn_id_recognizer",
        patterns=[
            Pattern("cccd_12", r"(?<![\d.,/-])\d{12}(?![.,/-]?\d)", 0.5),
            Pattern("cmnd_9", r"(?<![\d.,/-])\d{9}(?![.,/-]?\d)", 0.15),          # needs context
            Pattern("passport", r"\b[A-Z]\d{7,8}\b", 0.2),                         # needs context
        ],
        context=["cccd", "cmnd", "cmt", "căn", "cước", "chứng", "minh", "hộ", "chiếu", "passport", "định", "danh", "id"],
    ))
    registry.add_recognizer(PatternRecognizer(
        supported_entity="VN_BANK_ACCOUNT", supported_language=lang, name="vn_bank_account_recognizer",
        patterns=[
            Pattern("long_digits", r"(?<![\d.,/-])\d{10,19}(?![.,/-]?\d)", 0.55),    # bare long runs are almost always accounts/IDs
            Pattern("grouped_digits", r"(?<![\d.,/-])\d{4}(?:[ .-]\d{3,4}){2,4}(?![.,/-]?\d)", 0.3),
            Pattern("account_8_9", r"(?<![\d.,/-])\d{8,9}(?![.,/-]?\d)", 0.14),       # needs context; ≠ cmnd_9 (0.15) so ties never happen
        ],
        context=["stk", "tài", "khoản", "tk", "account", "acc", "chuyển", "thụ", "hưởng"],  # no generic "số"/"nhận"
    ))
    registry.add_recognizer(PatternRecognizer(
        supported_entity="VN_CIF", supported_language=lang, name="vn_cif_recognizer",
        patterns=[Pattern("cif_6_10", r"(?<![\d.,/-])\d{6,10}(?![.,/-]?\d)", 0.1)],  # only with context
        context=["cif", "khách", "hàng", "kh", "customer"],  # not "mã": it would tie with OTP ("mã OTP")
    ))
    registry.add_recognizer(PatternRecognizer(
        supported_entity="OTP_CODE", supported_language=lang, name="otp_recognizer",
        # 0.12 (not 0.1) so an OTP outranks a CIF when both contexts appear; "mã" alone is too generic
        patterns=[Pattern("otp_4_8", r"(?<![\d.,/-])\d{4,8}(?![.,/-]?\d)", 0.12)],
        context=["otp", "xác", "thực", "nhận", "bảo", "mật", "khẩu", "pin", "password", "passcode", "code"],
    ))

    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, registry=registry,
                              supported_languages=[lang], default_score_threshold=SCORE_THRESHOLD)
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


def _get_presidio():
    global _analyzer, _anonymizer, _presidio_failed
    if _analyzer is not None:
        return _analyzer, _anonymizer
    if _presidio_failed:
        return None, None
    with _lock:
        if _analyzer is None and not _presidio_failed:
            try:
                _analyzer, _anonymizer = _build_presidio()
                logger.info("PII engine: Microsoft Presidio ready (spaCy en_core_web_sm, region VN)")
            except Exception as exc:  # missing package / model → regex fallback
                _presidio_failed = True
                logger.warning("Presidio unavailable (%s); falling back to regex PII masking", exc)
    return _analyzer, _anonymizer


def warm_up() -> str:
    """Build the engine eagerly (called from the API lifespan). Returns the engine name."""
    if settings.PII_ENGINE == "presidio":
        a, _ = _get_presidio()
        return "presidio" if a is not None else "regex"
    return settings.PII_ENGINE


def _mask_presidio(text: str) -> PiiResult | None:
    from presidio_anonymizer.entities import OperatorConfig

    analyzer, anonymizer = _get_presidio()
    if analyzer is None:
        return None
    results = analyzer.analyze(text=text, language="en", entities=ENTITIES, score_threshold=SCORE_THRESHOLD)
    if not results:
        return PiiResult(text=text, engine="presidio")
    operators = {ent: OperatorConfig("replace", {"new_value": ph}) for ent, ph in PLACEHOLDER.items()}
    out = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
    kinds: list[str] = []
    for item in sorted(out.items, key=lambda i: i.start):
        k = KIND_OF.get(item.entity_type, item.entity_type.lower())
        if k not in kinds:
            kinds.append(k)
    return PiiResult(text=out.text, kinds=kinds, engine="presidio")


# ---------------------------------------------------------------------------
# Regex fallback (same placeholders, lower recall)
# ---------------------------------------------------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_PHONE = re.compile(r"(?<![\d\w])(?:\+?84|0)(?:[ .-]?\d){9,10}(?![\d\w])")
_OTP = re.compile(r"((?:OTP|mã xác (?:thực|nhận)|mã bảo mật|mật khẩu|password|PIN)\D{0,25}?)(\d{4,8})(?!\d)", re.I)
_KEYED_ID = re.compile(
    r"((?:CIF|STK|CMND|CCCD|CMT|số tài khoản|tài khoản số|số TK|TK số|số thẻ|thẻ số|mã khách hàng|mã KH|hộ chiếu|passport)"
    r"\s*(?:là|:|số|#)?\s*)(\d(?:[ .-]?\d){5,18})(?!\d)", re.I)
_LONG_DIGITS = re.compile(r"(?<![\d.,/-])\d{10,}(?![.,/-]?\d)")


def _mask_regex(text: str) -> PiiResult:
    kinds: list[str] = []

    def sub(pattern, repl, kind, s):
        new, n = pattern.subn(repl, s)
        if n and kind not in kinds:
            kinds.append(kind)
        return new

    s = text
    s = sub(_EMAIL, PLACEHOLDER["EMAIL_ADDRESS"], "email", s)
    s = sub(_OTP, lambda m: m.group(1) + PLACEHOLDER["OTP_CODE"], "otp", s)
    s = sub(_KEYED_ID, lambda m: m.group(1) + PLACEHOLDER["VN_ID_NUMBER"], "id", s)
    s = sub(_CARD, PLACEHOLDER["CREDIT_CARD"], "card", s)
    s = sub(_PHONE, PLACEHOLDER["PHONE_NUMBER"], "phone", s)
    s = sub(_LONG_DIGITS, PLACEHOLDER["VN_BANK_ACCOUNT"], "account", s)
    return PiiResult(text=s, kinds=kinds, engine="regex")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mask_pii(text: str | None) -> PiiResult:
    if not text:
        return PiiResult(text or "", engine=settings.PII_ENGINE)
    if settings.PII_ENGINE == "off":
        return PiiResult(text, engine="off")
    if settings.PII_ENGINE == "presidio":
        try:
            res = _mask_presidio(text)
            if res is not None:
                return res
        except Exception as exc:  # never let the masker break a chat request
            logger.exception("Presidio masking failed, using regex fallback: %s", exc)
    return _mask_regex(text)


def notice_for(kinds: list[str]) -> str:
    labels = ", ".join(KIND_LABELS.get(k, k) for k in kinds)
    return f"Đã ẩn thông tin nhạy cảm ({labels}) trước khi xử lý. Trợ lý không cần và không lưu các dữ liệu này."
