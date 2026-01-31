This is the design for a propagation tool that will answers the operator question:
	•	Can I likely move traffic (VARA/Winlink) intra-island in Hawaii right now?
	•	Can I likely move traffic (VARA/Winlink) to the mainland (West coast of CONUS) right now?

⸻

0) Design principles (so the indicator behaves correctly)
	1.	Use observed RF reports as truth (PSKReporter spots) to detect real openings.
	2.	Avoid FT8 optimism: FT8 detects paths far below usable SNR for throughput-based links.
	3.	Use JS8Call as “data viability” proxy: if JS8Call is working, odds of VARA success rise sharply.
	4.	Separate three things:
	•	Propagation exists (FT8)
	•	Data link likely (JS8 presence and/or strong FT8 SNR)
	•	Data link quality (SNR + stability + diversity)
	5.	Be stable: add hysteresis and confidence gating to avoid flapping.

⸻

1) Outputs (the contract)

Your script produces a single JSON document per run:

1.1 Output JSON schema (exact fields)
{
  "timestamp_utc": "2026-01-31T06:00:00Z",
  "window_minutes": 30,

  "nvis": {
    "status": "GOOD|MARGINAL|POOR|UNKNOWN",
    "vara_class": "LIKELY|POSSIBLE|UNLIKELY|UNKNOWN",
    "score": 0,
    "confidence": "HIGH|MEDIUM|LOW",
    "bands": {
      "80m": {"score": 0, "paths": 0, "tx": 0, "rx": 0, "median_snr_db": null, "js8_paths": 0, "ft8_paths": 0},
      "40m": {"score": 0, "paths": 0, "tx": 0, "rx": 0, "median_snr_db": null, "js8_paths": 0, "ft8_paths": 0},
      "30m": {"score": 0, "paths": 0, "tx": 0, "rx": 0, "median_snr_db": null, "js8_paths": 0, "ft8_paths": 0}
    },
    "explain": "human-readable, <=160 chars"
  },

  "mainland": {
    "status": "OPEN|INTERMITTENT|CLOSED|UNKNOWN",
    "vara_class": "LIKELY|POSSIBLE|UNLIKELY|UNKNOWN",
    "score": 0,
    "confidence": "HIGH|MEDIUM|LOW",
    "bands": {
      "20m": {"score": 0, "paths": 0, "tx": 0, "rx": 0, "median_snr_db": null, "js8_paths": 0, "ft8_paths": 0},
      "17m": {"score": 0, "paths": 0, "tx": 0, "rx": 0, "median_snr_db": null, "js8_paths": 0, "ft8_paths": 0},
      "15m": {"score": 0, "paths": 0, "tx": 0, "rx": 0, "median_snr_db": null, "js8_paths": 0, "ft8_paths": 0},
      "12m": {"score": 0, "paths": 0, "tx": 0, "rx": 0, "median_snr_db": null, "js8_paths": 0, "ft8_paths": 0},
      "10m": {"score": 0, "paths": 0, "tx": 0, "rx": 0, "median_snr_db": null, "js8_paths": 0, "ft8_paths": 0}
    },
    "explain": "human-readable, <=160 chars"
  },

  "sources": {
    "pskreporter": {"ok": true, "last_fetch_utc": "2026-01-31T05:55:00Z", "requests_last_hour": 0},
    "notes": "optional diagnostics"
  }
}

Status semantics
	•	status describes propagation availability (public-friendly)
	•	vara_class describes Winlink/VARA usability likelihood (operator-relevant)
	•	confidence describes data sufficiency

⸻

2) Inputs and constants (no ambiguity)

2.1 Time window and cadence
	•	WINDOW_MIN = 30
	•	Run every POLL_MIN = 5 minutes
	•	Each run recomputes using trailing 30 minutes

2.2 Bands and frequency ranges (Hz)

NVIS bands
	•	80m: 3,500,000–4,000,000
	•	40m: 7,000,000–7,300,000
	•	30m: 10,100,000–10,150,000

Mainland bands
	•	20m: 14,000,000–14,350,000
	•	17m: 18,068,000–18,168,000
	•	15m: 21,000,000–21,450,000
	•	12m: 24,890,000–24,990,000
	•	10m: 28,000,000–29,700,000

2.3 Modes to query
	•	MODES = ["FT8", "JS8"]
	•	(Optional extension: include “CW” later; not required for this tuned spec)

2.4 Geographic filters

Hawaii bounding box
	•	lat: 18.5–23.0
	•	lon: −161.0 to −154.0

CONUS bounding box
	•	lat: 24.0–49.5
	•	lon: −125.0 to −66.0

