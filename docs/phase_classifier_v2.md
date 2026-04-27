# phase_classifier_v2

Rule table ini adalah spesifikasi implementable untuk phase classifier berbasis structure.

| Priority | Rule | Minimum Conditions | chart_phase | action | reason_code |
| --- | --- | --- | --- | --- | --- |
| 1 | Upper resistance rejection | `near_resistance` dan candle M15 rejection | `UPPER_RANGE_EXHAUSTION_RISK` | `PROTECT_LONG_OR_SELL_REJECTION` | `UPPER_RESISTANCE_REJECTION` |
| 2 | Upper range distribution | `near_resistance` tanpa rejection konklusif | `UPPER_RANGE_DISTRIBUTION` | `WAIT_BREAKOUT_OR_REJECTION` | `UPPER_RANGE_DISTRIBUTION` |
| 3 | Failed reclaim | harga gagal bertahan di atas `reclaim_level` | `FAILED_RECLAIM` | `SELL_ON_RALLY_OR_CONTINUATION` | `FAILED_RECLAIM_AT_PIVOT` |
| 4 | Pivot reclaim continuation | reclaim H1/M15 valid dan tidak near resistance | `PIVOT_RECLAIM_CONTINUATION` | `BUY_ON_RETEST_OR_RECLAIM_HOLD` | `PIVOT_RECLAIM_VALID` |
| 5 | High-base compression | kompresi M15 rapat di area atas tanpa reclaim yang lebih jelas | `HIGH_BASE_COMPRESSION` | `BUY_BREAKOUT_OR_RETEST` | `HIGH_BASE_COMPRESSION_READY` |
| 6 | Breakdown confirmation | close M15 konfirmasi di bawah support/breakdown level | `BREAKDOWN_CONFIRMATION` | `SELL_ON_RALLY_OR_CONTINUATION` | `SUPPORT_BREAKDOWN_CONFIRMED` |
| 7 | Lower-high rejection | bearish pullback H1/M15 aktif di luar support | `BEARISH_PULLBACK_CONTINUATION` | `SELL_ON_RALLY_OR_CONTINUATION` | `LOWER_HIGH_REJECTION` |
| 8 | Support decision | `near_support` tanpa konfirmasi reclaim/breakdown | `SUPPORT_REACTION_PENDING` | `WAIT_SUPPORT_REACTION_OR_RECLAIM` | `SUPPORT_DECISION_PENDING` |
| 9 | Range mid | tidak ada edge struktural | `RANGE_MID_NO_EDGE` | `NO_TRADE_WAIT_CONTEXT` | `RANGE_MID_NO_EDGE` |

## Level Inputs

`level_detector_v2` harus mengisi field berikut di snapshot:

- `range_low`
- `range_high`
- `pivot_mid`
- `support`
- `resistance`
- `reclaim_level`
- `breakdown_level`
- `breakout_level`
- `nearest_supply_zone`
- `nearest_demand_zone`

## Scenario Payload Contract

Setiap hasil classifier harus mengembalikan:

- `reason_code`
- `primary_scenario`
- `alternative_scenario`
- `no_trade_condition`

`trade_plan_builder` boleh tetap menampilkan satu `action` ringkas untuk dashboard, tetapi payload harus menyimpan seluruh scenario set.
