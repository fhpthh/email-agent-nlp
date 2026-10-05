from enum import Enum


# Danh mục phân loại email theo nghiệp vụ
class EmailCategory(str, Enum):
    WORK = "work"
    FINANCE_BILLING = "finance_billing"
    MEETING_CALENDAR = "meeting_calendar"
    ACTION_REQUIRED = "action_required"
    CUSTOMER_SUPPORT = "customer_support"
    REPORT = "report"
    MARKETING_NEWSLETTER = "marketing_newsletter"
    PERSONAL = "personal"
    SPAM = "spam"


# Mức độ ưu tiên của việc cần làm
class PriorityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Trạng thái trong state machine xử lý email
class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"