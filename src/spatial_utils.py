"""Hàm tiện ích phân tích không gian cho đồ án REDD+.

Chỉ dùng numpy/scipy (và thư viện chuẩn Python) nên chạy được cả khi máy chưa cài
GeoPandas/PySAL. Công thức Moran's I và Getis-Ord Gi* giống với PySAL (esda) và công cụ
Spatial Statistics của ArcGIS (ArcMap 10.4.1 / ArcGIS Pro) để có thể đối chiếu kết quả.
"""
from __future__ import annotations

import datetime
import json
import math
import struct
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.spatial import cKDTree

EARTH_RADIUS_KM = 6371.0088


# ----------------------------------------------------------------------------
# Toạ độ
# ----------------------------------------------------------------------------
def project_xy_km(lat, lon, lat0: float | None = None) -> np.ndarray:
    """Chiếu WGS84 sang mặt phẳng (km) theo phép chiếu equirectangular.

    Sai số rất nhỏ với vùng nghiên cứu cỡ < 200 km (mỗi tỉnh ở đây chỉ ~70-120 km),
    đủ dùng để tìm láng giềng gần nhất (KNN). Mỗi tỉnh phải được xử lý RIÊNG.
    """
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    if lat0 is None:
        lat0 = float(np.mean(lat))
    x = EARTH_RADIUS_KM * np.deg2rad(lon) * math.cos(math.radians(lat0))
    y = EARTH_RADIUS_KM * np.deg2rad(lat)
    return np.column_stack([x, y])


# ----------------------------------------------------------------------------
# Ma trận trọng số không gian
# ----------------------------------------------------------------------------
def _knn_index(xy: np.ndarray, k: int) -> np.ndarray:
    """Trả về chỉ số k láng giềng gần nhất (không gồm chính điểm đó), shape (n, k)."""
    n = len(xy)
    _, idx = cKDTree(xy).query(xy, k=k + 1)
    self_mask = idx == np.arange(n)[:, None]
    # Nếu có nhiều điểm trùng toạ độ, chính điểm i có thể không nằm trong kết quả;
    # khi đó bỏ láng giềng xa nhất để mỗi dòng luôn có đúng k láng giềng.
    no_self = ~self_mask.any(axis=1)
    self_mask[no_self, -1] = True
    return idx[~self_mask].reshape(n, k)


def knn_weights(xy: np.ndarray, k: int = 8, row_standardize: bool = True,
                include_self: bool = False) -> sparse.csr_matrix:
    """Ma trận trọng số KNN dạng thưa (sparse)."""
    n = len(xy)
    nbr = _knn_index(xy, k)
    rows = np.repeat(np.arange(n), k)
    cols = nbr.ravel()
    if include_self:
        rows = np.concatenate([rows, np.arange(n)])
        cols = np.concatenate([cols, np.arange(n)])
    data = np.ones(len(rows), dtype=float)
    W = sparse.csr_matrix((data, (rows, cols)), shape=(n, n))
    if row_standardize:
        rs = np.asarray(W.sum(axis=1)).ravel()
        W = sparse.diags(1.0 / rs) @ W
    return W.tocsr()


