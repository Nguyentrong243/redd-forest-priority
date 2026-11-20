# Hướng dẫn thực hành ArcMap 10.4.1 — Đồ án REDD+ (Nghệ An & Lâm Đồng)

## 1. Cấu trúc thư mục đã chuẩn bị sẵn

```text
outputs/arcmap/
├── mxd/                     # Lưu 2 file dự án: Nghe_An.mxd và Lam_Dong.mxd
├── boundary/                # Ranh giới GADM 4.1 đã cắt sẵn đúng 2 vùng nghiên cứu
│   ├── vn_quoc_gia.shp      # Toàn quốc Việt Nam (dùng cho Inset Map góc bản đồ)
│   ├── nghe_an_tinh.shp     # Ranh tỉnh Nghệ An
│   ├── nghe_an_2_huyen.shp  # 2 huyện Kỳ Sơn & Tương Dương
│   ├── nghe_an_xa.shp       # 39 xã thuộc Kỳ Sơn & Tương Dương
│   ├── lam_dong_tinh.shp    # Ranh tỉnh Lâm Đồng
│   ├── lam_dong_2_huyen.shp # 2 huyện Di Linh & Lạc Dương
│   └── lam_dong_xa.shp      # 25 xã thuộc Di Linh & Lạc Dương
└── exports/                 # Xuất ảnh PNG 300 DPI từ ArcMap vào đây
    ├── nghe_an/
    └── lam_dong/
```

Dữ liệu điểm và tiểu khu REDD+ lấy trực tiếp tại thư mục `outputs/gis/`:
- `redd_points_nghe_an.shp` (13.461 điểm)
- `redd_points_lam_dong.shp` (5.390 điểm)
- `subzone_summary.shp` (303 tiểu khu — tra tên cột rút gọn tại `outputs/gis/doi_chieu_ten_cot.csv`)

---

## 2. Tạo 2 file `.mxd` chuẩn (làm 1 lần, mất ~1 phút)

> **Lưu ý:** File `.mxd` là định dạng nhị phân riêng của ArcMap nên cần lưu trực tiếp từ trong ArcMap 10.4.1.

### A. Tạo `Nghe_An.mxd`
1. Mở **ArcMap 10.4.1** → chọn **Blank Map** → bấm **OK**.
2. Vào **File → Map Document Properties…** → tick **`Store relative pathnames to data sources`** → **OK**.
3. Chuột phải **`Layers`** (trong *Table of Contents*) → **Properties → Coordinate System** → chọn:
   `Projected Coordinate Systems → UTM → WGS 1984 → Northern Hemisphere → WGS 1984 UTM Zone 48N`.
4. Nhấn **Add Data (`+`)** thêm các lớp:
   - Từ `outputs/arcmap/boundary/`: `nghe_an_2_huyen.shp`, `nghe_an_xa.shp` (nền chính), và `nghe_an_tinh.shp` (nếu muốn làm Inset Map).
   - Từ `outputs/gis/`: `redd_points_nghe_an.shp`, `subzone_summary.shp`.
5. Vào **File → Save As…** lưu thành `outputs/arcmap/mxd/Nghe_An.mxd`.

### B. Tạo `Lam_Dong.mxd`
Làm giống hệt mục A nhưng đổi:
- Hệ chiếu Data Frame: **`WGS 1984 UTM Zone 49N`**.
- Lớp ranh giới từ `outputs/arcmap/boundary/`: `lam_dong_2_huyen.shp`, `lam_dong_xa.shp` (và `lam_dong_tinh.shp`).
- Lớp dữ liệu từ `outputs/gis/`: `redd_points_lam_dong.shp`, `subzone_summary.shp`.
- Lưu thành `outputs/arcmap/mxd/Lam_Dong.mxd`.

---

## 3. Chỉnh nền hành chính (mỗi `.mxd` làm 1 lần)

- `*_2_huyen`: *Fill Color* = `No Color`, *Outline Color* = xám đậm (`#4D4D4D`), *Outline Width* = `1.2`.
  - Bật nhãn (*Properties → Labels*): tick *Label features in this layer*, *Label Field* = **`NAME_2`**, font **`Arial`** (cỡ 10, Bold).
- `*_xa`: *Fill Color* = `No Color`, *Outline Color* = xám nhạt (`#BFBFBF`), *Outline Width* = `0.5`.
- Chuột phải lớp `*_2_huyen` → **Zoom To Layer** để căn vừa khung 2 huyện.

---

## 4. Nhân đôi lớp & tô Symbology cho 4 bản đồ (bật/tắt để xuất hàng loạt)

> **Mẹo chống bết màu:** Với lớp điểm (`redd_points_*`), luôn chỉnh **Size = `2.5` – `3.0` pt** và **Outline Color = `No Color`**.
> Trong tab *Symbology* → bấm **Advanced → Symbol Levels…** → tick bật và đưa `High` / `Hot spot 99%` vẽ **sau cùng (nằm trên cùng)**.

