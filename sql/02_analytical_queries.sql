-- ============================================================================
-- 02_analytical_queries.sql
-- Bộ 8 truy vấn SQL phân tích nghiệp vụ trả lời các bài toán của bộ dữ liệu REDD+
-- Tương thích chuẩn ANSI SQL / PostgreSQL 13+ (và SQLite 3.40+)
-- ============================================================================

-- Khi chạy trên PostgreSQL (pgAdmin 4), giữ dòng này để trỏ thẳng vào schema `redd`:
SET search_path TO redd, public;

-- ============================================================================
-- BÀI TOÁN 1: Toàn cảnh cơ cấu rừng và mức độ ưu tiên theo Tỉnh & Huyện
-- Câu hỏi: Sự phân bố rừng tự nhiên vs rừng trồng và tỷ lệ ưu tiên High/Medium/Low
--          khác biệt như thế nào giữa 4 huyện của Nghệ An và Lâm Đồng?
-- ============================================================================
SELECT
    province                                                                        AS tinh,
    district                                                                        AS huyen,
    COUNT(*)                                                                        AS tong_so_lo,
    COUNT(DISTINCT spatial_group)                                                   AS so_tieu_khu,
    SUM(CASE WHEN forest_origin = 'Natural forest' THEN 1 ELSE 0 END)               AS so_lo_rung_tu_nhien,
    ROUND(100.0 * AVG(CASE WHEN forest_origin = 'Natural forest' THEN 1.0 ELSE 0.0 END), 1) AS pct_rung_tu_nhien,
    ROUND(100.0 * AVG(CASE WHEN priority = 'High'   THEN 1.0 ELSE 0.0 END), 1)      AS pct_high,
    ROUND(100.0 * AVG(CASE WHEN priority = 'Medium' THEN 1.0 ELSE 0.0 END), 1)      AS pct_medium,
    ROUND(100.0 * AVG(CASE WHEN priority = 'Low'    THEN 1.0 ELSE 0.0 END), 1)      AS pct_low,
    ROUND(100.0 * AVG(prob_high), 1)                                                AS pct_prob_high_tb
FROM fact_forest_points
GROUP BY province, district
ORDER BY province, pct_high DESC;


-- ============================================================================
-- BÀI TOÁN 2: Kiểm chứng giả thuyết "Nguồn gốc rừng & Cấp trữ lượng quyết định Priority"
-- Câu hỏi: Vì sao rừng trồng gần như luôn là Low, còn trong rừng tự nhiên thì nhóm
--          hiện trạng và cấp trữ lượng nào có tỷ lệ ưu tiên cao (High) lớn nhất?
-- ============================================================================
SELECT
    forest_origin                                                                   AS nguon_goc_rung,
    land_cover_group                                                                AS nhom_hien_trang,
    stock_level                                                                     AS cap_tru_luong,
    COUNT(*)                                                                        AS so_lo,
    SUM(CASE WHEN priority = 'High' THEN 1 ELSE 0 END)                              AS so_lo_high,
    ROUND(100.0 * AVG(CASE WHEN priority = 'High'   THEN 1.0 ELSE 0.0 END), 1)      AS pct_high,
    ROUND(100.0 * AVG(CASE WHEN priority = 'Medium' THEN 1.0 ELSE 0.0 END), 1)      AS pct_medium,
    ROUND(100.0 * AVG(CASE WHEN priority = 'Low'    THEN 1.0 ELSE 0.0 END), 1)      AS pct_low
FROM fact_forest_points
GROUP BY forest_origin, land_cover_group, stock_level
HAVING COUNT(*) >= 30
ORDER BY forest_origin, pct_high DESC, so_lo DESC;