Distance thresholds (km)
	•	NVIS_MAX_KM = 450
	•	MAINLAND_MIN_KM = 3000
	•	MAINLAND_MAX_KM = 5200

2.5 Grid handling
	•	Use Maidenhead locator → lat/lon at center
	•	Accept 4-char or 6-char locators
	•	If 6-char, still normalize to 4-char for aggregation keys

⸻

3) Data acquisition from PSKReporter

3.1 Endpoint
	•	Base: https://retrieve.pskreporter.info/query

3.2 Query strategy (rate-safe, Hawaii-focused)

You cannot reliably query “all Hawaii” in one request. Use anchor grids.

3.2.1 Anchor grids (initial set)

Define 10 anchors (tweakable), each as a 4-char Maidenhead:
	•	Oahu/Honolulu region (2–3 anchors)
	•	Kauai (1)
	•	Maui (1–2)
	•	Big Island east/west (2–3)
	•	Molokai/Lanai (1)

Implementation requirement: anchors are a config file, e.g.:

{"anchors": ["BL11", "BL12", "BL02", "BK29", "BK19", "BL01", "BL21", "BL22", "BK28", "BK18"]}

3.2.2 Per-run request budget

Hard caps:
	•	MAX_REQUESTS_PER_RUN = 12
	•	MAX_REQUESTS_PER_HOUR = 120
	•	MIN_SECONDS_BETWEEN_IDENTICAL_URL = 300 (cache)

3.2.3 Rotation plan (deterministic)

Each run:
	1.	Pick ANCHORS_THIS_RUN = first 4 anchors in a rotating window
	2.	Query two bands per run per mode:
	•	NVIS: rotate among 80/40/30
	•	Mainland: rotate among 20/17/15/12/10
	3.	Always query both modes (FT8 + JS8) for each selected band.

This yields (example):
	•	4 anchors × 2 bands × 2 modes = 16 requests → too high
So constrain further:

Final per-run plan (meets 12 req/run):
	•	3 anchors per run
	•	2 bands per run
	•	2 modes per band
→ 3 × 2 × 2 = 12 requests/run

Over 15 minutes you cover 9 anchors; over 30 minutes you cover all 10 anchors at least once.

3.2.4 URL template

For each anchor + band + mode:
	•	callsign=<ANCHOR>
	•	modify=grid  (callsign interpreted as grid)
	•	flowStartSeconds=-(WINDOW_MIN*60) i.e. -1800
	•	rronly=1
	•	rptlimit=2000
	•	mode=<MODE>
	•	frange=<LOW>-<HIGH>
	•	(Optional but recommended) appcontact=<email>

⸻

4) Parsing and normalization

4.1 Parse response XML

Extract each <receptionReport ...> into a normalized record:

{
  "t_utc": "...",          // derive from server time + report age if available; otherwise "now" minus flow bucket
  "mode": "FT8|JS8",
  "freq_hz": 7074000,
  "snr_db": -12,           // if missing -> null
  "sender_loc": "BL11aa",  // raw
  "receiver_loc": "BL02bb",
  "sender4": "BL11",
  "receiver4": "BL02",
  "sender_lat": 21.3,
  "sender_lon": -157.9,
  "receiver_lat": 20.8,
  "receiver_lon": -156.3,
  "distance_km": 140.2
}

Required behavior if fields missing
	•	If either locator missing/invalid → drop record
	•	If frequency missing → drop record
	•	If mode missing → infer from query mode used
	•	If SNR missing → allow record but SNR metrics become null for that aggregation bucket

4.2 Deduplication

Deduplicate per-run at minimum by:
	•	key = (mode, band, sender4, receiver4)
Keep the best (highest SNR) record for that key in the window.

(Reason: avoids multiple identical spots inflating.)

⸻

5) Classification: NVIS vs Mainland path sets

For each record, determine membership:

5.1 Compute flags
	•	sender_in_hi if sender lat/lon within HI bbox
	•	receiver_in_hi similarly
	•	sender_in_conus within CONUS bbox
	•	receiver_in_conus similarly

5.2 NVIS candidate

Record contributes to NVIS if:
	•	sender_in_hi AND receiver_in_hi
	•	band in {80,40,30}
	•	distance_km ≤ NVIS_MAX_KM

5.3 Mainland candidate

Record contributes to Mainland if:
	•	(sender_in_hi AND receiver_in_conus) OR (sender_in_conus AND receiver_in_hi)
	•	band in {20,17,15,12,10}
	•	MAINLAND_MIN_KM ≤ distance_km ≤ MAINLAND_MAX_KM

