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
-- 3. TABEL FOREIGN FLOW HARIAN
-- ============================================================
CREATE TABLE IF NOT EXISTS foreign_flow (
    id                  BIGSERIAL       PRIMARY KEY,
    stock_code          VARCHAR(10)     NOT NULL REFERENCES stocks(stock_code),
    trade_date          DATE            NOT NULL,

    -- Data dalam lot
    foreign_buy_lot     BIGINT          NOT NULL DEFAULT 0,
    foreign_sell_lot    BIGINT          NOT NULL DEFAULT 0,
    foreign_net_lot     BIGINT          GENERATED ALWAYS AS (foreign_buy_lot - foreign_sell_lot) STORED,

    -- Data dalam rupiah
    foreign_buy_value   NUMERIC(20, 2)  NOT NULL DEFAULT 0,
    foreign_sell_value  NUMERIC(20, 2)  NOT NULL DEFAULT 0,
    foreign_net_value   NUMERIC(20, 2)  GENERATED ALWAYS AS (foreign_buy_value - foreign_sell_value) STORED,

    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ff_stock_date UNIQUE (stock_code, trade_date)
);

COMMENT ON TABLE foreign_flow IS 'Data transaksi asing (foreign buy/sell) harian per saham';
COMMENT ON COLUMN foreign_flow.foreign_net_lot IS 'Net = buy - sell, positif = net buy (akumulasi asing)';
COMMENT ON COLUMN foreign_flow.foreign_net_value IS 'Net value dalam rupiah, positif = net buy';

CREATE INDEX IF NOT EXISTS idx_ff_stock_date ON foreign_flow (stock_code, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_ff_date ON foreign_flow (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_ff_net_lot ON foreign_flow (trade_date DESC, foreign_net_lot DESC);


-- ============================================================
-- 4. TABEL HASIL SCREENING HARIAN
-- ============================================================
CREATE TABLE IF NOT EXISTS screening_results (
    id              BIGSERIAL       PRIMARY KEY,
    stock_code      VARCHAR(10)     NOT NULL REFERENCES stocks(stock_code),
    screen_date     DATE            NOT NULL,

    -- Data harga & volume
    close_price     NUMERIC(14, 2)  NOT NULL,
    volume_ratio    NUMERIC(8, 2),  -- volume hari ini vs rata-rata 20 hari

    -- Akumulasi foreign flow (rolling sum)
    ff_net_3d       BIGINT,         -- net lot 3 hari terakhir
    ff_net_5d       BIGINT,         -- net lot 5 hari terakhir
    ff_net_20d      BIGINT,         -- net lot 20 hari terakhir (1 bulan)

    -- Sinyal
    signal_type     VARCHAR(50),    -- misal: 'strong_buy', 'buy', 'neutral', 'sell', 'strong_sell'
    signal_score    SMALLINT,       -- skor 0-100
    phase           VARCHAR(30),    -- 'accumulation', 'markup', 'distribution', 'markdown'

    created_at      TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_screening_stock_date UNIQUE (stock_code, screen_date)
);

COMMENT ON TABLE screening_results IS 'Hasil screening EOD per saham per hari';
COMMENT ON COLUMN screening_results.volume_ratio IS 'Perbandingan volume hari ini vs MA20 volume. >1.5 = volume tinggi';
COMMENT ON COLUMN screening_results.ff_net_3d IS 'Kumulatif foreign net lot 3 hari (indikator jangka pendek)';
COMMENT ON COLUMN screening_results.ff_net_5d IS 'Kumulatif foreign net lot 5 hari (indikator mingguan)';
COMMENT ON COLUMN screening_results.ff_net_20d IS 'Kumulatif foreign net lot 20 hari (indikator bulanan)';
COMMENT ON COLUMN screening_results.signal_score IS 'Skor gabungan 0-100: teknikal + foreign flow';
COMMENT ON COLUMN screening_results.phase IS 'Fase siklus saham saat ini berdasarkan Wyckoff Method';

CREATE INDEX IF NOT EXISTS idx_screen_date ON screening_results (screen_date DESC);
CREATE INDEX IF NOT EXISTS idx_screen_stock_date ON screening_results (stock_code, screen_date DESC);
CREATE INDEX IF NOT EXISTS idx_screen_phase ON screening_results (screen_date DESC, phase);
CREATE INDEX IF NOT EXISTS idx_screen_score ON screening_results (screen_date DESC, signal_score DESC);


-- ============================================================
-- 5. TABEL HISTORI FASE (AKUMULASI → DISTRIBUSI)
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

    -- Akumulasi foreign flow selama fase
    ff_net_cumulative   BIGINT,         -- total net lot selama fase berlangsung

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
COMMENT ON COLUMN phase_history.ff_net_cumulative IS 'Total akumulasi/distribusi asing selama fase (lot)';

CREATE INDEX IF NOT EXISTS idx_phase_stock ON phase_history (stock_code, phase_start DESC);
CREATE INDEX IF NOT EXISTS idx_phase_active ON phase_history (phase_end) WHERE phase_end IS NULL;
CREATE INDEX IF NOT EXISTS idx_phase_type ON phase_history (phase, phase_start DESC);


-- ============================================================
-- 6. TABEL LOG ETL (AUDIT TRAIL)
-- ============================================================
CREATE TABLE IF NOT EXISTS etl_log (
    id              BIGSERIAL       PRIMARY KEY,
    run_date        DATE            NOT NULL,
    process_name    VARCHAR(100)    NOT NULL,  -- 'fetch_ohlcv', 'fetch_ff', 'screening', 'phase_detect'
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
-- 7. VIEW BERGUNA
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
    sr.ff_net_3d,
    sr.ff_net_5d,
    sr.ff_net_20d,
    sr.signal_type,
    sr.signal_score,
    sr.phase,
    ff.foreign_net_lot AS ff_net_today,
    ff.foreign_net_value AS ff_value_today
FROM screening_results sr
JOIN stocks s ON s.stock_code = sr.stock_code
LEFT JOIN foreign_flow ff
    ON ff.stock_code = sr.stock_code
    AND ff.trade_date = sr.screen_date
WHERE sr.screen_date = (SELECT MAX(screen_date) FROM screening_results)
ORDER BY sr.signal_score DESC;

COMMENT ON VIEW v_screening_latest IS 'Hasil screening terbaru dengan data foreign flow hari itu';


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
     ORDER BY trade_date DESC LIMIT 1) AS current_price,
    ph.ff_net_cumulative
FROM phase_history ph
JOIN stocks s ON s.stock_code = ph.stock_code
WHERE ph.phase_end IS NULL
ORDER BY ph.phase, days_in_phase DESC;

COMMENT ON VIEW v_active_phases IS 'Semua saham yang sedang dalam suatu fase (phase_end IS NULL)';


-- ============================================================
-- SELESAI
-- Jalankan script ini di PostgreSQL:
--   psql -U <user> -d <dbname> -f schema_v2.sql
-- ============================================================
