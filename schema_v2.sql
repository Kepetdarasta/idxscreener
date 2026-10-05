-- ============================================================
-- Stock Screening V2 - Database Schema
-- PostgreSQL
-- ============================================================

-- Extension untuk UUID (opsional, jika ingin pakai UUID sebagai PK)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. TABEL MASTER SAHAM
-- ============================================================
CREATE TABLE IF NOT EXISTS stocks (
    stock_code      VARCHAR(10)     PRIMARY KEY,
    stock_name      VARCHAR(255)    NOT NULL,
    sector          VARCHAR(100),
    subsector       VARCHAR(100),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP       NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE stocks IS 'Master data semua saham yang ditracking';
COMMENT ON COLUMN stocks.stock_code IS 'Kode saham IDX, misal: BBCA, TLKM, GOTO';
COMMENT ON COLUMN stocks.is_active IS 'FALSE jika saham sudah delisted atau tidak ditracking';


-- ============================================================
-- 2. TABEL OHLCV HARIAN
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    id              BIGSERIAL       PRIMARY KEY,
    stock_code      VARCHAR(10)     NOT NULL REFERENCES stocks(stock_code),
    trade_date      DATE            NOT NULL,
    open_price      NUMERIC(14, 2)  NOT NULL,
    high_price      NUMERIC(14, 2)  NOT NULL,
    low_price       NUMERIC(14, 2)  NOT NULL,
    close_price     NUMERIC(14, 2)  NOT NULL,
    volume          BIGINT          NOT NULL DEFAULT 0,  -- dalam lot
    value           BIGINT          NOT NULL DEFAULT 0,  -- dalam rupiah
    frequency       INTEGER         NOT NULL DEFAULT 0,  -- jumlah transaksi
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ohlcv_stock_date UNIQUE (stock_code, trade_date)
);

COMMENT ON TABLE daily_ohlcv IS 'Data OHLCV harian per saham (end of day)';
COMMENT ON COLUMN daily_ohlcv.volume IS 'Volume dalam satuan lot (1 lot = 100 lembar)';
COMMENT ON COLUMN daily_ohlcv.value IS 'Nilai transaksi dalam rupiah';
COMMENT ON COLUMN daily_ohlcv.frequency IS 'Jumlah transaksi/frekuensi dalam sehari';

