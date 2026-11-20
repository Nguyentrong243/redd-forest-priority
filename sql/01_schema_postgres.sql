-- ============================================================================
-- 01_schema_postgres.sql
-- Thiết kế CSDL trung gian (Data Mart) trên PostgreSQL + PostGIS cho đồ án REDD+
-- Luồng dữ liệu: Python (ETL & ML) -> PostgreSQL/PostGIS -> ArcGIS Pro & Power BI
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS redd;
SET search_path TO redd, public;

-- (Tuỳ chọn) Bật extension PostGIS nếu dùng kết nối trực tiếp từ ArcGIS Pro / QGIS
-- CREATE EXTENSION IF NOT EXISTS postgis;

-- ----------------------------------------------------------------------------
-- 1. Bảng chiều (Dimension): Đơn vị quản lý cấp Tiểu khu (303 tiểu khu)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS redd.fact_forest_points CASCADE;
DROP TABLE IF EXISTS redd.dim_subzone CASCADE;

CREATE TABLE redd.dim_subzone (
    spatial_group       VARCHAR(32) PRIMARY KEY,   -- Khoá chính: Tinh_MaTieuKhu (VD: NgheAn_463)
    province            VARCHAR(32) NOT NULL,
    district            VARCHAR(32) NOT NULL,
    sub_region          VARCHAR(32) NOT NULL,
    latitude            DOUBLE PRECISION NOT NULL,
    longitude           DOUBLE PRECISION NOT NULL,
    n_points            INTEGER NOT NULL CHECK (n_points > 0),
    share_natural       NUMERIC(6,4) NOT NULL,
    share_high_actual   NUMERIC(6,4) NOT NULL,
    priority_index      NUMERIC(6,4) NOT NULL,     -- Xác suất High trung bình do ML dự báo
    accuracy            NUMERIC(6,4) NOT NULL,
    share_hotspot       NUMERIC(6,4) NOT NULL,     -- Tỷ lệ điểm thuộc vùng nóng Gi* >= 95%
    main_land_cover     VARCHAR(64) NOT NULL,
    reliable            BOOLEAN NOT NULL,          -- TRUE nếu tiểu khu có >= 10 điểm khảo sát
    rank_in_province    NUMERIC(6,1)
);

CREATE INDEX idx_dim_subzone_prov_dist ON redd.dim_subzone (province, district);
CREATE INDEX idx_dim_subzone_priority  ON redd.dim_subzone (province, priority_index DESC);

-- ----------------------------------------------------------------------------
-- 2. Bảng sự kiện trung tâm (Fact): 18.851 điểm khảo sát & dự báo ML + Gi*
-- ----------------------------------------------------------------------------
CREATE TABLE redd.fact_forest_points (
    id                      INTEGER PRIMARY KEY,
    latitude                DOUBLE PRECISION NOT NULL,
    longitude               DOUBLE PRECISION NOT NULL,
    province                VARCHAR(32) NOT NULL,
    district                VARCHAR(32) NOT NULL,
    commune                 VARCHAR(64) NOT NULL,
    sub_region              VARCHAR(32) NOT NULL,
    spatial_group           VARCHAR(32) NOT NULL REFERENCES redd.dim_subzone(spatial_group),
    owner_type              VARCHAR(32) NOT NULL,
    forest_origin           VARCHAR(32) NOT NULL,
    land_cover_group        VARCHAR(64) NOT NULL,
    stock_level             VARCHAR(32) NOT NULL,
    land_type               VARCHAR(160) NOT NULL,
    date                    DATE NOT NULL,
    year                    SMALLINT NOT NULL,
    status                  VARCHAR(24) NOT NULL,
    low_precision_coord     BOOLEAN NOT NULL,
    priority                VARCHAR(12) NOT NULL CHECK (priority IN ('High', 'Medium', 'Low')),
    predicted_priority      VARCHAR(12) NOT NULL CHECK (predicted_priority IN ('High', 'Medium', 'Low')),
    prob_high               NUMERIC(6,4) NOT NULL,
    prob_medium             NUMERIC(6,4) NOT NULL,
    prob_low                NUMERIC(6,4) NOT NULL,
    confidence              NUMERIC(6,4) NOT NULL,
    priority_rank_high      INTEGER NOT NULL,
    is_correct              SMALLINT NOT NULL CHECK (is_correct IN (0, 1)),
    error_type              VARCHAR(32) NOT NULL,
    resid_high              NUMERIC(7,4) NOT NULL,
    gi_z_actual             NUMERIC(8,4) NOT NULL,
    gi_bin_actual           SMALLINT NOT NULL CHECK (gi_bin_actual BETWEEN -3 AND 3),
    hotspot_actual          VARCHAR(24) NOT NULL,
    gi_z_pred               NUMERIC(8,4) NOT NULL,
    gi_bin_pred             SMALLINT NOT NULL CHECK (gi_bin_pred BETWEEN -3 AND 3),
    hotspot_pred            VARCHAR(24) NOT NULL
);