⸻

6) Scoring (propagation score) — unchanged structure, tuned thresholds

We keep your earlier 0–100 scores but adjust targets and thresholds to be Winlink/VARA conservative.

6.1 Mode weights (for scoring)

Apply to path counts and diversity counts:
	•	W_FT8 = 1.0
	•	W_JS8 = 1.8  (increased from 1.6 → more VARA-aligned)

6.2 Per-band aggregation metrics (within window)

For each indicator + band:
	•	P_weighted = sum over unique (sender4, receiver4) of mode weight
	•	TX_weighted = weighted count of unique sender4 by mode presence
	•	RX_weighted = weighted count of unique receiver4 by mode presence
	•	S_median_db = median SNR over deduped records (all modes combined), if any
	•	JS8_paths = count of unique (sender4, receiver4) where mode=JS8
	•	FT8_paths similarly

How to combine mode weights for TX/RX

For each unique sender4, compute:
	•	if sender4 appears in JS8 paths: add 1.8
	•	else if only FT8: add 1.0
Same for receiver4.

6.3 Normalize activity and diversity

Use log scaling to reduce spikes:

Targets (tuned)

NVIS typically has more local activity (if there are local digimode users). Mainland is sparser.
	•	P_target_nvis = 8  (lowered slightly to reduce “all red at night”)
	•	P_target_mainland = 5
	•	D_target_nvis = 3
	•	D_target_mainland = 3

Formulas:

p_norm = min(1, ln(1 + P_weighted) / ln(1 + P_target))
d_norm = min(1, ln(1 + min(TX_weighted, RX_weighted)) / ln(1 + D_target))

6.4 SNR normalization (important for VARA tuning)

This is where we become more conservative than general propagation.

Define clamp range:
	•	SNR_MIN = -24
	•	SNR_MAX = 0

s_norm = clamp((S_median_db - SNR_MIN) / (SNR_MAX - SNR_MIN), 0, 1)

6.5 Per-band propagation score

If SNR exists:

band_score = 100*(0.45*p_norm + 0.20*d_norm + 0.35*s_norm)


If SNR missing:

band_score = 100*(0.70*p_norm + 0.30*d_norm)

7) Aggregation weights (bands) — same as your updated version

7.1 NVIS weights
	•	40m: 0.45
	•	80m: 0.40
	•	30m: 0.15

7.2 Mainland weights
	•	20m: 0.40
	•	17m: 0.20
	•	15m: 0.15
	•	12m: 0.15
	•	10m: 0.10

⸻

8) Status mapping (propagation), with hysteresis

8.1 NVIS status thresholds
	•	GOOD: ≥ 70
	•	MARGINAL: 40–69
	•	POOR: < 40

8.2 Mainland status thresholds
	•	OPEN: ≥ 60
	•	INTERMITTENT: 30–59
	•	CLOSED: < 30

8.3 Hysteresis (anti-flap)

Let T be the boundary threshold. Use H = 5.
	•	Upgrade requires score ≥ (T + H)
	•	Downgrade requires score < (T − H)

Persist previous statuses in a small local state file.

⸻

9) VARA/Winlink usability classification (NEW + tuned)

This is the part you asked to tune first. It produces vara_class and is stricter than propagation status.

9.1 Core idea

Use a “VARA viability score” that:
	•	strongly rewards JS8 presence
	•	requires SNR above a threshold for “LIKELY”
	•	avoids declaring LIKELY on FT8-only weak paths

9.2 Per-band VARA viability score (0–100)

Compute:

A) JS8 presence factor

Let js8_ratio = JS8_paths / max(1, JS8_paths + FT8_paths)

Define:
	•	js8_factor = clamp(js8_ratio / 0.25, 0, 1)
	•	reaches 1.0 when ≥25% of paths are JS8
	•	still gives partial credit with some JS8

B) SNR suitability factor

VARA success depends heavily on bandwidth, interleaving, QRM, and station setup. We can’t know those, so we tune conservatively with SNR proxies:

Define band-type thresholds:
	•	NVIS SNR threshold for “likely usable”: SNR_OK_NVIS = -10
	•	Mainland SNR threshold for “likely usable”: SNR_OK_MAINLAND = -12
	•	Strong threshold: SNR_STRONG = -6

Convert median SNR to factor:
	•	If S_median_db is null → snr_factor = 0.3 (unknown)
	•	else:
	•	snr_factor = 0 if S < SNR_OK
	•	linear ramp to 1 by SNR_STRONG

Example:

snr_factor = clamp((S_median_db - SNR_OK) / (SNR_STRONG - SNR_OK), 0, 1)

C) Propagation baseline factor

Use the earlier band_score but damp it (FT8 optimism):
	•	base_factor = band_score / 100

D) Combine to per-band VARA score

Weights tuned for VARA:
	•	JS8 is most important, then SNR, then baseline propagation

    vara_band = 100*(0.45*js8_factor + 0.35*snr_factor + 0.20*base_factor)



    If JS8_paths == 0, apply a penalty:
	•	vara_band *= 0.70
(This prevents FT8-only from going green too easily.)

9.3 Aggregate VARA score per indicator

Same band weights as propagation:

vara_nvis = Σ(w_band * vara_band)
vara_mainland = Σ(w_band * vara_band)

9.4 Map VARA score → vara_class (tuned)

NVIS vara_class
	•	LIKELY: ≥ 65
	•	POSSIBLE: 35–64
	•	UNLIKELY: < 35

Mainland vara_class
	•	LIKELY: ≥ 60
	•	POSSIBLE: 30–59
	•	UNLIKELY: < 30

9.5 Override rules (operator realism)

These handle edge cases:
	1.	If JS8 exists on any band with S_median_db ≥ SNR_OK, then minimum class is POSSIBLE (even if score is low).
	2.	If JS8 exists on ≥2 mainland bands or JS8_paths total ≥ 3, then boost mainland vara_mainland by +10 (cap 100).
	3.	If only FT8 exists and median SNR is below SNR_OK, cap vara_class at POSSIBLE (never LIKELY).

⸻

10) Confidence model (data sufficiency)

Confidence affects whether you show UNKNOWN vs a real status.

10.1 Compute confidence inputs per indicator
	•	records_total = total deduped records contributing to that indicator (any band)
	•	anchors_reporting = number of anchors that returned ≥1 valid record in window
	•	fresh_minutes = minutes since last successful PSKReporter fetch

10.2 Confidence thresholds (tuned)

HIGH
	•	records_total ≥ 30
	•	anchors_reporting ≥ 3
	•	fresh_minutes ≤ 10

MEDIUM
	•	records_total ≥ 10
	•	anchors_reporting ≥ 2
	•	fresh_minutes ≤ 20

LOW
	•	otherwise

10.3 UNKNOWN behavior (public-safe)

If confidence is LOW and records_total == 0:
	•	set status = UNKNOWN
	•	set vara_class = UNKNOWN
	•	explain = “Limited recent reports.”

If confidence LOW but records_total > 0:
	•	keep computed status, but explain includes “Low report volume.”

⸻

11) Explain strings (must be deterministic)

Generate explain from simple templates:

NVIS explain template
	•	If status GOOD: "Strong inter-island paths on 40m/80m (JS8 present)." / "(FT8 only)."
	•	If MARGINAL: "Some inter-island activity; expect variability."
	•	If POOR: "Little inter-island activity in last 30m."
	•	If UNKNOWN: "Limited recent reports."

Include “JS8 present” only when JS8_paths_total >= 1.

Mainland explain template
	•	If OPEN: "HI↔CONUS paths observed on 20m+ (JS8 present)." / "(FT8 only)."
	•	If INTERMITTENT: "Intermittent HI↔CONUS activity; openings may be brief."
	•	If CLOSED: "No recent HI↔CONUS paths observed."
	•	If UNKNOWN: "Limited recent reports."

⸻

12) Persistence and state

Store a local state.json:


{
  "last": {
    "nvis_status": "MARGINAL",
    "mainland_status": "INTERMITTENT",
    "timestamp_utc": "..."
  }
}

Used only for hysteresis.

⸻

13) Validation checklist (so you know it’s correct)

Your implementation is correct if:
	1.	With only a handful of FT8 spots at very low SNR, propagation may show MARGINAL but VARA shows POSSIBLE/UNLIKELY.
	2.	When JS8 appears, VARA class jumps upward even if FT8 volume is modest.
	3.	When higher bands open (10/12/15), mainland propagation increases, but VARA still requires decent SNR/JS8 to be LIKELY.
	4.	Status does not flap on single reports due to hysteresis and confidence gating.

⸻

14) What you should expose on the public dashboard

Public-facing:
	•	Inter-Island HF (NVIS): GOOD/MARGINAL/POOR
	•	Mainland HF Reach: OPEN/INTERMITTENT/CLOSED
	•	Confidence indicator (small)

Operator-facing (optional tooltip/secondary label):
	•	Data link (Winlink/VARA): LIKELY/POSSIBLE/UNLIKELY


