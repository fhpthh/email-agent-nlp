# EMAIL AGENT

> **AI Agent** — Tự động thu thập, phân loại, tóm tắt chuỗi email, trích xuất việc cần làm
> và hỏi đáp dữ liệu hộp thư theo thời gian thực (Hybrid RAG & Analytics).

---

## Nguyên lý thiết kế

* **Hybrid RAG Search:** Kết hợp **Dense Vector (pgvector HNSW)** và **Sparse FTS (PostgreSQL unaccent)** qua thuật toán
  **RRF (Reciprocal Rank Fusion)**.
* **Tối ưu GIN Index & Tiệm cận BM25:**
    * Hàm SQL `clean_fts_vietnamese` lọc từ tiếng Việt subword  $\rightarrow$ **Giảm dung lượng GIN index**.
    * **Field Weighting:** Ưu tiên Tiêu đề (Weight A = 1.0) hơn Thân thư (Weight B = 0.4).
    * **Document Length Normalization:** Áp dụng cờ `32` trên `ts_rank_cd` để phạt tài liệu dài.
* **Enriched Vector Embedding:**
    * Băm vector đầy đủ: **Subject + Senders + Category + Summary + Action Items + 500 ký tự Body mới nhất**.
    * Khắc phục lỗi "Mù người gửi", mất mã hóa đơn (`INV-...`) trong body, và không phụ thuộc mù quáng vào
      Summary của LLM.
* **Intent Routing & Self-Querying (Chống ảo giác số liệu):**
    * Tự động bóc tách thời gian động ("tháng trước", "quý 3", "hôm qua") thành timestamp ISO 8601 chuẩn xác.
    * **Luồng `SEARCH`:** Tra cứu ngữ nghĩa qua Hybrid RAG Top-K.
    * **Luồng `ANALYTICS`:** Chạy trực tiếp SQL `COUNT(*)` từ Database $\rightarrow$ Số liệu chính xác 100%, không bị
      giới hạn Top-K.
* **2-Tier NLP Engine:**
    * **Tầng 1 (Fast-Path):** Rule Engine regex bắt OTP, hóa đơn, thông báo hệ thống $\rightarrow$ **0 Token chi phí**,
      độ trễ < 1ms.
    * **Tầng 2 (Cognitive-Path):** Gom batch 5 threads/lần gọi Gemini Flash / LiteLLM Proxy kèm XML Sandboxing phòng vệ
      Prompt Injection.
* **Chống trùng lặp Task:** Băm **SHA-256 Fingerprint** (`task + deadline`) với ràng buộc `UNIQUE` trong CSDL, chạy
  idempotent an toàn.
* **Chạy ngầm tự động (Scheduler):** `APScheduler` chạy định kỳ 15 phút/chu kỳ, chống tràn RAM và chống chạy đè
  (`max_instances=1`).
* **Hỗ trợ Model Context Protocol (MCP):** Cung cấp 6 công cụ thao tác hòm thư chuẩn MCP cho Claude Desktop, Cursor IDE.

---

## Sơ Đồ Kiến Trúc (Architecture)

```
                            [NGƯỜI DÙNG / MCP CLIENT]
                                       │
                                       ▼
                     +-----------------------------------+
                     |       FastAPI / MCP Server        |
                     +-----------------------------------+
                                       │
                                       ▼
                     +-----------------------------------+
                     |     TẦNG DỊCH VỤ (APPLICATION)    |
                     |  Ingestion | Analysis | QA | Sync |
                     +-----------------------------------+
                                       │
                      ┌────────────────┴────────────────┐
                      ▼                                 ▼
         +────────────────────────+        +────────────────────────+
         |   PORTS & DOMAIN DTOs  |        |    ADAPTERS (HẠ TẦNG)  |
         |  EmailProvider, LLM,   |        |  Gmail API (OAuth2)    |
         |  Embedding Gateway     |        |  Gemini / LiteLLM      |
         +────────────────────────+        |  PostgreSQL 16 + HNSW  |
                                           +────────────────────────+
```

### Cấu Trúc Thư Mục Tinh Gọn