CREATE INDEX idx_fact_points_admin     ON redd.fact_forest_points (province, district, commune);
CREATE INDEX idx_fact_points_subzone   ON redd.fact_forest_points (spatial_group);
CREATE INDEX idx_fact_points_priority  ON redd.fact_forest_points (priority, predicted_priority);
CREATE INDEX idx_fact_points_prob_high ON redd.fact_forest_points (prob_high DESC);
CREATE INDEX idx_fact_points_hotspot   ON redd.fact_forest_points (gi_bin_actual, gi_bin_pred);

-- Nếu đã bật PostGIS: tạo cột hình học chuẩn WGS84 (EPSG:4326) và Spatial Index GIST cho ArcGIS Pro
-- ALTER TABLE redd.fact_forest_points
--     ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)
--     GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)) STORED;
-- CREATE INDEX IF NOT EXISTS idx_fact_points_geom ON redd.fact_forest_points USING GIST (geom);

-- ----------------------------------------------------------------------------
-- 3. Các bảng lưu kết quả đánh giá mô hình & kiểm định không gian (phục vụ BI)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS redd.model_comparison_cv CASCADE;
CREATE TABLE redd.model_comparison_cv (
    model_name          VARCHAR(64) NOT NULL,
    cv_scheme           VARCHAR(32) NOT NULL,
    accuracy            NUMERIC(6,4),
    balanced_acc        NUMERIC(6,4),
    precision_macro     NUMERIC(6,4),
    recall_macro        NUMERIC(6,4),
    f1_macro            NUMERIC(6,4),
    recall_high         NUMERIC(6,4),
    f1_high             NUMERIC(6,4),
    f1_high_natural     NUMERIC(6,4),
    PRIMARY KEY (model_name, cv_scheme)
);

-- ----------------------------------------------------------------------------
-- 4. Các VIEW nghiệp vụ (dùng trực tiếp trong Power BI và ArcGIS Pro)
-- ----------------------------------------------------------------------------

-- View 1: Danh sách các lô rừng được đề xuất ưu tiên kiểm tra thực địa trước
-- (Kèm phân tầng hành động dựa trên xác suất ML và điểm nóng không gian Gi*)
CREATE OR REPLACE VIEW redd.vw_patrol_priority_queue AS
SELECT
    p.priority_rank_high,
    p.id,
    p.province,
    p.district,
    p.commune,
    p.sub_region,
    p.spatial_group,
    p.latitude,
    p.longitude,
    p.forest_origin,
    p.land_cover_group,
    p.stock_level,
    p.owner_type,
    p.priority              AS actual_priority,
    p.predicted_priority,
    p.prob_high,
    p.hotspot_actual,
    p.hotspot_pred,
    CASE
        WHEN p.prob_high >= 0.55 AND p.gi_bin_pred >= 2 THEN '1. Khẩn cấp (Xác suất cao & nằm trong Vùng nóng)'
        WHEN p.prob_high >= 0.45                        THEN '2. Ưu tiên cao (Xác suất ML cao)'
        WHEN p.gi_bin_pred >= 2                         THEN '3. Giám sát vùng đệm (Lân cận cụm điểm nóng)'
        ELSE                                                 '4. Theo dõi định kỳ'
    END AS action_tier
FROM redd.fact_forest_points p;

-- View 2: Tổng hợp rủi ro & hiệu năng mô hình theo Cấp Xã (Commune)
CREATE OR REPLACE VIEW redd.vw_commune_priority_summary AS
SELECT
    province,
    district,
    commune,
    COUNT(*)                                                        AS n_points,
    COUNT(DISTINCT spatial_group)                                   AS n_subzones,
    ROUND(AVG(CASE WHEN forest_origin = 'Natural forest' THEN 1.0 ELSE 0.0 END), 4) AS share_natural,
    SUM(CASE WHEN priority = 'High' THEN 1 ELSE 0 END)              AS n_high_actual,
    ROUND(AVG(CASE WHEN priority = 'High' THEN 1.0 ELSE 0.0 END), 4) AS share_high_actual,
    ROUND(AVG(prob_high), 4)                                        AS avg_prob_high,
    ROUND(AVG(is_correct), 4)                                       AS model_accuracy,
    SUM(CASE WHEN gi_bin_actual >= 2 THEN 1 ELSE 0 END)             AS n_hotspot_points
FROM redd.fact_forest_points
GROUP BY province, district, commune;

