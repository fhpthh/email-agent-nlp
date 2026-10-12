import re
from typing import Tuple

# Giới hạn kích thước đầu vào (5MB)
MAX_INPUT_BYTES_LIMIT: int = 5 * 1024 * 1024

# Ngưỡng ký tự tối thiểu để kích hoạt guard bảo vệ
MIN_BODY_LENGTH_GUARD: int = 25

# CSS Selector chứa vùng Quote/Reply trong Gmail, Outlook, Apple Mail
QUOTE_CSS_SELECTORS: Tuple[str, ...] = (
    "div.gmail_quote",
    "div.gmail_attr",
    "#divRplyFwdMsg",
    "#appendonsend",
    "blockquote",
    ".moz-cite-prefix",
    "hr#stopSpelling",
)

# Regex nhận diện email Forward (Tiếng Anh & Tiếng Việt)
FORWARD_HEADER_REGEX = re.compile(
    r"(?m)^-+\s*(?:Forwarded message|Thư được chuyển tiếp)\s*-+",
    re.IGNORECASE,
)

# Regex nhận diện Reply Header dạng Text
TEXT_REPLY_REGEXES = (
    re.compile(r"(?m)^On\s+.*?(?:<[^>]+>|\S+@\S+)\s*(?:\n\s*)?wrote:\s*$", re.IGNORECASE),
    re.compile(r"(?m)^Vào\s+.*?(?:<[^>]+>|\S+@\S+)\s*(?:\n\s*)?đã\s+viết:\s*$", re.IGNORECASE),
    re.compile(r"(?m)^From:\s+.*?\nSent:\s+.*?\n(?:To:\s+.*?\n)?(?:Cc:\s+.*?\n)?Subject:\s+.*?", re.IGNORECASE),
    re.compile(r"(?m)^Từ:\s+.*?\nĐã\s+gửi:\s+.*?\n(?:Tới|Đến):\s+.*?\n(?:Cc:\s+.*?\n)?Chủ\s+đề:\s+.*?", re.IGNORECASE),
)

# Regex nhận diện lời chào kết thư / chữ ký
SIGN_OFF_REGEX = re.compile(
    r"(?im)^(?:--\s*|Trân trọng|Thân ái|Kính thư|Thân gửi|Best regards|Warm regards|Regards|Thanks & regards|Thanks|Many thanks|Sincerely|Cheers)[,!]?\s*$"
)

# Regex nhận diện Tuyên bố miễn trừ trách nhiệm bảo mật ở cuối mail
DISCLAIMER_REGEX = re.compile(
    r"(?is)(?:\n\s*)(?:Thư này và các tài liệu đính kèm|Thông tin trong email này|This email and any attachments are confidential|This message contains confidential information).*?(?:bảo mật|tiêu hủy|xóa ngay|intended recipient|delete this email).{0,500}$"
)