```
email-agent/
├── docker-compose.yml              # PostgreSQL 16 + pgvector (Port 5434)
├── requirements.txt                # Thư viện phụ thuộc
├── scripts/
│   ├── schema.sql                  # Khởi tạo bảng, index và function CSDL
│   └── migration_fts_optimize.sql  # Script tối ưu Stopwords & GIN index
├── src/emailagent/
│   ├── config.py                   # Cấu hình tập trung (.env & Settings)
│   ├── mcp_server.py               # Server Model Context Protocol (JSON-RPC)
│   ├── domain/                     # Entities & Pydantic Models (QueryFormulationResult...)
│   ├── ports/                      # Interfaces (Provider, LLM, Embedding)
│   ├── adapters/
│   │   ├── provider/               # Gmail OAuth2 & Mock Provider
│   │   ├── llm/                    # GeminiLLMGateway & LiteLLMGateway (Factory)
│   │   ├── embedding/              # Gemini & LiteLLM Embedding Gateway
│   │   └── db/
│   │       ├── session.py          # SQLAlchemy async session factory
│   │       └── repositories/       # Phân tầng Repository (Facade Pattern)
│   │           ├── base.py         # BaseRepository
│   │           ├── account.py      # Quản lý tài khoản hộp thư
│   │           ├── email.py        # Ingestion & đồng bộ thư
│   │           ├── analysis.py     # Action Items & SQL get_analytics_summary
│   │           ├── search.py       # Vector HNSW + Weighted FTS + RRF
│   │           └── __init__.py     # EmailRepository Facade
│   ├── prompts/                    # Quản lý Prompts tập trung
│   │   ├── qa.py                   # System instruction QA & Context block
│   │   ├── analysis.py             # Prompt phân tích chuỗi email & trích xuất task
│   │   ├── rewriter.py             # Self-Querying, Intent Routing & Query Expansion
│   │   └── __init__.py             # build_thread_embedding_text helper
│   ├── services/                   # Application Services (Ingestion, Analysis, QA, Embedding)
│   ├── utils/                      # Tiền xử lý (Cleaner, Prefilter, Stopwords, Security)
│   ├── resources/                  # vietnamese_stopwords.txt
│   └── routers/                    # FastAPI Endpoints (sync.py, analysis.py, chat.py)
└── tests/                          # Unit & Integration Tests
```

---

## 🗄️ Thiết Kế Cơ Sở Dữ Liệu (Database Schema)

Hệ thống sử dụng **PostgreSQL 16** với các extension: `vector` (HNSW), `unaccent`, `pg_trgm`.

```mermaid
erDiagram
    accounts ||--o{ threads: "sở hữu"
    accounts ||--o{ emails: "nhận"
    threads ||--o{ emails: "chứa"
    threads ||--o{ action_items: "sinh ra"

    accounts {
        UUID id PK
        TEXT email_address UK
        TEXT owner_name
        TEXT timezone
        JSONB cursor_state "Lưu historyId đồng bộ gia tăng"
    }

    threads {
        UUID id PK
        TEXT subject
        TEXT summary "Tóm tắt 2-3 câu"
        TEXT category "work, finance, report..."
        BOOLEAN is_urgent "Cần xử lý trong ngày"
        BOOLEAN needs_reply "Chờ trả lời"
        VECTOR_768 embedding "Chỉ mục HNSW"
    }

    emails {
        UUID id PK
        TEXT sender
        TIMESTAMPTZ date_sent
        TEXT subject
        TEXT clean_body "Nội dung sạch đã cắt reply/chữ ký"
        TSVECTOR tsv "Cột phái sinh: Subject A + Body B - Stopwords"
    }

    action_items {
        UUID id PK
        TEXT task "Động từ hành động đứng đầu"
        TEXT assignee "Người phụ trách"
        DATE deadline "YYYY-MM-DD"
        TEXT priority "high, medium, low"
        TEXT fingerprint "SHA-256 hash chống trùng task"
    }
```

---

## Luồng Xử Lý Hỏi Đáp (Hybrid RAG & Analytics Flow)

