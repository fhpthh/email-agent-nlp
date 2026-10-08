import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from src.emailagent.domain.enums import EmailCategory
from src.emailagent.domain.models import ThreadAnalysisItem


class BaseFilterRule(ABC):

    @property
    @abstractmethod
    def rule_name(self) -> str:
        pass

    @abstractmethod
    def is_match(self, sender: str, subject: str, body: str) -> bool:
        pass

    @abstractmethod
    def build_result(self, thread_id: UUID, sender: str, subject: str) -> ThreadAnalysisItem:
        pass


class OtpVerificationRule(BaseFilterRule):
    rule_name = "OTP_Verification"
    DEFAULT_PATTERN = (
        r"(mã xác thực|mã xác minh|mã otp|verification code|security code|"
        r"mã khôi phục|one-time password|passcode)"
    )

    def __init__(self, pattern: Optional[str] = None):
        self._pattern = re.compile(pattern or self.DEFAULT_PATTERN, re.IGNORECASE)

    def is_match(self, sender: str, subject: str, body: str) -> bool:
        return bool(self._pattern.search(subject) or self._pattern.search(body[:500]))

    def build_result(self, thread_id: UUID, sender: str, subject: str) -> ThreadAnalysisItem:
        return ThreadAnalysisItem(
            thread_id=str(thread_id),
            category=EmailCategory.ACTION_REQUIRED,
            is_urgent=True,
            needs_reply=False,
            summary="Email tự động cung cấp mã xác thực OTP / bảo mật tài khoản. Mã có thời hạn sử dụng ngắn.",
            action_items=[]
        )


class MarketingNewsletterRule(BaseFilterRule):
    rule_name = "Marketing_Newsletter"
    DEFAULT_SENDER_PATTERN = r"(newsletter|marketing|promo|news|deals|jobalerts?|digest)@"
    DEFAULT_JOB_PATTERN = r"(job alert|cơ hội việc làm|lời mời kết nối)"
    DEFAULT_UNSUBSCRIBE_KEYWORDS: Tuple[str, ...] = ("unsubscribe", "hủy đăng ký", "hủy nhận thư")

    def __init__(
            self,
            sender_pattern: Optional[str] = None,
            job_pattern: Optional[str] = None,
            unsubscribe_keywords: Optional[Tuple[str, ...]] = None
    ):
        self._sender_regex = re.compile(sender_pattern or self.DEFAULT_SENDER_PATTERN, re.IGNORECASE)
        self._job_regex = re.compile(job_pattern or self.DEFAULT_JOB_PATTERN, re.IGNORECASE)
        self._unsubscribe_keywords = unsubscribe_keywords or self.DEFAULT_UNSUBSCRIBE_KEYWORDS

    def is_match(self, sender: str, subject: str, body: str) -> bool:
        if self._sender_regex.search(sender):
            return True
        if self._job_regex.search(subject):
            return True
        if any(kw in body for kw in self._unsubscribe_keywords):
            return True
        return False

    def build_result(self, thread_id: UUID, sender: str, subject: str) -> ThreadAnalysisItem:
        return ThreadAnalysisItem(
            thread_id=str(thread_id),
            category=EmailCategory.MARKETING_NEWSLETTER,
            is_urgent=False,
            needs_reply=False,
            summary=f"Bản tin định kỳ, gợi ý việc làm hoặc quảng cáo từ {sender}. Không yêu cầu hành động.",
            action_items=[]
        )


class AutomatedBillingRule(BaseFilterRule):
    rule_name = "Automated_Billing"
    DEFAULT_PATTERN = (
        r"(biên lai|hóa đơn điện tử|e-invoice|e-receipt|thông báo giao dịch|"
        r"sao kê tài khoản|phiếu thanh toán|payment receipt)"
    )

    def __init__(self, pattern: Optional[str] = None):
        self._pattern = re.compile(pattern or self.DEFAULT_PATTERN, re.IGNORECASE)

    def is_match(self, sender: str, subject: str, body: str) -> bool:
        return bool(self._pattern.search(subject))

    def build_result(self, thread_id: UUID, sender: str, subject: str) -> ThreadAnalysisItem:
        return ThreadAnalysisItem(
            thread_id=str(thread_id),
            category=EmailCategory.FINANCE_BILLING,
            is_urgent=False,
            needs_reply=False,
            summary=f"Thông báo giao dịch hoặc hóa đơn thanh toán tự động gửi từ {sender}.",
            action_items=[]
        )


class SystemNotificationRule(BaseFilterRule):
    rule_name = "System_Notification"
    DEFAULT_PATTERN = r"(no-?reply|do-?not-?reply|notifications?|mailer-daemon|system|alert|support-automated)@"

    def __init__(self, pattern: Optional[str] = None):
        self._pattern = re.compile(pattern or self.DEFAULT_PATTERN, re.IGNORECASE)

    def is_match(self, sender: str, subject: str, body: str) -> bool:
        return bool(self._pattern.search(sender))

    def build_result(self, thread_id: UUID, sender: str, subject: str) -> ThreadAnalysisItem:
        return ThreadAnalysisItem(
            thread_id=str(thread_id),
            category=EmailCategory.REPORT,
            is_urgent=False,
            needs_reply=False,
            summary=f"Thông báo tự động từ hệ thống ({sender}). Thư không nhận phản hồi.",
            action_items=[]
        )


class EmailRuleEngine:

    def __init__(self, rules: Optional[List[BaseFilterRule]] = None):
        self._rules: List[BaseFilterRule] = rules or [
            OtpVerificationRule(),
            MarketingNewsletterRule(),
            AutomatedBillingRule(),
            SystemNotificationRule(),
        ]

    def add_rule(self, rule: BaseFilterRule) -> None:
        self._rules.append(rule)

    def evaluate(self, thread_id: UUID, emails: List[Dict[str, Any]]) -> Optional[ThreadAnalysisItem]:
        if not emails:
            return None

        last_email = emails[-1]
        sender = last_email.get("sender", "").lower()
        subject = last_email.get("subject", "").lower()
        body = (last_email.get("clean_body") or "").lower()

        for rule in self._rules:
            if rule.is_match(sender, subject, body):
                return rule.build_result(thread_id, sender, subject)

        return None


default_rule_engine = EmailRuleEngine()