-- ============================================================================
-- BÀI TOÁN 3: Trách nhiệm quản lý theo Loại chủ rừng (Owner Type)
-- Câu hỏi: Trong các diện tích rừng tự nhiên, nhóm chủ rừng nào (Ban quản lý,
--          UBND xã, Hộ gia đình hay Đất chưa giao/Unknown) đang nắm giữ nhiều
--          lô ưu tiên cao (High) và nhiều điểm nóng (Hot spot) nhất?
-- ============================================================================
SELECT
    owner_type                                                                      AS loai_chu_rung,
    COUNT(*)                                                                        AS so_lo_rung_tu_nhien,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)                              AS ty_trong_trong_rung_tn_pct,
    SUM(CASE WHEN priority = 'High' THEN 1 ELSE 0 END)                              AS so_lo_high,
    ROUND(100.0 * AVG(CASE WHEN priority = 'High' THEN 1.0 ELSE 0.0 END), 1)        AS ty_le_high_pct,
    SUM(CASE WHEN gi_bin_actual >= 2 THEN 1 ELSE 0 END)                             AS so_diem_nong_95pct,
    ROUND(100.0 * AVG(CASE WHEN status = 'Verified' THEN 1.0 ELSE 0.0 END), 2)      AS ty_le_da_xac_minh_pct
FROM fact_forest_points
WHERE forest_origin = 'Natural forest'
GROUP BY owner_type
ORDER BY so_lo_high DESC;


-- ============================================================================
-- BÀI TOÁN 4: Phát hiện "Khoảng trống xác minh thực địa" (Verification Gap)
-- Câu hỏi: Có bao nhiêu lô rừng được xếp mức High (hoặc nằm trong vùng nóng 99%)
--          nhưng vẫn ở trạng thái 'Not Verified'? Xã nào đang tồn đọng nhiều nhất?
-- ============================================================================
SELECT
    province                                                                        AS tinh,
    district                                                                        AS huyen,
    commune                                                                         AS xa,
    COUNT(*)                                                                        AS tong_so_lo_high,
    SUM(CASE WHEN status = 'Not Verified' THEN 1 ELSE 0 END)                        AS high_chua_xac_minh,
    SUM(CASE WHEN status = 'Not Verified' AND gi_bin_actual = 3 THEN 1 ELSE 0 END)  AS high_vung_nong_99_chua_xm,
    ROUND(100.0 * AVG(CASE WHEN status = 'Not Verified' THEN 1.0 ELSE 0.0 END), 1)  AS pct_chua_xac_minh
FROM fact_forest_points
WHERE priority = 'High'
GROUP BY province, district, commune
HAVING COUNT(*) >= 20
ORDER BY high_vung_nong_99_chua_xm DESC, high_chua_xac_minh DESC
LIMIT 12;


-- ============================================================================
-- BÀI TOÁN 5: Xếp hạng Top 5 Tiểu khu ưu tiên tuần tra cao nhất mỗi Tỉnh (Window Function)
-- Câu hỏi: Nếu mỗi tỉnh cần chọn ra 5 tiểu khu trọng điểm (có >= 20 điểm khảo sát)
--          để tập trung nguồn lực bảo vệ rừng trước tiên, đó là những tiểu khu nào?
-- ============================================================================
WITH ranked_subzones AS (
    SELECT
        province,
        district,
        spatial_group,
        sub_region,
        n_points,
        ROUND(100.0 * share_natural, 1)         AS pct_rung_tu_nhien,
        ROUND(100.0 * share_high_actual, 1)     AS pct_high_thuc_te,
        ROUND(100.0 * priority_index, 1)        AS chi_so_uu_tien_ml,
        ROUND(100.0 * share_hotspot, 1)         AS pct_diem_nong_gi,
        main_land_cover,
        ROW_NUMBER() OVER (
            PARTITION BY province
            ORDER BY priority_index DESC, share_hotspot DESC
        ) AS hang_trong_tinh
    FROM dim_subzone
    WHERE n_points >= 20
)
SELECT
    province            AS tinh,
    hang_trong_tinh,
    spatial_group       AS ma_tieu_khu,
    district            AS huyen,
    n_points            AS so_diem,
    pct_rung_tu_nhien,
    pct_high_thuc_te,
    chi_so_uu_tien_ml,
    pct_diem_nong_gi,
    main_land_cover     AS hien_trang_chinh
FROM ranked_subzones
WHERE hang_trong_tinh <= 5
ORDER BY province, hang_trong_tinh;


