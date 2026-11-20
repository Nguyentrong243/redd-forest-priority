"""Các lớp tuỳ biến dùng trong Pipeline của mô hình (notebook 03).

Đặt trong module riêng (không định nghĩa trong notebook) để mô hình lưu bằng joblib
có thể được nạp lại ở nơi khác (script, ứng dụng web...) chỉ với `import src.model_utils`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin
from sklearn.cluster import KMeans

from .spatial_utils import project_xy_km

PRIORITY_ORDER = ["High", "Medium", "Low"]


class ProvinceKMeansFeatures(BaseEstimator, TransformerMixin):
    """Thêm cụm không gian KMeans (fit RIÊNG từng tỉnh) và khoảng cách (km) tới tâm cụm gần nhất.

    Đặt trong Pipeline nên khi cross-validation, KMeans chỉ học trên tập train của từng fold
    -> không rò rỉ thông tin từ tập test.
    """

    def __init__(self, n_clusters: int = 6, random_state: int = 42):
        self.n_clusters = n_clusters
        self.random_state = random_state

    def fit(self, X, y=None):
        self.models_, self.lat0_ = {}, {}
        for prov, sub in X.groupby("province"):
            lat0 = float(sub["latitude"].mean())
            xy = project_xy_km(sub["latitude"].values, sub["longitude"].values, lat0)
            km = KMeans(n_clusters=min(self.n_clusters, len(sub)), n_init=10, random_state=self.random_state)
            self.models_[prov] = km.fit(xy)
            self.lat0_[prov] = lat0
        return self

    def transform(self, X):
        X = X.copy()
        min_dist = np.zeros(len(X))
        cluster = np.full(len(X), "unknown", dtype=object)
        for prov, km in self.models_.items():
            m = (X["province"] == prov).values
            if not m.any():
                continue
            xy = project_xy_km(X.loc[m, "latitude"].values, X.loc[m, "longitude"].values, self.lat0_[prov])
            d = km.transform(xy)
            min_dist[m] = d.min(axis=1)
            cluster[m] = [f"{prov}_{c}" for c in d.argmin(axis=1)]
        X["kmeans_min_dist_km"] = min_dist
        X["kmeans_cluster"] = cluster
        return X


class OriginRuleClassifier(BaseEstimator, ClassifierMixin):
    """Baseline luật 1 dòng rút ra từ EDA: Rừng tự nhiên -> Medium, Rừng trồng -> Low."""

    def fit(self, X, y):
        self.classes_ = np.array(PRIORITY_ORDER)
        t = pd.crosstab(X["forest_origin"].values, np.asarray(y), normalize="index")
        self.probs_ = t.reindex(columns=self.classes_, fill_value=0.0)
        return self

    def predict(self, X):
        return np.where(X["forest_origin"].values == "Natural forest", "Medium", "Low")

    def predict_proba(self, X):
        return self.probs_.reindex(X["forest_origin"].values).fillna(1 / 3).values

