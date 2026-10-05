-- Kích hoạt các extension cần thiết
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Hàm wrapper immutable cho unaccent để dùng được trong Generated Column
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
$$
SELECT public.unaccent($1);
$$;

-- 1. Tài khoản kết nối Email
CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,                -- 'gmail' | 'fake' | 'outlook'
    email_address TEXT NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    cursor_state JSONB DEFAULT '{}'::jsonb, -- Lưu historyId (Gmail) hoặc mốc đồng bộ
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Chuỗi hội thoại (Thread là đơn vị tóm tắt)
CREATE TABLE IF NOT EXISTS threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    provider_thread_id TEXT NOT NULL,
    subject TEXT,
    last_message_at TIMESTAMPTZ,
    summary TEXT,                          -- Tóm tắt chuỗi hội thoại
    category TEXT,                         -- Danh mục (work, finance, task...)
    is_urgent BOOLEAN DEFAULT FALSE,
    needs_reply BOOLEAN DEFAULT FALSE,
    embedding VECTOR(768),                 -- Vector embedding của summary (Gemini/OpenAI)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(account_id, provider_thread_id)
);
CREATE INDEX IF NOT EXISTS idx_threads_hnsw ON threads USING hnsw (embedding vector_cosine_ops);

-- 3. Email chi tiết
CREATE TABLE IF NOT EXISTS emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    thread_id UUID REFERENCES threads(id) ON DELETE SET NULL,
    provider_message_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    recipients TEXT[] NOT NULL,
    date_sent TIMESTAMPTZ NOT NULL,
    subject TEXT,
    clean_body TEXT,                       -- Nội dung đã làm sạch, cắt reply
    status TEXT NOT NULL DEFAULT 'PENDING',-- PENDING | PROCESSED | FAILED
    tsv TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', immutable_unaccent(COALESCE(subject, '') || ' ' || COALESCE(clean_body, '')))
    ) STORED,
    UNIQUE(account_id, provider_message_id)
);
CREATE INDEX IF NOT EXISTS idx_emails_fts ON emails USING GIN(tsv);
CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(account_id, date_sent DESC);

-- 4. Việc cần làm (Action Items)
CREATE TABLE IF NOT EXISTS action_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    task TEXT NOT NULL,
    assignee TEXT,
    deadline DATE,
    priority TEXT DEFAULT 'medium',        -- 'high' | 'medium' | 'low'
    status TEXT DEFAULT 'open',            -- 'open' | 'done'
    evidence TEXT NOT NULL,                -- Câu trích dẫn bằng chứng từ email
    fingerprint TEXT NOT NULL,             -- Chống tạo trùng việc khi sync lại
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(thread_id, fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_action_items_deadline ON action_items(status, deadline);