-- ============================================================================
-- BÀI TOÁN 6: Đánh giá hiệu quả Xếp hạng của Mô hình Học máy (Gain & Lift Analysis bằng SQL)
-- Câu hỏi: Nếu kiểm lâm đi tuần tra theo thứ tự xác suất `prob_high` giảm dần do ML
--          đề xuất (Top 5%, 10%, 20%, 30%, 50% số lô), sẽ phát hiện được bao nhiêu %
--          tổng số lô High thực tế so với đi tuần tra ngẫu nhiên?
-- ============================================================================
WITH ordered_points AS (
    SELECT
        id,
        priority,
        prob_high,
        ROW_NUMBER() OVER (ORDER BY prob_high DESC, id) AS rn,
        COUNT(*) OVER ()                                AS total_n,
        SUM(CASE WHEN priority = 'High' THEN 1 ELSE 0 END) OVER () AS total_high
    FROM fact_forest_points
),
cumulative AS (
    SELECT
        rn,
        total_n,
        total_high,
        100.0 * rn / total_n AS pct_inspected,
        SUM(CASE WHEN priority = 'High' THEN 1 ELSE 0 END)
            OVER (ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_high_found
    FROM ordered_points
),
thresholds AS (
    SELECT 5 AS top_pct UNION ALL SELECT 10 UNION ALL SELECT 20 UNION ALL SELECT 30 UNION ALL SELECT 50
)
SELECT
    t.top_pct || '%'                                                AS top_lo_kiem_tra,
    MAX(c.rn)                                                       AS so_lo_kiem_tra,
    MAX(c.cum_high_found)                                           AS so_lo_high_phat_hien,
    ROUND(100.0 * MAX(c.cum_high_found) / MAX(c.total_high), 1)     AS pct_high_thu_duoc_recall,
    ROUND(100.0 * MAX(c.cum_high_found) / MAX(c.rn), 1)             AS do_chinh_xac_precision_pct,
    ROUND((100.0 * MAX(c.cum_high_found) / MAX(c.total_high)) / t.top_pct, 2) AS he_so_lift
FROM thresholds t
JOIN cumulative c ON c.pct_inspected <= t.top_pct
GROUP BY t.top_pct
ORDER BY t.top_pct;


-- ============================================================================
-- BÀI TOÁN 7: Phân tích các trường hợp Mô hình Dự đoán Nhầm & "Ứng viên Ưu tiên Tiềm ẩn"
-- Câu hỏi: Các lỗi dự đoán tập trung vào kiểu nhầm nào? Những lô nào thực tế đang ghi
--          Medium nhưng vừa có xác suất ML rất cao (prob_high >= 0.70) vừa nằm trong
--          vùng nóng thực tế (Gi* >= 95%) -> cần đề xuất rà soát lại nhãn thực địa?
-- ============================================================================
SELECT
    error_type                                                      AS loai_du_doan,
    COUNT(*)                                                        AS so_lo,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)              AS ty_le_pct,
    ROUND(AVG(confidence), 3)                                       AS do_tu_tin_tb,
    ROUND(AVG(prob_high), 3)                                        AS prob_high_tb,
    SUM(CASE WHEN gi_bin_actual >= 2 THEN 1 ELSE 0 END)             AS so_lo_nam_trong_hotspot_95
FROM fact_forest_points
GROUP BY error_type
ORDER BY so_lo DESC;


-- ============================================================================
-- BÀI TOÁN 8: Phân tầng hành động quản lý không gian (Kết hợp ML + Getis-Ord Gi*)
-- Câu hỏi: Khi kết hợp xác suất học máy (`prob_high`) với thống kê điểm nóng không gian
--          (`gi_bin_pred`), toàn bộ 18.851 lô rừng được chia thành mấy nhóm hành động
--          và tỷ lệ High thực tế trong mỗi nhóm là bao nhiêu?
-- ============================================================================
SELECT
    action_tier                                                                     AS nhom_hanh_dong,
    COUNT(*)                                                                        AS so_lo,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)                              AS ty_trong_lo_pct,
    SUM(CASE WHEN actual_priority = 'High' THEN 1 ELSE 0 END)                       AS so_lo_high_thuc_te,
    ROUND(100.0 * AVG(CASE WHEN actual_priority = 'High' THEN 1.0 ELSE 0.0 END), 1) AS ty_le_high_thuc_te_pct,
    ROUND(AVG(prob_high), 3)                                                        AS prob_high_tb
FROM vw_patrol_priority_queue
GROUP BY action_tier
ORDER BY action_tier;

