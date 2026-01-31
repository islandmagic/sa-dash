from __future__ import annotations

import json
from pathlib import Path

WINDOW_MIN = 60
POLL_MIN = 5

MODES = ["FT8", "JS8", "WSPR"]

NVIS_BANDS = {
    "80m": (3_500_000, 4_000_000),
    "40m": (7_000_000, 7_300_000),
    "30m": (10_100_000, 10_150_000),
}

NVIS_BAND_ORDER = ["80m", "40m", "30m"]

MAINLAND_BANDS = {
    "80m": (3_500_000, 4_000_000),
    "40m": (7_000_000, 7_300_000),
    "30m": (10_100_000, 10_150_000),
    "20m": (14_000_000, 14_350_000),
    "17m": (18_068_000, 18_168_000),
    "15m": (21_000_000, 21_450_000),
    "12m": (24_890_000, 24_990_000),
    "10m": (28_000_000, 29_700_000),
}

MAINLAND_BAND_ORDER = ["80m", "40m", "30m", "20m", "17m", "15m", "12m", "10m"]

ALL_BANDS = {**NVIS_BANDS, **MAINLAND_BANDS}

NVIS_BAND_WEIGHTS = { "80m": 0.40, "40m": 0.45, "30m": 0.15}
MAINLAND_BAND_WEIGHTS = {
    "80m": 0.08,
    "40m": 0.12,
    "30m": 0.10,
    "20m": 0.28,
    "17m": 0.14,
    "15m": 0.12,
    "12m": 0.10,
    "10m": 0.06,
}

W_FT8 = 1.0
W_JS8 = 1.8
W_WSPR = 0.4

P_TARGET_NVIS = 8
P_TARGET_MAINLAND = 5
D_TARGET_NVIS = 3
D_TARGET_MAINLAND = 3

SNR_MIN = -24
SNR_MAX = 0

SNR_OK_NVIS = -10
SNR_OK_MAINLAND = -12
SNR_STRONG = -6

NVIS_THRESHOLDS = {"GOOD": 70, "MARGINAL": 40}
MAINLAND_THRESHOLDS = {"OPEN": 60, "INTERMITTENT": 30}
HYSTERESIS = 5

VARA_THRESHOLDS_NVIS = {"LIKELY": 65, "POSSIBLE": 35}
VARA_THRESHOLDS_MAINLAND = {"LIKELY": 60, "POSSIBLE": 30}

BBOX_HI = {
    "lat_min": 18.5,
    "lat_max": 23.0,
    "lon_min": -161.0,
    "lon_max": -154.0,
}

BBOX_CONUS = {
    "lat_min": 24.0,
    "lat_max": 49.5,
    "lon_min": -125.0,
    "lon_max": -66.0,
}

NVIS_MAX_KM = 450
MAINLAND_MIN_KM = 3000
MAINLAND_MAX_KM = 5200

MIN_SECONDS_BETWEEN_IDENTICAL_URL = 300

DEFAULT_APP_CONTACT = None
GRID_QUERIES = ["BL", "BK"]