CREATE INDEX IF NOT EXISTS idx_ohlcv_stock_date ON daily_ohlcv (stock_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_ohlcv_date ON daily_ohlcv (trade_date DESC);


-- ============================================================
-- 3. TABEL HASIL SCREENING HARIAN
-- ============================================================
CREATE TABLE IF NOT EXISTS screening_results (
    id              BIGSERIAL       PRIMARY KEY,
    stock_code      VARCHAR(10)     NOT NULL REFERENCES stocks(stock_code),
    screen_date     DATE            NOT NULL,

    -- Data harga & volume
    close_price     NUMERIC(14, 2)  NOT NULL,
    volume_ratio    NUMERIC(8, 2),  -- volume hari ini vs rata-rata 20 hari

    -- Sinyal
    signal_type     VARCHAR(50),    -- misal: 'strong_buy', 'buy', 'neutral', 'sell', 'strong_sell'
    signal_score    SMALLINT,       -- skor 0-100
    phase           VARCHAR(30),    -- 'accumulation', 'markup', 'distribution', 'markdown'

    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_screening_stock_date UNIQUE (stock_code, screen_date)
);

COMMENT ON TABLE screening_results IS 'Hasil screening EOD per saham per hari';
COMMENT ON COLUMN screening_results.volume_ratio IS 'Perbandingan volume hari ini vs MA20 volume. >1.5 = volume tinggi';
COMMENT ON COLUMN screening_results.signal_score IS 'Skor sinyal 0-100 (dari harga & volume)';
COMMENT ON COLUMN screening_results.phase IS 'Fase siklus saham saat ini berdasarkan Wyckoff Method';

CREATE INDEX IF NOT EXISTS idx_screen_date ON screening_results (screen_date DESC);
CREATE INDEX IF NOT EXISTS idx_screen_stock_date ON screening_results (stock_code, screen_date DESC);
CREATE INDEX IF NOT EXISTS idx_screen_phase ON screening_results (screen_date DESC, phase);
CREATE INDEX IF NOT EXISTS idx_screen_score ON screening_results (screen_date DESC, signal_score DESC);


-- ============================================================
-- 4. TABEL HISTORI FASE (AKUMULASI → DISTRIBUSI)
-- ============================================================
CREATE TABLE IF NOT EXISTS phase_history (
    id                  BIGSERIAL       PRIMARY KEY,
    stock_code          VARCHAR(10)     NOT NULL REFERENCES stocks(stock_code),

    -- Fase dan durasi
    phase               VARCHAR(30)     NOT NULL,  -- 'accumulation', 'markup', 'distribution', 'markdown'
    phase_start         DATE            NOT NULL,
    phase_end           DATE,                      -- NULL jika fase masih berjalan
    duration_days       INTEGER
        GENERATED ALWAYS AS (
            CASE WHEN phase_end IS NOT NULL
                 THEN (phase_end - phase_start)
                 ELSE NULL
            END
        ) STORED,

    -- Harga saat masuk dan keluar fase
    price_at_start      NUMERIC(14, 2)  NOT NULL,
    price_at_end        NUMERIC(14, 2),
    price_change_pct    NUMERIC(8, 2)
        GENERATED ALWAYS AS (
            CASE WHEN price_at_end IS NOT NULL AND price_at_start > 0
                 THEN ROUND(((price_at_end - price_at_start) / price_at_start) * 100, 2)
                 ELSE NULL
            END
        ) STORED,

    -- Metadata
    detected_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_phase_valid CHECK (
        phase IN ('accumulation', 'markup', 'distribution', 'markdown', 'unknown')
    ),
    CONSTRAINT chk_phase_dates CHECK (
        phase_end IS NULL OR phase_end >= phase_start
    )
);

COMMENT ON TABLE phase_history IS 'Rekam jejak transisi fase siklus saham (Wyckoff)';
COMMENT ON COLUMN phase_history.phase IS 'accumulation=akumulasi, markup=kenaikan, distribution=distribusi, markdown=penurunan';
COMMENT ON COLUMN phase_history.phase_end IS 'NULL berarti saham masih berada di fase ini';
COMMENT ON COLUMN phase_history.duration_days IS 'Durasi fase dalam hari (otomatis dihitung)';
COMMENT ON COLUMN phase_history.price_change_pct IS 'Perubahan harga selama fase (%) (otomatis dihitung)';

CREATE INDEX IF NOT EXISTS idx_phase_stock ON phase_history (stock_code, phase_start DESC);
CREATE INDEX IF NOT EXISTS idx_phase_active ON phase_history (phase_end) WHERE phase_end IS NULL;
CREATE INDEX IF NOT EXISTS idx_phase_type ON phase_history (phase, phase_start DESC);


-- ============================================================
-- 5. TABEL LOG ETL (AUDIT TRAIL)
-- ============================================================
CREATE TABLE IF NOT EXISTS etl_log (
    id              BIGSERIAL       PRIMARY KEY,
    run_date        DATE            NOT NULL,
    process_name    VARCHAR(100)    NOT NULL,  -- 'fetch_ohlcv', 'screening', 'phase_detect', 'full_pipeline'
    status          VARCHAR(20)     NOT NULL,  -- 'success', 'failed', 'partial'
    stocks_total    INTEGER         DEFAULT 0,
    stocks_success  INTEGER         DEFAULT 0,
    stocks_failed   INTEGER         DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMP,
    duration_sec    INTEGER
        GENERATED ALWAYS AS (
            CASE WHEN finished_at IS NOT NULL
                 THEN EXTRACT(EPOCH FROM (finished_at - started_at))::INTEGER
                 ELSE NULL
            END
        ) STORED
);

COMMENT ON TABLE etl_log IS 'Log setiap proses ETL untuk monitoring dan debugging';
CREATE INDEX IF NOT EXISTS idx_etl_log_date ON etl_log (run_date DESC);


-- ============================================================
-- 6. VIEW BERGUNA
-- ============================================================

-- View: screening hari ini + data terbaru
CREATE OR REPLACE VIEW v_screening_latest AS
SELECT
    sr.screen_date,
    sr.stock_code,
    s.stock_name,
    s.sector,
    sr.close_price,
    sr.volume_ratio,
    sr.signal_type,
    sr.signal_score,
    sr.phase
FROM screening_results sr
JOIN stocks s ON s.stock_code = sr.stock_code
WHERE sr.screen_date = (SELECT MAX(screen_date) FROM screening_results)
ORDER BY sr.signal_score DESC;

COMMENT ON VIEW v_screening_latest IS 'Hasil screening terbaru';


-- View: saham yang sedang dalam fase aktif
CREATE OR REPLACE VIEW v_active_phases AS
SELECT
    ph.stock_code,
    s.stock_name,
    s.sector,
    ph.phase,
    ph.phase_start,
    NOW()::DATE - ph.phase_start AS days_in_phase,
    ph.price_at_start,
    (SELECT close_price FROM daily_ohlcv
     WHERE stock_code = ph.stock_code
     ORDER BY trade_date DESC LIMIT 1) AS current_price
FROM phase_history ph
JOIN stocks s ON s.stock_code = ph.stock_code
WHERE ph.phase_end IS NULL
ORDER BY ph.phase, days_in_phase DESC;

COMMENT ON VIEW v_active_phases IS 'Semua saham yang sedang dalam suatu fase (phase_end IS NULL)';


-- ============================================================
-- 7. TABEL SINYAL SWING (MA cross, MACD cross, Swing Setup)
-- Jalur swing terpisah dari Wyckoff; ditulis oleh etl_swing.py
-- ============================================================
CREATE TABLE IF NOT EXISTS swing_signals (
    id              BIGSERIAL       PRIMARY KEY,
    stock_code      VARCHAR(10)     NOT NULL REFERENCES stocks(stock_code),
    signal_date     DATE            NOT NULL,
    signal_type     VARCHAR(30)     NOT NULL,   -- MA_Golden_Cross, MACD_Bullish_Cross, Swing_Confirmed_Bullish, dst.
    direction       VARCHAR(10)     NOT NULL,
    close_price     NUMERIC(14, 2)  NOT NULL,
    strength        NUMERIC(4, 1),              -- skala 0-10
    note            TEXT,
    stop_price      NUMERIC(14, 2),             -- close - 2xATR14 (bullish Swing Setup)
    target_price    NUMERIC(14, 2),             -- target 2R
    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_swing_stock_date_type UNIQUE (stock_code, signal_date, signal_type),
    CONSTRAINT chk_swing_direction CHECK (direction IN ('bullish', 'bearish'))
);

CREATE INDEX IF NOT EXISTS idx_swing_date  ON swing_signals (signal_date);
CREATE INDEX IF NOT EXISTS idx_swing_stock ON swing_signals (stock_code, signal_date);


-- ============================================================
-- SELESAI
-- Jalankan script ini di PostgreSQL:
--   psql -U <user> -d <dbname> -f schema_v2.sql
-- ============================================================
