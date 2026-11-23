# Data sources

Every number in `data/` comes from a public source and can be traced to it. Nothing is estimated or filled in.

## IPAI: real-estate asset price index (`data/ipai/`)

Published quarterly by Bank Al-Maghrib (BAM) and the national land registry agency (ANCFCC).

| File | Content |
|---|---|
| `ipai_official_rates_2020Q1_2026Q2.csv` | Officially published % changes (QoQ and YoY) in prices and transaction counts, for Global, Residential, Land and Commercial property, 2020Q1-2026Q2 (26 bulletins) |
| `ipai_transaction_counts_national_2015Q1_2026Q2.csv` | National transaction counts measured from the bulletin charts by the extraction pipeline; `value_source` says whether the value is the first published one or a later revision |

Method choices:
- Only official published rates are used. Rebuilding an absolute index level by chaining quarterly rates was tested and rejected, because BAM revises past values in every bulletin and the chained series drifts from the published YoY figures.
- The Q4-2023 bulletin is printed as No. 54 instead of No. 57. This is a typo in the source document, not an extraction error.
- From 2025Q1 the index covers 83 land registries (a wider perimeter). Year-on-year comparisons across that break are less reliable.

## Bank credit to real estate (`data/external/bam_real_estate_credit_*.csv`)

Source: BAM quarterly bulletins, Table I-4, *Breakdown of bank credit by economic purpose and institutional sector*, page 12. Outstanding amounts in MAD million, monthly.

| Bulletin | Months covered | URL |
|---|---|---|
| December 2019 | Dec 2018 - Dec 2019 | https://www.bkam.ma/content/download/692229/7968153/BT-DEC2019-14022020.pdf |
| December 2020 | Dec 2019 - Dec 2020 | https://www.bkam.ma/content/download/724946/8305152/Bulletin%20trimestriel%20T4%202020.pdf |
| December 2021 | Dec 2020 - Dec 2021 | https://www.bkam.ma/content/download/753800/8518396/Bulletin%20trimestriel%20%20T4-2021.pdf |
| December 2022 | Dec 2021 - Dec 2022 | https://www.bkam.ma/content/download/779190/8694301/Bulletin%20trimestriel%20T4%202022.pdf |
| December 2023 | Dec 2022 - Dec 2023 | https://www.bkam.ma/content/download/800501/8840205/DSGD-BulletinTrimestriel-T4-2023.pdf |
| December 2024 | Dec 2023 - Dec 2024 | https://www.bkam.ma/content/download/820100/8975828/Bulletin%20trimestriel%20T4%202024.pdf |
| December 2025 | Dec 2024 - Dec 2025 | https://www.bkam.ma/content/download/839758/9110367/BT%20T4%202025.pdf |
| June 2026 | Jun 2025 - Jun 2026 | https://www.bkam.ma/content/download/849358/9175364/BT%20T2%202026.pdf |

Three rows are used: *real-estate credit* (total), *housing loans* (including Islamic home finance) and *loans to property developers*.

- `bam_real_estate_credit_all_vintages.csv` keeps every published value. Months that appear in two bulletins differ only by BAM's own revisions (at most 2.1%, on loans to developers). A test checks this.
- `bam_real_estate_credit_monthly.csv` keeps the latest published value for each month. This is the file the analysis uses.

## Cement deliveries (`data/external/cement_deliveries_cumulative.csv`)

Source: deliveries by members of the cement producers' association (APC: Asment Temara, Ciments de l'Atlas, Ciments du Maroc, LafargeHolcim Maroc and, since January 2024, Novacim). The housing ministry publishes them each month, and they are relayed by the national press and CemNet. Values are year-to-date cumulative tonnes at each quarter end, 2019Q1-2026Q3.

- Every row has its source URL. `precision = exact` means the article gives the tonnage to the tonne; `rounded` means it gives millions of tonnes to two or three decimals (9 of 31 rows).
- When a later release revised a figure, the revised value is used and the note says so.
- Quarterly volumes are differences of the cumulative figures, so each year's quarters add up exactly to the annual total (checked by a test).
- Novacim joined the APC panel in January 2024. The published 2024 growth rates (+9.45% for the year) equal the ratio of the published levels, so 2024 growth may partly reflect the larger panel rather than more construction. Read 2024 cement growth with that in mind.

## Reference workbook (`data/ipai/IPAI_quarterly_series.xlsx`)

The workbook in the format the pipeline writes (20 sheets plus Diagnostics). Price and transaction % changes for 2020Q1-2026Q2 come from the official rates above. Transaction counts and city sheets come from an earlier pipeline run, where values a bulletin did not cover were filled from later bulletins and labelled `revised (read in Qx-yyyy)`. Running the pipeline on the 26 bulletin PDFs (`python run_pipeline.py run --rebuild`) regenerates it from scratch. The dashboards in `outputs/dashboards/` are built from this workbook.