# ----------------------------------------------------------------------------
# Global Moran's I
# ----------------------------------------------------------------------------
def morans_i(values, W: sparse.csr_matrix, permutations: int = 999,
             seed: int = 42) -> dict:
    """Global Moran's I, kiểm định bằng hoán vị (permutation test).

    W phải được chuẩn hoá theo dòng (row-standardized), khi đó S0 = n.
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    z = x - x.mean()
    denom = (z * z).sum()
    if denom == 0:
        return {"I": np.nan, "E[I]": -1 / (n - 1), "z_sim": np.nan, "p_sim": np.nan, "n": n}
    S0 = W.sum()
    I = (n / S0) * (z @ (W @ z)) / denom

    rng = np.random.default_rng(seed)
    sims = np.empty(permutations)
    for p in range(permutations):
        zp = rng.permutation(z)
        sims[p] = (n / S0) * (zp @ (W @ zp)) / denom
    larger = (sims >= I).sum()
    if (permutations - larger) < larger:
        larger = permutations - larger
    p_sim = (larger + 1.0) / (permutations + 1.0)
    z_sim = (I - sims.mean()) / sims.std(ddof=1)
    return {"I": float(I), "E[I]": -1.0 / (n - 1), "z_sim": float(z_sim),
            "p_sim": float(p_sim), "n": n}


# ----------------------------------------------------------------------------
# Getis-Ord Gi* (hot spot analysis)
# ----------------------------------------------------------------------------
def getis_ord_gi_star(values, xy: np.ndarray, k: int = 8) -> np.ndarray:
    """Z-score Gi* với trọng số nhị phân KNN có tính cả chính điểm đó (giống ArcGIS)."""
    x = np.asarray(values, dtype=float)
    n = len(x)
    W = knn_weights(xy, k=k, row_standardize=False, include_self=True)
    xbar = x.mean()
    s = math.sqrt((x ** 2).mean() - xbar ** 2)
    wi = np.asarray(W.sum(axis=1)).ravel()                 # = k + 1
    s1i = np.asarray(W.multiply(W).sum(axis=1)).ravel()    # = k + 1 (nhị phân)
    num = W @ x - xbar * wi
    den = s * np.sqrt((n * s1i - wi ** 2) / (n - 1))
    return num / den


def classify_hotspot(z: np.ndarray) -> np.ndarray:
    """Phân lớp hot/cold spot theo mức tin cậy 90/95/99% (giống ArcGIS Gi_Bin)."""
    z = np.asarray(z)
    labels = np.full(len(z), "Not significant", dtype=object)
    for thr, conf in [(1.645, "90%"), (1.960, "95%"), (2.576, "99%")]:
        labels[z >= thr] = f"Hot spot {conf}"
        labels[z <= -thr] = f"Cold spot {conf}"
    return labels


def gi_bin(z: np.ndarray) -> np.ndarray:
    """Mã số -3..3 như trường Gi_Bin của ArcGIS."""
    z = np.asarray(z)
    b = np.zeros(len(z), dtype=int)
    for i, thr in enumerate([1.645, 1.960, 2.576], start=1):
        b[z >= thr] = i
        b[z <= -thr] = -i
    return b


# ----------------------------------------------------------------------------
# Xuất GeoJSON (không cần GeoPandas)
# ----------------------------------------------------------------------------
def _clean(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if (np.isnan(v) or np.isinf(v)) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if pd.isna(v):
        return None
    return v


def to_geojson(df: pd.DataFrame, path, lat_col: str = "latitude",
               lon_col: str = "longitude", properties: list[str] | None = None) -> Path:
    """Ghi DataFrame điểm ra GeoJSON (EPSG:4326). Dùng được với ArcGIS (JSON To Features)."""
    path = Path(path)
    props = properties or [c for c in df.columns if c not in (lat_col, lon_col)]
    features = []
    for rec in df[[lat_col, lon_col] + props].to_dict("records"):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [float(rec[lon_col]), float(rec[lat_col])]},
            "properties": {p: _clean(rec[p]) for p in props},
        })
    fc = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
          "features": features}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    return path


# ----------------------------------------------------------------------------
# Xuất ESRI Shapefile điểm cho ArcMap 10.4.1 (thuần Python, không cần GeoPandas)
# ----------------------------------------------------------------------------
WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)


def _truncate_utf8(text: str, max_bytes: int) -> bytes:
    """Cắt chuỗi UTF-8 tối đa `max_bytes` byte mà không làm gãy ký tự đa byte."""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return raw
    while max_bytes > 0 and (raw[max_bytes] & 0xC0) == 0x80:
        max_bytes -= 1
    return raw[:max_bytes]


def to_shapefile(
    df: pd.DataFrame,
    path,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    field_map: dict[str, str] | None = None,
    float_decimals: int = 4,
) -> Path:
    """Ghi DataFrame điểm ra bộ ESRI Shapefile WGS84 (.shp, .shx, .dbf, .prj, .cpg).

    Tương thích trực tiếp với ArcMap 10.4.1 (Add Data mở ngay, không cần GeoJSON/GDAL):
    - Tên trường DBF bắt buộc ASCII, dài tối đa 10 ký tự (truyền qua `field_map`).
    - Kiểu bool được ghi dạng số nguyên 0/1 (Short Integer) để lọc thuận tiện trong ArcMap.
    - Giá trị thiếu của số nguyên/số thực ghi khoảng trắng DBF; nên điền sẵn 0 cho cột xếp hạng
      như `rank_prov` để tránh lỗi hiển thị trên ArcMap 10.4.1.
    """
    base = Path(path).with_suffix("")
    base.parent.mkdir(parents=True, exist_ok=True)

    if field_map is None:
        cols = [c for c in df.columns if c not in (lat_col, lon_col)]
        field_map = {c: c for c in cols}

    # Kiểm tra hợp lệ tên cột DBF (≤ 10 ký tự ASCII, không trùng)
    seen: set[str] = set()
    for orig, short in field_map.items():
        if orig not in df.columns:
            raise KeyError(f"Không tìm thấy cột '{orig}' trong DataFrame.")
        if not short.isascii() or not (1 <= len(short) <= 10):
            raise ValueError(f"Tên cột Shapefile '{short}' (từ '{orig}') phải là ASCII dài 1..10 ký tự.")
        low = short.lower()
        if low in seen:
            raise ValueError(f"Tên cột Shapefile bị trùng: '{short}'.")
        seen.add(low)

    n = len(df)
    lons = df[lon_col].astype(float).to_numpy()
    lats = df[lat_col].astype(float).to_numpy()
    if n > 0 and not (np.isfinite(lons).all() and np.isfinite(lats).all()):
        raise ValueError("Tồn tại toạ độ NaN/Inf, không thể ghi Shapefile.")

    xmin, xmax = (float(lons.min()), float(lons.max())) if n else (0.0, 0.0)
    ymin, ymax = (float(lats.min()), float(lats.max())) if n else (0.0, 0.0)

    # 1. File .shp (Main file — Shape Type 1: Point)
    shp_header = (
        struct.pack(">7i", 9994, 0, 0, 0, 0, 0, 50 + 14 * n)
        + struct.pack("<2i8d", 1000, 1, xmin, ymin, xmax, ymax, 0.0, 0.0, 0.0, 0.0)
    )
    with open(base.with_suffix(".shp"), "wb") as f_shp:
        f_shp.write(shp_header)
        for i in range(n):
            f_shp.write(struct.pack(">2i", i + 1, 10))
            f_shp.write(struct.pack("<i2d", 1, float(lons[i]), float(lats[i])))

    # 2. File .shx (Index file)
    shx_header = (
        struct.pack(">7i", 9994, 0, 0, 0, 0, 0, 50 + 4 * n)
        + struct.pack("<2i8d", 1000, 1, xmin, ymin, xmax, ymax, 0.0, 0.0, 0.0, 0.0)
    )
    with open(base.with_suffix(".shx"), "wb") as f_shx:
        f_shx.write(shx_header)
        for i in range(n):
            f_shx.write(struct.pack(">2i", 50 + 14 * i, 10))

    # 3. File .dbf (dBASE III+ attribute table)
    specs: list[tuple[str, str, str, int, int]] = []
    for orig, short in field_map.items():
        s = df[orig]
        if pd.api.types.is_bool_dtype(s):
            specs.append((orig, short, "N", 4, 0))
        elif pd.api.types.is_integer_dtype(s):
            valid = s.dropna()
            max_w = max((len(str(int(v))) for v in valid), default=1)
            flen = 9 if max_w <= 9 else min(18, max_w)
            specs.append((orig, short, "N", flen, 0))
        elif pd.api.types.is_float_dtype(s):
            flen = max(14, float_decimals + 8)
            specs.append((orig, short, "N", flen, float_decimals))
        else:
            valid = s.dropna().astype(str)
            max_b = max((len(v.encode("utf-8")) for v in valid), default=1)
            flen = min(254, max(10, max_b))
            specs.append((orig, short, "C", flen, 0))

    today = datetime.date.today()
    header_len = 32 + 32 * len(specs) + 1
    rec_len = 1 + sum(sp[3] for sp in specs)
    dbf_header = struct.pack(
        "<4BIHH17sB2s",
        0x03,
        today.year - 1900,
        today.month,
        today.day,
        n,
        header_len,
        rec_len,
        b"\x00" * 17,
        0x00,
        b"\x00\x00",
    )

    col_arrays = [df[orig].tolist() for orig, *_ in specs]
    with open(base.with_suffix(".dbf"), "wb") as f_dbf:
        f_dbf.write(dbf_header)
        for _, short, ftype, flen, fdec in specs:
            f_dbf.write(
                short.encode("ascii").ljust(11, b"\x00")
                + ftype.encode("ascii")
                + b"\x00" * 4
                + struct.pack("<BB", flen, fdec)
                + b"\x00" * 14
            )
        f_dbf.write(b"\x0d")

        for i in range(n):
            parts = [b" "]
            for col_idx, (_, short, ftype, flen, fdec) in enumerate(specs):
                v = col_arrays[col_idx][i]
                if ftype == "C":
                    raw = b"" if pd.isna(v) else _truncate_utf8(str(v), flen)
                    parts.append(raw.ljust(flen, b" "))
                elif fdec == 0:
                    if pd.isna(v):
                        parts.append(b" " * flen)
                    else:
                        txt = f"{int(v):>{flen}d}"
                        if len(txt) > flen:
                            raise OverflowError(f"Giá trị {v} vượt độ dài {flen} ở cột '{short}'.")
                        parts.append(txt.encode("ascii"))
                else:
                    if pd.isna(v) or not math.isfinite(float(v)):
                        parts.append(b" " * flen)
                    else:
                        txt = f"{float(v):>{flen}.{fdec}f}"
                        if len(txt) > flen:
                            raise OverflowError(f"Giá trị {v} vượt độ dài {flen} ở cột '{short}'.")
                        parts.append(txt.encode("ascii"))
            f_dbf.write(b"".join(parts))
        f_dbf.write(b"\x1a")

    # 4. File .prj (WGS84 chuẩn ESRI) và .cpg (UTF-8)
    base.with_suffix(".prj").write_text(WGS84_PRJ, encoding="ascii")
    base.with_suffix(".cpg").write_text("UTF-8", encoding="ascii")
    return base.with_suffix(".shp")
