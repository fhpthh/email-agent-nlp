import asyncio
import base64
import email.utils
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.emailagent.config import settings
from src.emailagent.domain.models import RawEmailMessage
from src.emailagent.ports.provider import EmailProvider, SyncCursor

logger = logging.getLogger("emailagent.providers.gmail")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailProvider(EmailProvider):
    def __init__(self, credentials_path: Path, token_path: Path):
        self._credentials_path = credentials_path
        self._token_path = token_path
        self._service = self._authenticate_google()

    @property
    def provider_name(self) -> str:
        return "gmail"

    def _authenticate_google(self):
        """Xác thực OAuth 2.0 với Google và khởi tạo Gmail Client."""
        creds = None
        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Google OAuth token...")
                creds.refresh(Request())
            else:
                logger.info("Initiating Google OAuth login flow...")
                flow = InstalledAppFlow.from_client_secrets_file(str(self._credentials_path), SCOPES)
                creds = flow.run_local_server(port=0)

            with open(self._token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
            logger.info("Google OAuth token saved to %s", self._token_path)

        return build("gmail", "v1", credentials=creds)

    def _extract_body(self, payload: dict) -> Tuple[str, Optional[str]]:
        """Bóc tách body_text và body_html từ cấu trúc MIME Tree của Gmail."""
        body_text = ""
        body_html = None

        def _traverse_parts(part):
            nonlocal body_text, body_html
            mime_type = part.get("mimeType", "")
            data_b64 = part.get("body", {}).get("data", "")

            decoded_content = ""
            if data_b64:
                try:
                    decoded_content = base64.urlsafe_b64decode(data_b64).decode("utf-8", errors="replace")
                except Exception as exc:
                    logger.warning("Failed to decode base64 content: %s", exc)

            if mime_type == "text/plain" and not body_text:
                body_text = decoded_content
            elif mime_type == "text/html" and not body_html:
                body_html = decoded_content

            for sub_part in part.get("parts", []):
                _traverse_parts(sub_part)

        _traverse_parts(payload)
        return body_text, body_html

    def _parse_message(self, msg: dict) -> RawEmailMessage:
        """Parse raw Gmail API response dict thành domain model RawEmailMessage."""
        msg_id = msg["id"]
        payload = msg.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

        subject = headers.get("subject", "(No Subject)")
        sender = headers.get("from", "unknown")

        to_raw = headers.get("to", "")
        cc_raw = headers.get("cc", "")
        all_recipients_str = f"{to_raw},{cc_raw}"
        recipients = [r.strip() for r in all_recipients_str.split(",") if r.strip()]

        date_str = headers.get("date", "")
        try:
            date_sent = email.utils.parsedate_to_datetime(date_str)
        except Exception:
            date_sent = datetime.now(timezone.utc)

        body_text, body_html = self._extract_body(payload)

        return RawEmailMessage(
            provider_message_id=msg_id,
            provider_thread_id=msg.get("threadId", msg_id),
            sender=sender,
            recipients=recipients,
            subject=subject,
            date_sent=date_sent,
            body_text=body_text or subject,
            body_html=body_html,
        )

    def _fetch_message_sync(self, msg_id: str) -> Optional[RawEmailMessage]:
        """Tải chi tiết một email theo ID (đồng bộ)."""
        try:
            msg = self._service.users().messages().get(
                userId="me",
                id=msg_id,
                format="full"
            ).execute()
            return self._parse_message(msg)
        except Exception as exc:
            logger.error("Failed to fetch message ID %s: %s", msg_id, exc)
            return None

    async def fetch_history(
            self,
            since: datetime,
            until: datetime,
            page_token: Optional[str] = None
    ) -> Tuple[List[RawEmailMessage], Optional[str]]:
        """Lấy danh sách email cũ theo khoảng ngày từ Gmail API (Non-blocking & Concurrent)."""
        after_str = since.strftime("%Y/%m/%d")
        before_str = until.strftime("%Y/%m/%d")
        query_str = f"after:{after_str} before:{before_str}"

        logger.info("Querying Gmail messages with query: %s", query_str)

        # Chạy call list trong thread pool tránh block async loop
        result = await asyncio.to_thread(
            self._service.users().messages().list(
                userId="me",
                q=query_str,
                pageToken=page_token,
                maxResults=50
            ).execute
        )

        messages_meta = result.get("messages", [])
        next_token = result.get("nextPageToken")

        if not messages_meta:
            return [], next_token

        raw_emails: List[RawEmailMessage] = []
        for meta in messages_meta:
            mail = await asyncio.to_thread(self._fetch_message_sync, meta["id"])
            if mail is not None:
                raw_emails.append(mail)

        return raw_emails, next_token

    async def fetch_new_changes(
            self,
            cursor: SyncCursor
    ) -> Tuple[List[RawEmailMessage], SyncCursor]:
        """Đồng bộ email mới phát sinh dựa trên historyId của Gmail API."""
        start_history_id = cursor.cursor_value

        # Nếu chưa có cursor, lấy historyId hiện tại của hộp thư làm mốc khởi tạo
        if not start_history_id:
            logger.info("Cursor history_id not found. Initializing sync cursor with current profile.")
            profile = await asyncio.to_thread(
                self._service.users().getProfile(userId="me").execute
            )
            current_history_id = profile.get("historyId")
            updated_cursor = SyncCursor(
                account_id=cursor.account_id,
                cursor_value=str(current_history_id),
                updated_at=datetime.now(timezone.utc)
            )
            return [], updated_cursor

        try:
            history_response = await asyncio.to_thread(
                self._service.users().history().list(
                    userId="me",
                    startHistoryId=str(start_history_id),
                    historyTypes=["messageAdded"]
                ).execute
            )
        except HttpError as err:
            if err.resp.status == 404:
                logger.warning("History ID is out of date or invalid. Resetting cursor.")
                profile = await asyncio.to_thread(
                    self._service.users().getProfile(userId="me").execute
                )
                current_history_id = profile.get("historyId")
                updated_cursor = SyncCursor(
                    account_id=cursor.account_id,
                    cursor_value=str(current_history_id),
                    updated_at=datetime.now(timezone.utc)
                )
                return [], updated_cursor
            raise

        histories = history_response.get("history", [])
        new_msg_ids = set()
        for h in histories:
            for added in h.get("messagesAdded", []):
                msg_info = added.get("message", {})
                if "id" in msg_info:
                    new_msg_ids.add(msg_info["id"])

        raw_emails: List[RawEmailMessage] = []
        for msg_id in new_msg_ids:
            mail = await asyncio.to_thread(self._fetch_message_sync, msg_id)
            if mail is not None:
                raw_emails.append(mail)

        latest_history_id = history_response.get("historyId", start_history_id)
        updated_cursor = SyncCursor(
            account_id=cursor.account_id,
            cursor_value=str(latest_history_id),
            updated_at=datetime.now(timezone.utc)
        )
        return raw_emails, updated_cursor

    def get_profile(self) -> Tuple[str, str]:
        profile = self._service.users().getProfile(userId="me").execute()
        email_address = profile.get("emailAddress", settings.FALLBACK_OWNER_EMAIL)
        owner_name = email_address.split("@")[0]
        return email_address, owner_name