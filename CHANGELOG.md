# Nhật ký Thay đổi

Tất cả các thay đổi đáng chú ý của dự án này sẽ được ghi nhận lại trong file này.

Định dạng dựa trên [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) và dự án này tuân thủ quy
chuẩn [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## Các loại Thay đổi

- **Added**: Dành cho các tính năng mới được thêm vào.
- **Changed**: Dành cho các thay đổi trong các chức năng hiện tại.
- **Deprecated**: Dành cho các tính năng sắp bị loại bỏ trong tương lai.
- **Removed**: Dành cho các tính năng đã bị loại bỏ hoàn toàn.
- **Fixed**: Dành cho bất kỳ bản vá lỗi nào.
- **Security**: Dành cho các trường hợp khắc phục lỗ hổng bảo mật.

---

## [Chưa phát hành]

### 2026-10-14

### Added

- **Làm giàu Ngữ cảnh Vector Embedding chống "Mù người gửi" (Enriched Vector Embedding)**:
    - **Prompt Builder (`src/emailagent/prompts/__init__.py`)**:
        - Bổ sung 2 tham số `sender: Optional[str] = None` và `body_snippet: Optional[str] = None` vào hàm
          `build_thread_embedding_text()`.
        - Chuỗi văn bản tạo vector nhúng được mở rộng toàn diện:
          ```text
          Người gửi: {sender}
          Tiêu đề: {subject}
          Phân loại: {category}
          Nội dung chính: {summary}
          Nhiệm vụ: {action_items}
          Nội dung thư: {body_snippet}
          ```
        - Khắc phục triệt để lỗ hổng "mù người gửi" khi người dùng tra cứu các thực thể như *"Thư của anh A"*, *"
          Email của kế toán"* và bảo toàn các mã định danh quan trọng (mã hóa đơn, mã đơn hàng, đường link) nằm trong
          thân thư nhưng không xuất hiện trong bản tóm tắt của LLM.
    - **Embedding Sync Service (`src/emailagent/services/embedding.py`)**:
        - Nâng cấp phương thức `sync_pending_embeddings()` trong `ThreadEmbeddingService`: truyền
          `sender=t.get("senders")` và `body_snippet=t.get("body_snippet")` vào `build_thread_embedding_text()`.
        - Bảo đảm quá trình băm vector đồng bộ đầy đủ ngữ cảnh đa chiều vào cột `embedding` (`vector(768)`).

- **Phân loại Ý định Người dùng (Intent Routing) & Cơ chế Tự vấn Metadata (Self-Querying)**:
    - **Domain Enums & Schemas (`src/emailagent/domain/enums.py`, `src/emailagent/domain/models.py`)**:
        - Định nghĩa `QueryIntent` Enum với 2 nhánh ý định độc lập: `SEARCH` (truy vấn ngữ nghĩa) và `ANALYTICS` (câu
          hỏi thống kê, đếm số lượng, tổng hợp dữ liệu).
        - Khởi tạo Pydantic model `QueryFormulationResult` làm cấu trúc dữ liệu đầu ra cho bước Self-Querying:
            - `intent: QueryIntent`: Nhãn phân loại ý định xử lý.
            - `standalone_query: str`: Câu truy vấn độc lập ngữ cảnh (Condensing query từ lịch sử hội thoại).
            - `expanded_keywords: List[str]`: Danh sách từ khóa đồng nghĩa / mở rộng nghiệp vụ cho FTS.
            - `date_after: Optional[datetime]`: Giới hạn mốc thời gian bắt đầu (chuẩn hóa ISO 8601).
            - `date_before: Optional[datetime]`: Giới hạn mốc thời gian kết thúc (chuẩn hóa ISO 8601).
            - `category: Optional[str]`: Bộ lọc phân loại email (`work`, `billing`, `personal`, v.v.).
            - `analytics_metric: Optional[str]`: Định danh chỉ số cần thống kê (`total_threads`, `total_actions`, v.v.).
    - **Query Reformulation Prompt (`src/emailagent/prompts/rewriter.py`)**:
        - Nâng cấp `build_query_formulation_prompt()`: Tích hợp 2 tác vụ trong 1 lệnh gọi LLM duy nhất (Condensing câu
          hỏi đa lượt + Self-Querying bóc tách metadata thời gian/từ đồng nghĩa).
        - Cung cấp cơ chế phân giải các mốc thời gian tương đối (*"hôm qua"*, *"tháng trước"*, *"quý 3"*, *"tuần này"*)
          thành mốc thời gian tuyệt đối ISO 8601 dựa trên tham số thời gian hiện tại (`current_time`).

- **Động cơ Tổng hợp Thống kê Cơ sở Dữ liệu Trực tiếp (`AnalysisRepository.get_analytics_summary`)**:
    - **Database Repository (`src/emailagent/adapters/db/repositories/analysis.py`)**:
        - Bổ sung hàm `get_analytics_summary(account_id, category, date_after, date_before, metric)`:
            - Thực thi native SQL truy vấn trực tiếp bảng `threads` và `action_items` với các hàm tổng hợp
              `COUNT(t.id) AS total_threads`, `COUNT(ai.id) AS total_actions`.
            - Hỗ trợ đa điều kiện ràng buộc: `account_id`, `category` (kèm `CAST(:category AS text)`), `date_after` và
              `date_before`.
            - Triệt tiêu hoàn toàn hiện tượng ảo giác số liệu (Top-K Hallucination) khi người dùng hỏi các câu hỏi thống
              kê.

### Changed

- **Điều phối Dòng Chảy Hỏi Đáp Hộp Thư (`src/emailagent/services/qa.py`)**:
    - **Mailbox QA Service (`MailboxQAService.ask_mailbox`)**:
        - Loại bỏ hoàn toàn cơ chế lọc chuỗi thô sơ bằng regex Python; chuyển sang cơ chế Intent-based Routing điều phối
          2 luồng riêng biệt:
            - Luồng `QueryIntent.ANALYTICS`: Trực tiếp gọi `get_analytics_summary()`, định dạng kết quả thống kê chính
              xác tuyệt đối mà không cần qua tìm kiếm RAG Top-K.
            - Luồng `QueryIntent.SEARCH`: Kích hoạt Hybrid Search với đầy đủ bộ tham số thời gian (`date_after`,
              `date_before`), phân loại (`category`) và từ khóa mở rộng (`expanded_keywords`).
        - Tích hợp chuẩn hóa `system_instruction` tĩnh và format bảng Markdown trực quan khi trả về danh sách nhiều đối
          tượng.

- **Nâng cấp Mở rộng và Ràng buộc Lọc Thời gian trong Tìm kiếm Tương đồng (
  `src/emailagent/adapters/db/repositories/search.py`)**:
    - **Search Repository (`SearchRepository.search_similar_threads`)**:
        - Mở rộng chữ ký hàm: Nhận thêm `expanded_keywords`, `date_before`, `category`.
        - Tự động gộp `expanded_keywords` vào câu truy vấn văn bản thô trước khi đưa qua bộ lọc Stopwords tiếng Việt.
        - Đồng bộ các điều kiện lọc `date_before` và `category` vào cả 2 truy vấn song song: Dense Vector Search
          (`pgvector`) và Sparse Full-Text Search (`ts_rank_cd`).

- **Quy chuẩn Định dạng Hiển thị và Giải quyết Mâu thuẫn Thời gian (`src/emailagent/prompts/qa.py`)**:
    - **Prompt Engineering (`src/emailagent/prompts/qa.py`)**:
        - Bổ sung luật **Recency Resolution**: Khi có xung đột thông tin giữa các email (ví dụ deadline bị dời, cuộc họp
          bị hủy), thông tin trong email có mốc thời gian gửi mới nhất (`date_sent`) được xác định là chân lý duy nhất.
        - Chuẩn hóa định dạng Markdown Table bắt buộc cho các phản hồi danh sách nhiều công việc / email để tối ưu trải
          nghiệm đọc trên giao diện người dùng.

### Fixed

- **Triệt tiêu Lỗi Ảo giác Đếm Số lượng của RAG (Top-K Aggregation Fallacy)**:
    - **QA Service & Analysis Repository (`services/qa.py`, `repositories/analysis.py`)**:
        - Khắc phục sự cố khi người dùng hỏi *"Có bao nhiêu hóa đơn?"* hoặc *"Tháng này có bao nhiêu công việc?"*, hệ
          thống trước đó chỉ lấy Top 8 kết quả tương đồng nhất và LLM đếm trên 8 kết quả đó (dẫn đến câu trả lời sai
          lệch "Bạn có 8 hóa đơn").
        - Định tuyến chuẩn sang luồng `ANALYTICS` chạy SQL `COUNT(*)` trực tiếp trên cơ sở dữ liệu, đảm bảo độ chính xác
          100%.

- **Khắc phục Lỗi Ép kiểu Tham số Tùy chọn trong asyncpg (`AmbiguousParameterError`)**:
    - **SQL Execution Queries (`search.py`, `analysis.py`)**:
        - Bổ sung ép kiểu tường minh `CAST(:category AS text)`, `CAST(:date_before AS timestamptz)`,
          `CAST(:date_after AS timestamptz)`, `CAST(:account_id AS uuid)` trong các câu lệnh `text(...)`.
        - Ngăn chặn lỗi `asyncpg.exceptions.AmbiguousParameterError: could not determine data type of parameter $X` khi
          giá trị tham số là `None`.

---

### 2026-10-13

### Added

- **Tối ưu hóa Toàn diện Bộ máy Full-Text Search Tiếng Việt (PostgreSQL FTS)**:
    - **Database Migration (`scripts/migration_fts_optimize.sql`)**:
        - Tạo hàm SQL độc lập `clean_fts_vietnamese(val text) RETURNS text IMMUTABLE PARALLEL SAFE`: Sử dụng biểu thức
          chính quy (POSIX regex) để loại bỏ các hư từ tiếng Việt thường gặp ngay trong tầng database engine.
        - Cập nhật định nghĩa cột tìm kiếm `tsv` dạng Generated Column với phân bổ trọng số (Field Weighting): Tiêu đề
          thư (`subject`) gán nhãn trọng số `'A'` (Weight 1.0), Nội dung sạch (`clean_body`) gán nhãn trọng số `'B'`
          (Weight 0.4).
        - Tái tạo chỉ mục GIN `idx_emails_fts` trên cột `tsv`.
    - **Database Schema (`scripts/schema.sql`)**:
        - Đồng bộ hóa hàm `clean_fts_vietnamese` và cấu trúc cột `tsv` trọng số vào schema gốc của hệ thống.
    - **Từ điển Từ dừng & Tiện ích Làm sạch (`resources/vietnamese_stopwords.txt`, `utils/stopwords.py`)**:
        - Tạo bộ từ điển Micro-Stopwords 67 từ chọn lọc kỹ càng (liên từ, đại từ nhân xưng, trợ từ phổ biến như: *và,
          của, là, thì, các, những, một, được, có, tại, do,...*), chủ động loại trừ các từ mang ngữ nghĩa phủ định
          (*không, chưa*) hoặc từ vựng nghiệp vụ email (*gửi, thư, mail, họp*).
        - Triển khai module `stopwords.py` tích hợp cơ chế nạp bộ từ điển vào bộ nhớ đệm (In-memory caching) và hàm
          `remove_vietnamese_stopwords(text)` làm sạch truy vấn người dùng trước khi gửi vào FTS parser.

- **Kiến trúc Tách biệt Module Repository (Repository Facade Pattern)**:
    - **Module Package (`src/emailagent/adapters/db/repositories/`)**:
        - Chia tách file nguyên khối `repositories.py` (447 dòng) thành package chuyên biệt tuân thủ nguyên tắc Single
          Responsibility:
            - `base.py`: Lớp cơ sở `BaseRepository` quản lý session AsyncSQLAlchemy.
            - `account.py`: `AccountRepository` xử lý thông tin tài khoản hộp thư và con trỏ đồng bộ `historyId`.
            - `email.py`: `EmailIngestRepository` phụ trách ingestion, bulk upsert email và mapping thread.
            - `analysis.py`: `AnalysisRepository` quản lý phân tích tóm tắt, action items và truy vấn nghiệp vụ.
            - `search.py`: `SearchRepository` quản lý Vector Search, FTS, thuật toán RRF và đồng bộ embedding.
            - `__init__.py`: Lớp Facade `EmailRepository` kế thừa hợp nhất toàn bộ 5 sub-repositories, duy trì tính
              tương thích ngược 100% với toàn bộ router và background jobs.

- **Kiến trúc Prompt Module hóa & Quản trị Rủi ro Ngữ cảnh**:
    - **Modular Prompts Package (`src/emailagent/prompts/`)**:
        - Thay thế file nguyên khối `utils/prompt.py` bằng gói module:
            - `qa.py`: System instruction tĩnh cho Q&A, template format ngữ cảnh thread và luật trích dẫn nguồn.
            - `analysis.py`: Prompt chuyên dụng bóc tách tóm tắt, phân loại và trích xuất Action Items (kèm trạng thái,
              deadline, người phụ trách).
            - `rewriter.py`: Prompt chuyển đổi hội thoại đa lượt và trích xuất tham số truy vấn.
            - `__init__.py`: Khởi tạo và hàm `build_thread_embedding_text`.
    - **Hỗ trợ Hội thoại Đa lượt (Multi-Turn Chat Context) (`src/emailagent/domain/models.py`)**:
        - Bổ sung schema Pydantic `ChatMessage` với các trường `role: str` (`user` / `assistant`) và `content: str`, cho
          phép duy trì ngữ cảnh trao đổi liên tục trong các phiên chat dài.

### Changed

- **Chuẩn hóa Cấu trúc Quản lý Phiên Cơ sở Dữ liệu (`src/emailagent/adapters/db/session.py`)**:
    - Di chuyển `src/emailagent/db/session.py` sang `src/emailagent/adapters/db/session.py` nhằm chuẩn hóa theo cấu trúc
      Clean Architecture / Ports and Adapters.
    - Cập nhật đường dẫn import trên toàn bộ routers (`analysis.py`, `chat.py`, `sync.py`), `mcp_server.py`, scheduler
      orchestrator và test suites.

- **Nâng cấp Thuật toán Xếp hạng Văn bản Mô phỏng BM25 trong FTS (
  `src/emailagent/adapters/db/repositories/search.py`)**:
    - **Search Repository (`SearchRepository.search_similar_threads`)**:
        - Tinh chỉnh hàm `ts_rank_cd` trong PostgreSQL: cấu hình trọng số trường `{0.1, 0.2, 0.4, 1.0}` kết hợp cờ chuẩn
          hóa độ dài văn bản `32` (chia cho `rank / (1 + log(length))`), ngăn chặn tình trạng email dài chiếm ưu thế
          điểm số bất hợp lý so với email ngắn nhưng chứa từ khóa trọng tâm ở tiêu đề.

- **Mở rộng Không gian Ứng viên & Lọc Đa dạng hóa Kết quả Tìm kiếm (
  `src/emailagent/adapters/db/repositories/search.py`)**:
    - **Search Repository (`SearchRepository.search_similar_threads`)**:
        - Nâng số lượng ứng viên truy vấn từ mỗi nguồn (Vector và FTS) lên mức $Top\ 8 \times 3 = 24$ ứng viên trước khi
          thực hiện thuật toán Reciprocal Rank Fusion (RRF).
        - Tích hợp cơ chế Diversity Filtering: Loại bỏ các email trùng lặp nội dung hoặc có độ tương đồng quá cao trong
          cùng một chuỗi hội thoại, đảm bảo độ bao phủ thông tin đa chiều.

### Removed

- **Loại bỏ Mã Nguồn Nguyên Khối (Monolithic Codebase)**:
    - Xóa bỏ file `src/emailagent/adapters/db/repositories.py` (447 dòng code) sau khi đã phân tách hoàn chỉnh sang
      package `adapters/db/repositories/`.
    - Xóa bỏ file `src/emailagent/utils/prompt.py` (142 dòng code) sau khi đã module hóa sang package
      `src/emailagent/prompts/` và `utils/security.py`.

- **Gỡ bỏ Biểu thức Chính quy Chặn nhầm Email Tự động (Prefilter Overzealous Regex)**:
    - **Prefilter Utility (`src/emailagent/utils/prefilter.py`)**:
        - Gỡ bỏ rule regex cứng `re.compile(r"^noreply@", re.IGNORECASE)` trong `SystemNotificationRule`.
        - Khắc phục sự cố email công việc thực tế gửi từ địa chỉ noreply (điển hình như email mời tham gia dự án từ đối
          tác `vingovan`) bị hệ thống nuốt chửng và gán nhầm bản tóm tắt thông báo tự động giả mạo.

- **Loại bỏ Bộ Lọc Thời Gian Bằng Chuỗi Cứng**:
    - **QA Service (`src/emailagent/services/qa.py`)**:
        - Xóa bỏ các nhánh `if "gần đây" in q_lower:` xử lý thời gian thô sơ bằng Python, chuyển giao toàn bộ cho LLM
          Self-Querying trích xuất mốc thời gian ISO 8601.

### Security

- **Phòng chống Tấn công Prompt Injection từ Nội dung Email (`src/emailagent/utils/security.py`)**:
    - Triển khai các hàm thoát ký tự đặc biệt XML `escape_text()` và `escape_attr()` nhằm vô hiệu hóa các cuộc tấn công
      Prompt Injection tiềm ẩn từ nội dung email không tin cậy.
    - Tách biệt nội dung email bên ngoài trong các thẻ bọc XML an toàn `<emails>` với thuộc tính đã được escape trước
      khi đưa vào ngữ cảnh LLM.

- **Kiểm tra Tính Trung thực của Trích dẫn Nguồn Bằng Mã Code (Deterministic Citation Validation) (
  `src/emailagent/utils/security.py`)**:
    - Triển khai cơ chế xác thực trích dẫn nguồn bằng mã nguồn Python `verify_and_filter_citations()`: kiểm tra tính tồn
      tại thực tế của `thread_id` trong danh sách thread đã được kéo về từ cơ sở dữ liệu, loại bỏ triệt để trích dẫn bịa
      đặt (Hallucinated Citations).
