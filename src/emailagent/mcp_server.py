import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Tự động nạp .env từ thư mục gốc của dự án
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from mcp.server.mcpserver import MCPServer
from src.emailagent.adapters.embedding.factory import get_configured_embedding_gateway
from src.emailagent.db.session import async_session_factory
from src.emailagent.services.tools import MailboxToolsService

# Tắt log stdout để không làm nhiễu giao thức JSON-RPC qua stdio của MCP
logging.basicConfig(level=logging.WARNING)

mcp = MCPServer("Email Brief Agent")

# Khởi tạo Service nghiệp vụ độc lập
tools_service = MailboxToolsService(
    embedding_gateway=get_configured_embedding_gateway(),
    session_factory=async_session_factory
)


@mcp.tool()
async def get_action_items(status: str = "open", priority: Optional[str] = None) -> str:
    """Tra cứu các đầu việc cần làm (action items), deadline và mức độ ưu tiên từ hộp thư."""
    tasks = await tools_service.get_action_items(status=status, priority=priority)
    if not tasks:
        return "Không tìm thấy nhiệm vụ nào phù hợp trong hộp thư."
    return "\n".join(
        [
            f"- [{t.priority.upper()}] {t.task} (Hạn: {t.deadline or 'Chưa rõ'}) | Thư: '{t.thread_subject}'"
            for t in tasks
        ]
    )


@mcp.tool()
async def get_urgent_threads(limit: int = 5) -> str:
    """Tra cứu các chuỗi email khẩn cấp hoặc cần người dùng trả lời gấp."""
    urgents = await tools_service.get_urgent_threads(limit=limit)
    if not urgents:
        return "Không có email khẩn cấp nào cần xử lý."
    return "\n".join(
        [
            f"- [ID: {u.thread_id}] Tiêu đề: {u.subject} (Khẩn cấp: {u.is_urgent}, Cần trả lời: {u.needs_reply})\n  Tóm tắt: {u.summary}"
            for u in urgents
        ]
    )


@mcp.tool()
async def search_mailbox(query: str, top_k: int = 5) -> str:
    """Tìm kiếm nội dung thư trong hộp thư cá nhân theo ngữ nghĩa câu hỏi bằng pgvector."""
    results = await tools_service.search_mailbox(query=query, top_k=top_k)
    if not results:
        return "Không tìm thấy email nào phù hợp với yêu cầu tìm kiếm."
    return "\n".join(
        [
            f"- [Độ tương đồng: {r.similarity_score:.2f}] Tiêu đề: {r.subject}\n  Tóm tắt: {r.summary}"
            for r in results
        ]
    )


@mcp.tool()
async def get_thread_detail(thread_id: str) -> str:
    """Đọc chi tiết toàn bộ nội dung nguyên văn các email trong một chuỗi thư cụ thể theo ID."""
    emails = await tools_service.get_thread_detail(thread_id=thread_id)
    if not emails:
        return f"Không tìm thấy email nào cho chuỗi thư {thread_id}."
    return "\n---\n".join(
        [
            f"Người gửi: {e.sender}\nNgày: {e.date_sent}\nTiêu đề: {e.subject}\nNội dung:\n{e.clean_body}"
            for e in emails
        ]
    )


@mcp.tool()
async def sync_latest_emails(days_back: int = 1) -> str:
    """Kéo và đồng bộ các email mới nhất từ hộp thư Gmail, tự động phân tích và cập nhật CSDL. Gọi công cụ này khi người dùng muốn đồng bộ toàn bộ hộp thư gần đây."""
    return await tools_service.sync_latest_emails(days_back=days_back)


@mcp.tool()
async def get_recent_emails(days_back: int = 1, unread_only: bool = False, limit: int = 10) -> str:
    """Lấy danh sách các email gần đây nhất trực tiếp từ hộp thư Gmail (kèm ngày giờ nhận và trạng thái đã đọc hay chưa đọc).
    Hãy gọi công cụ này khi người dùng hỏi: 'Hôm nay có mail nào mới không?', 'Có thư nào chưa đọc không?', 'Gần đây nhận được email gì?'."""
    emails = await tools_service.get_recent_emails(days_back=days_back, unread_only=unread_only, limit=limit)
    if not emails:
        tag = "chưa đọc" if unread_only else "mới"
        return f"Không có email {tag} nào trong {days_back} ngày qua."

    lines = []
    for idx, e in enumerate(emails, 1):
        status_tag = "CHƯA ĐỌC" if e.is_unread else "ĐÃ ĐỌC"
        lines.append(
            f"{idx}. [{status_tag}] Nhận lúc: {e.date_sent}\n"
            f"   - Người gửi: {e.sender}\n"
            f"   - Tiêu đề: {e.subject}\n"
            f"   - Nội dung trích yếu: {e.snippet}..."
        )
    return "\n\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")

