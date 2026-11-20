"""Tiện ích kết nối và nạp dữ liệu vào CSDL trung gian (PostgreSQL / SQLite).

- Khi có biến môi trường `POSTGRES_URI` (ví dụ:
  `postgresql+psycopg2://postgres:<YOUR_PASSWORD>@localhost:5432/redd_forest_db`),
  dữ liệu sẽ được đẩy thẳng vào schema `redd` trên PostgreSQL để Power BI và các công cụ GIS
  kết nối trực tiếp.
- Đồng thời luôn tạo sẵn một bản CSDL cục bộ `outputs/sql/redd_warehouse.db` (SQLite 3.40+,
  hỗ trợ đầy đủ CTE, Window Functions, VIEW) để các câu truy vấn SQL trong notebook 05
  chạy và xuất bảng kết quả ngay cả trên máy chưa bật dịch vụ PostgreSQL.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
import pandas as pd


VIEWS_SQL = """
DROP VIEW IF EXISTS vw_patrol_priority_queue;
CREATE VIEW vw_patrol_priority_queue AS
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
FROM fact_forest_points p;

DROP VIEW IF EXISTS vw_commune_priority_summary;
CREATE VIEW vw_commune_priority_summary AS
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
FROM fact_forest_points
GROUP BY province, district, commune;
"""


def build_warehouse(root: Path, postgres_uri: str | None = None) -> dict:
    """Nạp các bảng chuẩn Star Schema vào SQLite cục bộ và (nếu có) PostgreSQL."""
    root = Path(root)
    pbi_dir = root / "outputs" / "powerbi"
    sql_dir = root / "outputs" / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)

    fact_points = pd.read_csv(pbi_dir / "fact_points.csv")
    dim_subzone = pd.read_csv(pbi_dir / "dim_subzone.csv")
    model_cv = pd.read_csv(pbi_dir / "model_comparison_cv.csv")
    ablation = pd.read_csv(pbi_dir / "feature_ablation.csv")
    morans = pd.read_csv(pbi_dir / "spatial_morans_i.csv")

    sqlite_path = sql_dir / "redd_warehouse.db"
    with sqlite3.connect(sqlite_path) as conn:
        dim_subzone.to_sql("dim_subzone", conn, if_exists="replace", index=False)
        fact_points.to_sql("fact_forest_points", conn, if_exists="replace", index=False)
        model_cv.to_sql("model_comparison_cv", conn, if_exists="replace", index=False)
        ablation.to_sql("feature_ablation", conn, if_exists="replace", index=False)
        morans.to_sql("spatial_morans_i", conn, if_exists="replace", index=False)
        conn.executescript(VIEWS_SQL)
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_fp_admin   ON fact_forest_points(province, district, commune);
            CREATE INDEX IF NOT EXISTS idx_fp_subzone ON fact_forest_points(spatial_group);
            CREATE INDEX IF NOT EXISTS idx_fp_prio    ON fact_forest_points(priority, predicted_priority);
            CREATE INDEX IF NOT EXISTS idx_fp_prob    ON fact_forest_points(prob_high DESC);
        """)

    pg_status = "Chưa cấu hình POSTGRES_URI (đang dùng bản mirror SQLite tương thích ANSI SQL)"
    uri = postgres_uri or os.environ.get("POSTGRES_URI")
    if uri:
        from sqlalchemy import Boolean, Date, Double, Integer, Numeric, String, create_engine, text

        engine = create_engine(uri)
        dim_dtypes = {
            "spatial_group": String(32),
            "province": String(32),
            "district": String(32),
            "sub_region": String(32),
            "latitude": Double(),
            "longitude": Double(),
            "n_points": Integer(),
            "share_natural": Numeric(8, 4),
            "share_high_actual": Numeric(8, 4),
            "priority_index": Numeric(8, 4),
            "accuracy": Numeric(8, 4),
            "share_hotspot": Numeric(8, 4),
            "main_land_cover": String(64),
            "reliable": Boolean(),
            "rank_in_province": Numeric(6, 1),
        }
        fact_dtypes = {
            "id": Integer(),
            "latitude": Double(),
            "longitude": Double(),
            "province": String(32),
            "district": String(32),
            "commune": String(64),
            "sub_region": String(32),
            "spatial_group": String(32),
            "owner_type": String(32),
            "forest_origin": String(32),
            "land_cover_group": String(64),
            "stock_level": String(32),
            "land_type": String(160),
            "date": Date(),
            "year": Integer(),
            "status": String(24),
            "low_precision_coord": Boolean(),
            "priority": String(12),
            "predicted_priority": String(12),
            "prob_high": Numeric(8, 4),
            "prob_medium": Numeric(8, 4),
            "prob_low": Numeric(8, 4),
            "confidence": Numeric(8, 4),
            "priority_rank_high": Integer(),
            "is_correct": Integer(),
            "error_type": String(32),
            "resid_high": Numeric(8, 4),
            "gi_z_actual": Numeric(8, 4),
            "gi_bin_actual": Integer(),
            "hotspot_actual": String(24),
            "gi_z_pred": Numeric(8, 4),
            "gi_bin_pred": Integer(),
            "hotspot_pred": String(24),
        }

        fact_pg = fact_points.copy()
        fact_pg["date"] = pd.to_datetime(fact_pg["date"]).dt.date

        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS redd;"))
            conn.execute(text("DROP VIEW IF EXISTS redd.vw_patrol_priority_queue CASCADE;"))
            conn.execute(text("DROP VIEW IF EXISTS redd.vw_commune_priority_summary CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS redd.fact_forest_points CASCADE;"))
            conn.execute(text("DROP TABLE IF EXISTS redd.dim_subzone CASCADE;"))

            dim_subzone.to_sql("dim_subzone", conn, schema="redd", if_exists="replace", index=False, dtype=dim_dtypes)
            fact_pg.to_sql("fact_forest_points", conn, schema="redd", if_exists="replace", index=False, dtype=fact_dtypes)
            model_cv.to_sql("model_comparison_cv", conn, schema="redd", if_exists="replace", index=False)
            ablation.to_sql("feature_ablation", conn, schema="redd", if_exists="replace", index=False)
            morans.to_sql("spatial_morans_i", conn, schema="redd", if_exists="replace", index=False)

            # Khoá chính, khoá ngoại Star Schema & chỉ mục (hiển thị đẹp trên ERD Tool của pgAdmin 4)
            conn.execute(text("ALTER TABLE redd.dim_subzone ADD PRIMARY KEY (spatial_group);"))
            conn.execute(text("ALTER TABLE redd.fact_forest_points ADD PRIMARY KEY (id);"))
            conn.execute(text(
                "ALTER TABLE redd.fact_forest_points "
                "ADD CONSTRAINT fk_fact_subzone FOREIGN KEY (spatial_group) "
                "REFERENCES redd.dim_subzone (spatial_group);"
            ))
            conn.execute(text("CREATE INDEX idx_fp_admin   ON redd.fact_forest_points (province, district, commune);"))
            conn.execute(text("CREATE INDEX idx_fp_subzone ON redd.fact_forest_points (spatial_group);"))
            conn.execute(text("CREATE INDEX idx_fp_prio    ON redd.fact_forest_points (priority, predicted_priority);"))
            conn.execute(text("CREATE INDEX idx_fp_prob    ON redd.fact_forest_points (prob_high DESC);"))

            # Tạo 2 VIEW nghiệp vụ trực tiếp trong schema `redd`
            conn.execute(text("SET search_path TO redd, public;"))
            for stmt in [s.strip() for s in VIEWS_SQL.split(";") if s.strip()]:
                conn.execute(text(stmt))

        pg_status = "Đã đồng bộ thành công lên PostgreSQL (schema `redd`: 5 bảng, khoá chính/ngoại & 2 VIEW)"

    return {
        "sqlite_path": sqlite_path,
        "postgres_status": pg_status,
        "tables": {
            "dim_subzone": len(dim_subzone),
            "fact_forest_points": len(fact_points),
            "model_comparison_cv": len(model_cv),
            "feature_ablation": len(ablation),
            "spatial_morans_i": len(morans),
        },
    }

