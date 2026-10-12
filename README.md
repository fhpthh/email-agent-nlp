#  EMAIL AGENT

### *Intelligent Autonomous Email Assistant, Hybrid RAG & Task Extraction System*

---

##  MỤC LỤC

1. [Giới Thiệu Tổng Quan](#1-giới-thiệu-tổng-quan)
2. [Kiến Trúc Hệ Thống (Architecture)](#2-kiến-trúc-hệ-thống-architecture)
3. [Thiết Kế Cơ Sở Dữ Liệu (Database Schema)](#3-thiết-kế-cơ-sở-dữ-liệu-database-schema)
4. [Quy Trình Xử Lý NLP & Trí Tuệ Nhân Tạo (NLP Pipeline)](#4-quy-trình-xử-lý-nlp--trí-tuệ-nhân-tạo-nlp-pipeline)
5. [Cơ Chế Hybrid RAG & Bộ Nhớ Ngữ Nghĩa (Hybrid Search & RRF)](#5-cơ-chế-hybrid-rag--bộ-nhớ-ngữ-nghĩa-hybrid-search--rrf)
6. [Tiến Trình Chạy Ngầm Tự Động (Autonomous Background Scheduler)](#6-tiến-trình-chạy-ngầm-tự-động-autonomous-background-scheduler)
7. [Máy Chủ Giao Thức Model Context Protocol (MCP Server)](#7-máy-chủ-giao-thức-model-context-protocol-mcp-server)
8. [Tài Liệu Chi Tiết REST API (Endpoints, Request & Response)](#8-tài-liệu-chi-tiết-rest-api-endpoints-request--response)
9. [Hướng Dẫn Cài Đặt & Triển Khai (Deployment Guide)](#9-hướng-dẫn-cài-đặt--triển-khai-deployment-guide)

---

## 1. GIỚI THIỆU TỔNG QUAN

**Email Brief Agent**  Hệ thống tự động thu thập, làm sạch, phân loại, tóm tắt các chuỗi email dài, trích xuất việc
cần làm kèm hạn chót (Action Items), đồng thời cung cấp giao diện hỏi đáp ngữ nghĩa (RAG Q&A) không ảo giác với trích
dẫn minh bạch.

###  Tính Năng Cốt Lõi

* **Tự động hóa Ingestion đa nền tảng:** Tích hợp Gmail API (OAuth 2.0) với cơ chế đồng bộ gia tăng (Incremental Sync
  qua `historyId`) và Mock Provider phục vụ kiểm thử.
* **Tiền xử lý văn bản Enterprise Preprocessing):** Bóc tách DOM HTML thành bảng Markdown, nhận diện
  email Forward/Reply đa ngôn ngữ (Anh - Việt), loại bỏ chữ ký và tuyên bố bảo mật có guard an toàn.
* **Hybrid 2-Tier NLP Engine:**
    * *Tầng 1 (Fast-Path Rule Engine):* Lọc 100% email mẫu (OTP, Newsletter, Hóa đơn, Thông báo hệ thống) với **0 Token
      chi phí** và độ trễ < 1ms.
    * *Tầng 2 (Cognitive-Path LLM Batching):* Gom 5 chuỗi phức tạp gọi **Google Gemini Flash** với kỹ thuật phòng vệ
      Prompt Injection (XML Sandboxing) và ép kiểu Pydantic Structured Output.
* **Trích xuất & Chống trùng lặp nhiệm vụ (Task Deduplication):** Tự động phát hiện deadline, quy đổi ngày tương đối (
  "sáng mai", "thứ 6") thành ngày tuyệt đối `YYYY-MM-DD`, băm **SHA-256 Fingerprint** ngăn chặn hoàn toàn việc tạo trùng
  task.
* **Bộ nhớ ngữ nghĩa Hybrid RAG & RRF:** Kết hợp tìm kiếm Dense Vector (pgvector HNSW) và Sparse Full-Text Search
  (PostgreSQL unaccent) qua thuật toán **Reciprocal Rank Fusion (RRF)**; làm giàu ngữ cảnh hội thoại chống nạn đói thông
  tin.
* **Tiến trình tự động hóa chạy ngầm (Autonomous Scheduler):** Tích hợp `APScheduler` tự động kích hoạt chu kỳ đồng bộ
  định kỳ mà không cần người dùng thao tác thủ công, có cơ chế chống nghẽn và kiểm soát Rate Limit.
* **Tích hợp mở rộng qua MCP Server:** Cung cấp 6 công cụ thao tác hộp thư theo chuẩn Model Context Protocol kết nối
  trực tiếp với Claude Desktop, Cursor IDE, Antigravity.

---

## 2. KIẾN TRÚC HỆ THỐNG (ARCHITECTURE)

```
                      +------------------------------------------+
                      |         FastAPI REST / MCP Clients       |
                      +------------------------------------------+
                                           │
                                           ▼
                      +------------------------------------------+
                      |       TẦNG DỊCH VỤ (APPLICATION)         |
                      | - IngestionService   - AnalysisService   |
                      | - EmbeddingService   - MailboxQAService  |
                      | - ToolsService       - SchedulerRunner   |
                      +------------------------------------------+
                                    │             │
                ┌───────────────────┘             └───────────────────┐
                ▼                                                     ▼
    +────────────────────────+                           +────────────────────────+
    |   PORTS (INTERFACES)   |                           |    DOMAIN & SCHEMAS    |
    | - EmailProvider        |                           | - Models & Enums       |
    | - LLMGateway           |                           | - Tools DTOs           |
    | - EmbeddingGateway     |                           | - CleanedEmailPayload  |
    +────────────────────────+                           +────────────────────────+
                │
                ▼
    +─────────────────────────────────────────────────────────────────────────────+
    |                         ADAPTERS (INFRASTRUCTURE)                           |
    | - GmailProvider (OAuth2)                 - GeminiLLMGateway (Structured)    |
    | - FakeEmailProvider (Mock)               - GeminiEmbeddingGateway (768-dim) |
    | - EmailRepository (SQLAlchemy / asyncpg) - PostgreSQL 16 (pgvector + FTS)   |
    +─────────────────────────────────────────────────────────────────────────────+
```

### 📂 Cấu Trúc Thư Mục Dự Án

```
email-agent/
├── docker-compose.yml              # Dựng PostgreSQL 16 + pgvector container
├── requirements.txt                # Thư viện phụ thuộc của dự án
├── scripts/
│   └── schema.sql                  # Khởi tạo CSDL, extensions, indexes & functions
├── src/emailagent/
│   ├── config.py                   # Cấu hình tập trung (Pydantic Settings & .env)
│   ├── mcp_server.py               # Máy chủ Model Context Protocol (stdio JSON-RPC)
│   ├── domain/                     # Entities & Data Transfer Objects (DTO)
│   │   ├── enums.py                # EmailCategory, PriorityLevel, ProcessingStatus
│   │   ├── models.py               # Pydantic models (ThreadInsight, RetrievedContext...)
│   │   └── tools_models.py         # DTOs chuyên biệt cho công cụ MCP/Tools
│   ├── ports/                      # Giao diện trừu tượng (Abstract Interfaces)
│   │   ├── provider.py             # EmailProvider interface & SyncCursor
│   │   ├── llm.py                  # LLMGateway interface & UntrustedPayload
│   │   └── embedding.py            # EmbeddingGateway interface
│   ├── adapters/                   # Triển khai hạ tầng kỹ thuật cụ thể
│   │   ├── provider/               # GmailProvider (OAuth2) & FakeEmailProvider
│   │   ├── llm/                    # GeminiLLMGateway (Google GenAI SDK)
│   │   ├── embedding/              # GeminiEmbeddingGateway (gemini-embedding-001)
│   │   └── db/                     # EmailRepository (PostgreSQL queries)
│   ├── services/                   # Use cases và điều phối nghiệp vụ chính
│   │   ├── ingestion.py            # Đồng bộ và làm sạch thư
│   │   ├── analysis.py             # Phân tích 2 tầng: Rule Engine + Gemini Batching
│   │   ├── embedding.py            # Tính toán vector nhúng cho threads
│   │   ├── qa.py                   # RAG Q&A pipeline (Grounded reasoning)
│   │   ├── tools.py                # Đóng gói 6 công cụ thao tác hộp thư
│   │   └── scheduler/              # Tiến trình chạy ngầm định kỳ
│   │       ├── orchestrator.py     # Điều phối luồng Ingest -> Analyze -> Embed
│   │       └── runner.py           # Quản lý vòng đời AsyncIOScheduler
│   ├── utils/                      # Tiện ích tiền xử lý & NLP
│   │   ├── cleaner/                # Bộ tiền xử lý email đa tầng (DOM, Unicode, Reply)
│   │   ├── fingerprint.py          # Tính SHA-256 hash chống trùng task
│   │   ├── prefilter.py            # EmailRuleEngine 0-token (OTP, Hóa đơn, Promo)
│   │   └── prompt.py               # XML sandboxing & grounded system prompts
│   ├── db/
│   │   └── session.py              # Async SQLAlchemy engine & session factory
│   └── api/                        # Giao tiếp HTTP REST (FastAPI)
│       ├── main.py                 # Lifespan app & Health check endpoint
│       └── routers/                # sync.py, analysis.py, chat.py
└── tests/                          # Bộ kiểm thử tự động (Unit & Integration tests)
```

---

## 3. THIẾT KẾ CƠ SỞ DỮ LIỆU (DATABASE SCHEMA)

Hệ thống sử dụng **PostgreSQL 16** kết hợp các Extension:

* `vector`: Kiểu dữ liệu `VECTOR(768)` và toán tử Cosine distance `<=>`.
* `unaccent`: Loại bỏ dấu tiếng Việt, kết hợp hàm wrapper `immutable_unaccent` phục vụ Generated Columns.
* `pg_trgm`: Hỗ trợ tìm kiếm xấp xỉ chuỗi (Trigram).

```mermaid
erDiagram
    accounts ||--o{ threads: "owns"
    accounts ||--o{ emails: "receives"
    threads ||--o{ emails: "contains"
    threads ||--o{ action_items: "produces"

    accounts {
        UUID id PK
        TEXT provider "gmail | fake | outlook"
        TEXT email_address UK
        TEXT owner_name
        TEXT timezone "Asia/Ho_Chi_Minh"
        JSONB cursor_state "Lưu historyId (Gmail)"
        TIMESTAMPTZ created_at
    }

    threads {
        UUID id PK
        UUID account_id FK
        TEXT provider_thread_id
        TEXT subject
        TIMESTAMPTZ last_message_at
        TEXT summary "Tóm tắt 2-3 câu"
        TEXT category "work | finance_billing | ..."
        BOOLEAN is_urgent "Khẩn cấp trong ngày"
        BOOLEAN needs_reply "Chờ chủ thư phản hồi"
        VECTOR_768 embedding "Chỉ mục HNSW"
        TIMESTAMPTZ created_at
    }

    emails {
        UUID id PK
        UUID account_id FK
        UUID thread_id FK
        TEXT provider_message_id
        TEXT sender
        TEXT_ARRAY recipients
        TIMESTAMPTZ date_sent
        TEXT subject
        TEXT clean_body "Văn bản sạch đã bóc tách"
        TEXT status "PENDING | PROCESSED | FAILED"
        TSVECTOR tsv "Cột tự sinh Generated unaccent FTS"
    }

    action_items {
        UUID id PK
        UUID thread_id FK
        TEXT task "Hành động (động từ đứng đầu)"
        TEXT assignee "Người phụ trách"
        DATE deadline "Ngày cụ thể YYYY-MM-DD"
        TEXT priority "high | medium | low"
        TEXT status "open | done"
        TEXT evidence "Trích dẫn nguyên văn"
        TEXT fingerprint "SHA-256 hash chống trùng"
        TIMESTAMPTZ created_at
    }
```

### ⚡ Chỉ Mục Tối Ưu Hóa (Indexes)

1. **Chỉ mục Vector HNSW (Hierarchical Navigable Small World):**  
   `CREATE INDEX idx_threads_hnsw ON threads USING hnsw (embedding vector_cosine_ops);`  
   Tối ưu hóa tìm kiếm xấp xỉ vector với độ phức tạp $O (\log N)$.
2. **Chỉ mục GIN Full-Text Search:**  
   `CREATE INDEX idx_emails_fts ON emails USING GIN(tsv);`  
   Hỗ trợ tìm kiếm từ khóa tiếng Việt không dấu siêu tốc.
3. **Chỉ mục B-Tree Nghiệp Vụ:**  
   `CREATE INDEX idx_emails_date ON emails(account_id, date_sent DESC);`  
   `CREATE INDEX idx_action_items_deadline ON action_items(status, deadline);`

---

## 4. QUY TRÌNH XỬ LÝ NLP & TRÍ TUỆ NHÂN TẠO (NLP PIPELINE)

Hệ thống xử lý văn bản theo luồng 5 bước tối ưu hóa chi phí và bảo mật:

```
[Raw Email (HTML/MIME)]
         │
         ▼
[BƯỚC 1: Tiền Xử Lý Đa Tầng (Cleaner Package)]
- DOMExtractor: lxml bóc CSS selectors, chuyển table HTML thành bảng Markdown
- TextNormalizer: Chuẩn hóa Unicode NFC, lọc sạch ký tự ẩn (zero-width chars)
- ThreadSplitter: Nhận diện Forward (giữ nguyên) & Reply Header tiếng Anh/Việt
- NoiseStripper: Cắt chữ ký và Disclaimer pháp lý có guard bảo vệ (>40% cuối thư)
         │
         ▼
[BƯỚC 2: Tầng Lọc Quy Tắc Fast-Path (0 Token)]
- EmailRuleEngine: Regex bắt mã OTP, Newsletter, Hóa đơn điện tử, Mail no-reply
         │
         ├── Khớp luật ──> Lưu DB & Đánh dấu PROCESSED (Chi phí 0đ, độ trễ < 1ms)
         │
         ▼ Chưa khớp (Chuỗi trao đổi công việc phức tạp)
[BƯỚC 3: Tầng Nhận Thức LLM Batching (Cognitive-Path)]
- Gom nhóm 5 threads/batch đưa vào 1 prompt duy nhất
- XML Sandboxing: Đóng gói thẻ <untrusted_message id="..."> chống Prompt Injection
- Context Grounding: Nạp mốc thời gian tham chiếu (reference_date) & timezone
- Đánh giá needs_reply dựa trên người gửi cuối cùng so với chủ hộp thư
- Ép kiểu JSON Schema tuyệt đối qua Gemini Structured Output
         │
         ▼
[BƯỚC 4: Trích Xuất Action Items & Khử Trùng Lặp]
- Quy đổi thời gian tương đối ("chiều nay", "thứ 6") thành ngày tuyệt đối YYYY-MM-DD
- Băm SHA-256 Fingerprint: clean_task + deadline
- Lưu Database với ràng buộc UNIQUE(thread_id, fingerprint) ON CONFLICT DO NOTHING
         │
         ▼
[BƯỚC 5: Đồng Bộ Vector Memory (768 chiều)]
- Ghép chuỗi đặc trưng: Subject + Category + Summary + Action Items
- Nhúng qua gemini-embedding-001 và cập nhật vào cột threads.embedding
```

---

## 5. CƠ CHẾ HYBRID RAG & BỘ NHỚ NGỮ NGHĨA (HYBRID SEARCH & RRF)

Khi người dùng đặt câu hỏi ngôn ngữ tự nhiên về hộp thư cá nhân, quy trình RAG thực hiện:

### 1. Tìm Kiếm Lai Kết Hợp Thuật Toán RRF (Reciprocal Rank Fusion)

Thay vì chỉ dùng Vector Cosine đơn độc, hệ thống kích hoạt đồng thời 2 luồng tìm kiếm:

* **Dense Vector Search:** Dùng toán tử Cosine `<=>` trên `threads.embedding` với Top $K \times 2$.
* **Sparse Full-Text Search:** Dùng `e.tsv @@ plainto_tsquery('simple', immutable_unaccent(:text_query))` trên `emails`
  với Top $K \times 2$.
* **Hợp nhất điểm số (RRF Score):**
  $$\text{RRF\_Score} (d) = \sum_{m \in \{\text{Dense, Sparse}\}} \frac{1}{60 + \text{Rank}_m (d)}$$
* **Soft Fallback Threshold:** Nếu điểm Cosine không chạm ngưỡng khắt khe `0.60`, hệ thống tự động hạ xuống
  `RAG_MIN_FALLBACK_THRESHOLD = 0.40` để tránh bị loại sạch kết quả.

### 2. Làm Giàu Ngữ Cảnh (Context Enrichment)

Bằng việc sử dụng SQL Window Function:

```sql
ROW_NUMBER
() OVER (PARTITION BY e.thread_id ORDER BY e.date_sent DESC) <= 3
```

Hệ thống lấy Top 3 tin nhắn mới nhất của chuỗi (`sender`, `date_sent`, `body_snippet` 800 ký tự) nạp vào thẻ
`<recent_messages>`. LLM có đầy đủ dữ kiện về **người gửi, ngày giờ và trích đoạn nguyên văn** để trả lời chính xác
100%, không bị ảo giác.

### 3. Nguyên Tắc Phản Hồi Bắt Buộc (Grounded Citations)

Mô hình bị ràng buộc chỉ trả lời dựa trên thẻ `<context>` và bắt buộc trả về mảng `citations` chứa `thread_id`,
`subject`, `evidence` để người dùng kiểm chứng.

---

## 6. TIẾN TRÌNH CHẠY NGẦM TỰ ĐỘNG (AUTONOMOUS BACKGROUND SCHEDULER)

Hệ thống tích hợp `APScheduler` (AsyncIOScheduler) trực tiếp vào vòng đời của FastAPI (`lifespan`), tự động kích hoạt
chu kỳ đồng bộ định kỳ mà không cần người dùng thao tác.

### Cơ Chế Hoạt Động & Bảo Vệ

* **Chu kỳ mặc định:** 15 phút/lần (cấu hình động qua biến `SCHEDULER_INTERVAL_MINUTES`).
* **Quy trình khép kín:** `Ingest recent emails` -> `Analyze pending threads` -> `Sync vector embeddings`.
* **Chống rò rỉ RAM (Zero Memory Leak):** Áp dụng Scoped Session (`async with session_factory()`), giải phóng bộ nhớ
  ngay sau khi kết thúc chu kỳ.
* **Chống chạy chồng chéo:** `max_instances=1` và `coalesce=True` (nếu chu kỳ trước gặp mạng chậm chạy quá 15 phút, chu
  kỳ sau sẽ tự động bỏ qua, không chạy đè).
* **Kiểm soát Rate Limit:** Mỗi chu kỳ giới hạn tối đa 15 threads, giãn cách an toàn giữa các lượt gọi Gemini.

---

## 7. MÁY CHỦ GIAO THỨC MODEL CONTEXT PROTOCOL (MCP SERVER)

File thực thi: `src/emailagent/mcp_server.py`. Chạy độc lập qua kênh truyền thông `stdio` (JSON-RPC), sẵn sàng kết nối
vào các AI Client (Claude Desktop, Cursor IDE, Antigravity).

### Danh Sách 6 Công Cụ MCP

1. **`get_action_items(status, priority)`:** Tra cứu danh sách việc cần làm, hạn chót và mức độ ưu tiên.
2. **`get_urgent_threads(limit)`:** Lọc nhanh các email khẩn cấp hoặc đang chờ chủ thư trả lời.
3. **`search_mailbox(query, top_k)`:** Tìm kiếm ngữ nghĩa trong hộp thư qua pgvector.
4. **`get_thread_detail(thread_id)`:** Đọc chi tiết nội dung nguyên văn các email trong 1 chuỗi thư.
5. **`sync_latest_emails(days_back)`:** Đồng bộ toàn diện hộp thư từ Gmail, tự động phân tích và cập nhật vector CSDL.
6. **`get_recent_emails(days_back, unread_only, limit)`:** Đọc danh sách thư mới nhất trực tiếp từ Gmail kèm trạng thái
   đọc/chưa đọc theo giờ chuẩn Việt Nam (UTC+7).

---

## 8. TÀI LIỆU CHI TIẾT REST API (ENDPOINTS, REQUEST & RESPONSE)

Tài liệu tương tác Swagger UI: `http://localhost:8000/docs`.

### 8.1. System Endpoints

#### `GET /health`

* **Mô tả:** Kiểm tra trạng thái hoạt động của hệ thống và tiến trình chạy ngầm.
* **Request:** Không tham số.
* **Response (200 OK):**

```json
{
  "status": "healthy",
  "app_name": "Email Brief Agent",
  "environment": "development",
  "scheduler_running": true
}
```

---

### 8.2. Sync Endpoints

#### `POST /api/sync/backfill`

* **Mô tả:** Kích hoạt kéo email lịch sử từ Gmail hoặc Mock Provider vào CSDL.
* **Request Body (JSON):**

```json
{
  "days_back": 30,
  "date_from": null,
  "date_to": null
}
```

* **Response (200 OK):**

```json
{
  "status": "success",
  "owner_email": "user@vccorp.vn",
  "date_range": {
    "since": "2026-09-12T15:00:00+00:00",
    "until": "2026-10-12T15:00:00+00:00"
  },
  "ingested_count": 48
}
```

#### `GET /api/sync/emails`

* **Mô tả:** Truy vấn danh sách email đã ingest trong CSDL.
* **Query Parameters:** `limit` (int, default: 50).
* **Response (200 OK):** Danh sách mảng các đối tượng email tóm tắt.

---

### 8.3. Analysis Endpoints

#### `POST /api/analysis/process-pending`

* **Mô tả:** Quét các chuỗi thư có email `PENDING`, tự động chạy qua Rule Engine (Tầng 1) và gom batch gọi Gemini (Tầng
  2).
* **Query Parameters:** `limit` (default: 20), `batch_size` (default: 5).
* **Response (200 OK):**

```json
{
  "status": "completed",
  "total_threads": 8,
  "rule_filtered": 5,
  "llm_processed": 3,
  "total_api_calls": 1,
  "succeeded": 8,
  "failed": 0,
  "details": [
    {
      "thread_id": "8b51d6c8-1111-4a3e-9082-9f6b907c1234",
      "status": "success",
      "source": "llm",
      "category": "work",
      "is_urgent": true,
      "needs_reply": false,
      "summary": "Trưởng phòng yêu cầu hoàn thiện tài liệu kiến trúc AI Agent trước 17h chiều nay.",
      "action_items_count": 1
    }
  ]
}
```

#### `POST /api/analysis/threads/{thread_id}`

* **Mô tả:** Phân tích tức thời một chuỗi email cụ thể theo UUID.
* **Path Parameter:** `thread_id` (UUID).
* **Response (200 OK):** Kết quả phân tích chi tiết của chuỗi thư đó.

---

### 8.4. Chat & RAG Assistant Endpoints

#### `POST /api/chat/sync-embeddings`

* **Mô tả:** Quét các chuỗi thư đã có summary nhưng chưa có vector và tính toán vector nhúng 768 chiều.
* **Query Parameters:** `limit` (default: 50), `batch_size` (default: 10).
* **Response (200 OK):**

```json
{
  "total_found": 12,
  "synced": 12,
  "failed": 0
}
```

#### `POST /api/chat/ask`

* **Mô tả:** Hỏi đáp ngôn ngữ tự nhiên về hộp thư cá nhân với AI Agent (có kèm trích dẫn nguồn).
* **Request Body (JSON):**

```json
{
  "query": "Hạn nộp tự đánh giá KPI Quý 3 là khi nào?",
  "account_id": null
}
```

* **Response (200 OK):**

```json
{
  "query": "Hạn nộp tự đánh giá KPI Quý 3 là khi nào?",
  "answer": "Hạn nộp tự đánh giá KPI Quý 3 của toàn thể nhân viên là trước ngày 08/10/2026 theo thông báo từ phòng Nhân sự.",
  "citations": [
    {
      "thread_id": "e4a2c5a1-7788-4e89-a212-3b0d7b3dcb11",
      "subject": "Nhắc nhở: Hạn nộp đánh giá KPI Quý 3",
      "evidence": "Toàn thể nhân viên lưu ý hoàn thành tự đánh giá KPI Quý 3 trước ngày 08/10/2026."
    }
  ],
  "relevant_threads_count": 1
}
```

---

## 9. HƯỚNG DẪN CÀI ĐẶT & TRIỂN KHAI (DEPLOYMENT GUIDE)

### Bước 1: Yêu Cầu Môi Trường

* Python 3.10 trở lên.
* Docker & Docker Compose.
* Google Cloud Console Project (nếu dùng Gmail API thật).

### Bước 2: Khởi Động Cơ Sở Dữ Liệu

Khởi động container PostgreSQL 16 tích hợp `pgvector` trên cổng `5434`:

```bash
docker compose up -d
```

*(Kiểm tra trạng thái container bằng lệnh `docker ps`).*

### Bước 3: Cài Đặt Môi Trường Ảo & Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Bước 4: Thiết Lập Biến Môi Trường (`.env`)

Sao chép `.env.example` thành `.env` và điền các thông số:

```ini
APP_NAME = Email Brief Agent
ENV = development
DEBUG = False

# Database (Host port 5434)
DATABASE_URL = postgresql+asyncpg://huepth:huepth123@localhost:5434/email_agent_db

# Email Provider: "fake" (mock test) hoặc "gmail" (hòm thư thật)
ACTIVE_EMAIL_PROVIDER = fake
GMAIL_CREDENTIALS_PATH = credentials.json
GMAIL_TOKEN_PATH = token.json

# AI & LLM Settings
LLM_PROVIDER = gemini
GEMINI_API_KEY = your_gemini_api_key_here
LLM_MODEL_NAME = gemini-3.8-flash

# Vector & Embedding
EMBEDDING_PROVIDER = gemini
EMBEDDING_MODEL_NAME = gemini-embedding-001
VECTOR_DIMENSION = 768
RAG_TOP_K = 5
RAG_SIMILARITY_THRESHOLD = 0.60
RAG_MIN_FALLBACK_THRESHOLD = 0.40

# Background Scheduler
SCHEDULER_ENABLED = True
SCHEDULER_INTERVAL_MINUTES = 15
SCHEDULER_BATCH_LIMIT = 15
SCHEDULER_CHUNK_SIZE = 5
```

### Bước 5: Kiểm Thử Hệ Thống (Sanity Tests)

```bash
# Kiểm tra kết nối CSDL, schema và domain models
python tests/run_test.py

# Kiểm tra luồng Ingestion
pytest tests/test_ingestion.py -v
```

### Bước 6: Khởi Chạy REST API Server

```bash
uvicorn src.emailagent.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Truy cập tài liệu API tương tác tại: [http://localhost:8000/docs](http://localhost:8000/docs).

### Bước 7: Khởi Chạy MCP Server (Kết Nối Trợ Lý AI)

Để kết nối công cụ hộp thư vào Claude Desktop hoặc Cursor:

```bash
python -m src.emailagent.mcp_server
```

Cấu hình trong `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "email-agent": {
      "command": "/path/to/email-agent/.venv/bin/python",
      "args": [
        "-m",
        "src.emailagent.mcp_server"
      ],
      "cwd": "/path/to/email-agent"
    }
  }
}
```

---