Trong mỗi file `.mxd`, **Copy & Paste** lớp `redd_points_*` thành 3–4 bản sao trong *Table of Contents*, đặt tên rõ ràng rồi cấu hình từng lớp:

### Lớp 1: `01_Uu_tien_Thuc_te` và `01_Uu_tien_Du_doan`
- *Symbology → Categories → Unique Values*:
  - Thực tế: Value Field = **`priority`**
  - Dự đoán ML: Value Field = **`pred_prio`**
- Bấm **Add All Values** → bỏ tick `<all other values>` → gán RGB:
  - `High`: `215, 25, 28` (Đỏ)
  - `Medium`: `253, 174, 97` (Cam vàng)
  - `Low`: `26, 150, 65` (Xanh lá)

### Lớp 2: `02_Vung_nong_Thuc_te` và `02_Vung_nong_Du_doan` (Getis-Ord Gi*)
- *Symbology → Categories → Unique Values*:
  - Thực tế: Value Field = **`hot_act`**
  - Dự đoán: Value Field = **`hot_pred`**
- Gán RGB chuẩn ArcGIS Hot Spot:
  - `Hot spot 99%`: `215, 25, 28` (Đỏ đậm)
  - `Hot spot 95%`: `240, 124, 74` (Cam đỏ)
  - `Hot spot 90%`: `254, 201, 128` (Vàng cam)
  - `Not significant`: `225, 225, 225` (Xám nhạt, Size = `2 pt`)
  - `Cold spot 90%`: `199, 230, 219` (Xanh ngọc nhạt)
  - `Cold spot 95%`: `127, 185, 215` (Xanh dương vừa)
  - `Cold spot 99%`: `44, 123, 182` (Xanh dương đậm)

### Lớp 3: `03_Tieu_khu_Uu_tien` (`subzone_summary.shp`)
- *Properties → **Definition Query*** (chỉ lọc đúng tỉnh và tiểu khu ≥ 10 điểm):
  - Nghệ An: `"province" = 'Nghe An' AND "reliable" = 1`
  - Lâm Đồng: `"province" = 'Lam Dong' AND "reliable" = 1`
- *Symbology → Quantities → Graduated Colors* (hoặc *Graduated Symbols*):
  - Value = **`prio_idx`**, chia 5 lớp màu từ Vàng nhạt → Đỏ đậm (Size `7–9 pt`).
- Dán nhãn **riêng Top 5 tiểu khu** (*Properties → Labels*):
  - *Method*: `Define classes of features and label each class differently`
  - *SQL Query*: `"rank_prov" >= 1 AND "rank_prov" <= 5`
  - *Expression* (VBScript): `"#" & [rank_prov] & " (" & [sub_region] & ")"`
  - *Symbol → Edit Symbol → Mask → Halo* (`1 pt` màu trắng).

### Lớp 4 *(tuỳ chọn)*: `04_Phan_du_Du_doan`
- *Symbology → Quantities → Graduated Colors* theo **`resid_high`** (5 lớp Đỏ – Trắng – Xanh dương), hoặc đặt *Definition Query*: `"error_type" <> 'Correct'` rồi tô *Unique Values* theo **`error_type`**.

---

## 5. Layout View & Quy ước đặt tên file xuất ảnh (300 DPI)

1. Chuyển sang **Layout View** (*View → Layout View*), chọn khổ A4 (*File → Page and Print Setup…*).
2. Thêm đủ 5 thành phần qua menu **Insert**:
   - **Title** (Tiêu đề bản đồ)
   - **Legend** (Chú giải — bỏ các lớp nền thừa nếu rối)
   - **North Arrow** (Mũi tên Bắc)
   - **Scale Bar** (đổi đơn vị sang **`Kilometers`**)
   - **Grids**: chuột phải Data Frame → *Properties → Grids → New Grid → Graticule*
   - *(Tuỳ chọn)* **Inset Map**: *Insert → Data Frame* → add `vn_quoc_gia.shp` (xám nhạt) + `nghe_an_tinh.shp` hoặc `lam_dong_tinh.shp` (tô đỏ).
3. **Bật đúng 1 lớp chuyên đề** (tắt các lớp chuyên đề còn lại) → sửa **Title** → **File → Export Map…** (`PNG`, **`300 dpi`**):
   - Vào `outputs/arcmap/exports/nghe_an/`:
     - `NA_01_uu_tien_thuc_te.png` / `NA_01_uu_tien_du_doan.png`
     - `NA_02_hotspot_thuc_te.png` / `NA_02_hotspot_du_doan.png`
     - `NA_03_xep_hang_tieu_khu.png`
     - `NA_04_phan_du_sai_so.png` *(tuỳ chọn)*
   - Vào `outputs/arcmap/exports/lam_dong/`:
     - `LD_01_uu_tien_thuc_te.png` / `LD_01_uu_tien_du_doan.png`
     - `LD_02_hotspot_thuc_te.png` / `LD_02_hotspot_du_doan.png`
     - `LD_03_xep_hang_tieu_khu.png`
     - `LD_04_phan_du_sai_so.png` *(tuỳ chọn)*