```
[CÂU HỎI NGƯỜI DÙNG]
        │
        ▼
[REWRITER & INTENT CLASSIFIER] ──> Tự động bóc tách:
        │                          - Từ đồng nghĩa (expanded_keywords)
        │                          - Mốc thời gian động (date_after, date_before)
        │                          - Phân loại Intent (SEARCH vs ANALYTICS)
        │
   ┌────┴─────────────────────────────────────────┐
   ▼                                              ▼
[INTENT: SEARCH]                              [INTENT: ANALYTICS]
"Họp dự án X nói gì?"                        "Tháng này có bao nhiêu hóa đơn?"
"Deadline nộp bài..."                         "Có mấy việc chưa hoàn thành?"
   │                                              │
   ▼                                              ▼
[HYBRID RETRIEVAL]                            [DATABASE ANALYTICS]
- Dense Vector (pgvector HNSW)                - Chạy trực tiếp SQL COUNT(*)
- Sparse FTS (Weighted ts_rank_cd)            - Không dùng RAG Top-K
   │                                              │
   ▼                                              │
[RRF FUSION: Top-K] ──────────────────────────────┤
                                                  ▼
                                       [LLM SYNTHESIZER]
                                       - Bắt buộc xuất Markdown Table
                                       - Mốc thời gian mới nhất là chân lý
                                                  │
                                                  ▼
                                       [CÂU TRẢ LỜI CHÍNH XÁC]
```

---

## Danh Sách MCP Tools (Model Context Protocol)

File chạy: `src/emailagent/mcp_server.py`. Kết nối trực tiếp vào Claude Desktop / Cursor IDE:

| Công cụ                              | Mô tả ngắn                                              |
|:-------------------------------------|:--------------------------------------------------------|
| `search_mailbox(query, top_k)`       | Tìm kiếm ngữ nghĩa trong hộp thư qua pgvector           |
| `get_action_items(status, priority)` | Tra cứu danh sách việc cần làm, deadline và độ ưu tiên  |
| `get_urgent_threads(limit)`          | Lọc nhanh các email khẩn cấp hoặc đang chờ trả lời      |
| `get_thread_detail(thread_id)`       | Đọc chi tiết nội dung từng email trong 1 luồng thư      |
| `sync_latest_emails(days_back)`      | Đồng bộ hòm thư từ Gmail, tự động tóm tắt và băm vector |
| `get_recent_emails(days_back, ...)`  | Đọc thư mới nhất trực tiếp từ Gmail theo giờ UTC+7      |

---

## Hướng Dẫn Cài Đặt & Chạy Hệ Thống

### 1. Khởi động Cơ sở dữ liệu

```bash
docker compose up -d
# Chạy migration tối ưu FTS và GIN index
docker exec -i email_agent_postgres psql -U postgres -d email_agent_db < scripts/migration_fts_optimize.sql
```

### 2. Thiết lập Môi trường Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Cấu hình biến môi trường (`.env`)

Tạo file `.env` từ mẫu:

```ini
APP_NAME = Email Brief Agent
DATABASE_URL = postgresql+asyncpg://huepth:huepth123@localhost:5434/email_agent_db

ACTIVE_EMAIL_PROVIDER = gmail

# AI Gateway (Hỗ trợ Gemini Native hoặc LiteLLM Proxy)
LLM_PROVIDER = litellm
LITELLM_BASE_URL = http://172.18.5.44:8000/mlbigdata/proxyllm
LITELLM_API_KEY = your_key_here
LITELLM_MODEL = gemini/gemini-3.8-flash

EMBEDDING_PROVIDER = litellm
EMBEDDING_MODEL_NAME = gemini/gemini-embedding-001
VECTOR_DIMENSION = 768
```

### 4. Khởi chạy Dịch vụ

* **Khởi chạy REST API Server:**
  ```bash
  uvicorn src.emailagent.api.main:app --host 0.0.0.0 --port 8000 --reload
  ```
  *Tài liệu Swagger UI tương tác:* `http://localhost:8000/docs`.

* **Khởi chạy MCP Server (Cho Claude Desktop / Cursor):**
  ```bash
  python -m src.emailagent.mcp_server
  ```
