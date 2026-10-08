import hashlib
import re
from datetime import date
from typing import Optional, Union

def compute_action_item_fingerprint(
    task: str,
    deadline: Optional[Union[date, str]] = None
) -> str:

    # chuan hoa task text
    clean_task = task.strip().lower()
    clean_task = re.sub(r"[^\w\s]", "", clean_task)
    clean_task = re.sub(r"\s+", " ", clean_task)

    # chuan hoa deadline
    deadline_str = str(deadline) if deadline else "No_deadline"

    raw_payload = f"{clean_task}|{deadline_str}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()[:24]