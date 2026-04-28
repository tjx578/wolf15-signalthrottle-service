# phase_classifier_v2

Rule table ini adalah spesifikasi implementable untuk phase classifier berbasis structure.

| Priority | Rule | Minimum Conditions | chart_phase | action | reason_code |
| --- | --- | --- | --- | --- | --- |
| 1 | Upper failed expansion | `near_resistance` dan breakout gagal accept di atas `breakout_level` | `UPPER_RANGE_EXHAUSTION_RISK` | `WAIT_BREAKOUT_OR_REJECTION` | `UPPER_RANGE_FAILED_EXPANSION` |
| 2 | Upper resistance rejection | `near_resistance` dan candle M15 rejection | `UPPER_RANGE_EXHAUSTION_RISK` | `PROTECT_LONG_OR_SELL_REJECTION` | `UPPER_RESISTANCE_REJECTION` |
| 3 | Upper range distribution | `near_resistance` tanpa rejection konklusif | `UPPER_RANGE_DISTRIBUTION` | `WAIT_BREAKOUT_OR_REJECTION` | `UPPER_RANGE_DISTRIBUTION` |
| 4 | Failed reclaim | harga gagal bertahan di atas `reclaim_level` | `FAILED_RECLAIM` | `SELL_ON_RALLY_OR_CONTINUATION` | `FAILED_RECLAIM_AT_PIVOT` |
| 5 | Pivot reclaim continuation | reclaim H1/M15 valid dan tidak near resistance | `PIVOT_RECLAIM_CONTINUATION` | `BUY_ON_RETEST_OR_RECLAIM_HOLD` | `PIVOT_RECLAIM_VALID` |
| 6 | High-base compression | kompresi M15 rapat di area atas tanpa reclaim yang lebih jelas | `HIGH_BASE_COMPRESSION` | `BUY_BREAKOUT_OR_RETEST` | `HIGH_BASE_COMPRESSION_READY` |
| 7 | Breakdown confirmation | close M15 konfirmasi di bawah support/breakdown level | `BREAKDOWN_CONFIRMATION` | `SELL_ON_RALLY_OR_CONTINUATION` | `SUPPORT_BREAKDOWN_CONFIRMED` |
| 8 | Lower-high rejection | bearish pullback H1/M15 aktif di luar support | `BEARISH_PULLBACK_CONTINUATION` | `SELL_ON_RALLY_OR_CONTINUATION` | `LOWER_HIGH_REJECTION` |
| 9 | Support decision / failed lower expansion | `near_support` tanpa konfirmasi reclaim/breakdown, atau breakdown gagal accept | `SUPPORT_REACTION_PENDING` | `WAIT_SUPPORT_REACTION_OR_RECLAIM` | `SUPPORT_DECISION_PENDING` / `LOWER_RANGE_FAILED_EXPANSION` |
| 10 | Range mid | tidak ada edge struktural | `RANGE_MID_NO_EDGE` | `NO_TRADE_WAIT_CONTEXT` | `RANGE_MID_NO_EDGE` |

## H4 Semantic Layer

## Pressure Grade Interpretation

`pressure_grade` bukan label arah trade. Ia hanya menjelaskan kualitas pressure block dari sisi durasi, density, dan internal gap.

Interpretasi arah tetap berasal dari `chart_phase`, `action`, `reason_code`, dan gating structure yang dibaca dari snapshot.

Jadi:

- `A+` bisa berarti continuation atau exhaustion
- `A` dan `A-` bisa berarti bullish atau bearish context
- `B+` bisa tetap valid sebagai watchlist pressure tanpa menjadi entry langsung

Di level engine, repo juga membedakan:

- `max_event_gap_seconds = 300` sebagai batas canonical family
- `max_continuity_gap_seconds = 90` sebagai batas continuity block sehat

Akibatnya satu family bisa tetap satu `pressure_series`, tetapi terpecah menjadi beberapa `pressure_blocks` bila continuity internalnya rusak.

## NZDCHF Case Study

Contoh NZDCHF membantu menjelaskan kenapa continuity dan direction tidak boleh dicampur.

Secara historis, run NZDCHF yang kuat menunjukkan pola seperti ini:

- density sehat
- internal max gap kecil, sekitar 27 sampai 33 detik
- grade tinggi (`A+`, `A+`, `A-`) pada pressure run yang rapat

Tetapi arah trade dari run tersebut tidak identik:

- satu run `A+` bisa dibaca sebagai `UPPER_RANGE_EXHAUSTION_RISK`
- run `A+` lain bisa dibaca sebagai `BEARISH_PULLBACK_CONTINUATION`
- run `A-` bisa berakhir sebagai `SUPPORT_REACTION_PENDING` atau context breakdown risk

Artinya:

- `A+` tidak berarti buy otomatis
- `A+` juga tidak berarti sell otomatis
- grade hanya mengatakan pressure-nya sehat
- `chart_phase`, `action`, dan `reason_code` tetap menentukan interpretasi akhirnya

Contoh ini juga menjelaskan kenapa gap besar seperti `264s` tidak layak diperlakukan sebagai satu continuity block sehat, walaupun masih berada di bawah hard family timeout `300s`.

Rule praktisnya:

- `300s` menjaga family besar tetap utuh
- `90s` menjaga kualitas continuity block tetap bersih
- family boleh tetap satu `pressure_series`, tetapi grading harus dihitung dari sub-block yang continuity-nya masih valid

Selain `h4_structure`, classifier sekarang mengembalikan `h4_context_type` untuk membedakan subtype H4 yang dipakai downstream scoring/API:

- `CONTINUATION_TREND`
- `FAILED_BREAKOUT_ACCEPTANCE`
- `FAILED_BREAKDOWN_ACCEPTANCE`
- `TERMINAL_REJECTION`
- `RANGE_EDGE_COMPRESSION`
- `RANGE_OR_TRANSITION`

Mapping saat ini:

- `BULLISH_CONTINUATION` / `BEARISH_CONTINUATION` -> `CONTINUATION_TREND`
- `BULLISH_EXHAUSTION_RISK` + breakout gagal accept -> `FAILED_BREAKOUT_ACCEPTANCE`
- `BEARISH_EXHAUSTION_RISK` + breakdown gagal accept -> `FAILED_BREAKDOWN_ACCEPTANCE`
- exhaustion dengan wick rejection dominan -> `TERMINAL_REJECTION`
- exhaustion dengan kompresi di tepi range -> `RANGE_EDGE_COMPRESSION`
- fase netral -> `RANGE_OR_TRANSITION`

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
- `h4_structure`
- `h4_context_type`
- `primary_scenario`
- `alternative_scenario`
- `no_trade_condition`

`trade_plan_builder` boleh tetap menampilkan satu `action` ringkas untuk dashboard, tetapi payload harus menyimpan seluruh scenario set.
