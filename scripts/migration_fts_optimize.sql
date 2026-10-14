-- Migration: Tối ưu hóa Full-Text Search (Stopwords + Field Weighting + Length Normalization)
-- Ngày cập nhật: 2026-10-13

-- 1. Tạo hàm IMMUTABLE loại bỏ các hư từ tiếng Việt phổ biến (chống phình to chỉ mục GIN)
CREATE OR REPLACE FUNCTION clean_fts_vietnamese(val text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
SELECT regexp_replace(
    immutable_unaccent(COALESCE(val, '')),
    '\m(va|cua|la|thi|ma|o|tai|cho|duoc|bi|boi|do|voi|cac|nhung|cai|chiec|nay|do|kia|ay|tu|den|trong|cung|theo|ve|de)\M',
    ' ',
    'gi'
);
$$;

-- 2. Tái cấu trúc lại cột tsv trên bảng emails:
-- - Subject: gán trọng số 'A' (Weight 1.0)
-- - Clean Body: gán trọng số 'B' (Weight 0.4)
-- - Tự động loại bỏ hư từ qua clean_fts_vietnamese
ALTER TABLE emails DROP COLUMN IF EXISTS tsv;

ALTER TABLE emails ADD COLUMN tsv TSVECTOR GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', clean_fts_vietnamese(COALESCE(subject, ''))), 'A') ||
    setweight(to_tsvector('simple', clean_fts_vietnamese(COALESCE(clean_body, ''))), 'B')
) STORED;

-- 3. Tạo lại chỉ mục GIN trên cột tsv
CREATE INDEX IF NOT EXISTS idx_emails_fts ON emails USING GIN(tsv);

-- Phân quyền cho user ứng dụng
GRANT ALL ON TABLE emails TO huepth;
