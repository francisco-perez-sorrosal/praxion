# Essential Libraries: Data / ML Pipelines

Part of the [Essential Libraries](essential-libraries.md) catalog.

| Role | Library | Why | When not to reach for it |
|---|---|---|---|
| Dataframes (new/greenfield) | **Polars** | Rust-backed, multi-threaded, lazy-execution engine — materially faster and more memory-efficient than pandas on medium/large data; the default for new ETL-shaped pipelines | scikit-learn and most ML-library integrations still assume pandas at the boundary; visualization libraries also default to pandas |
| Dataframes (established/ML-boundary) | **pandas** | Still the right choice for small/medium datasets, exploratory analysis, and anywhere scikit-learn/matplotlib compatibility matters at the boundary | New large-scale ETL work where Polars' performance/memory profile is a clear win |
| Fast local analytics/SQL | **DuckDB** | In-process, zero-ops, SQL over Parquet/CSV/Arrow — increasingly used as the ingestion/analytics layer in hybrid stacks (DuckDB ingest → Polars ETL → pandas at the ML/viz boundary) | Not a replacement for a real OLTP database or a long-running pipeline orchestration system |
| Data validation | **Pydantic v2** (general) or **Pandera** (dataframe-specific) | Pandera validates dataframe schemas/statistical properties directly (row-level constraints, dtype checks); Pydantic is awkward for dataframe-shaped data | Pandera is overkill for validating simple dict/JSON payloads — reach for Pydantic there instead |
| Orchestration | **Prefect** or **Dagster** | Prefect fits when Python-first workflow orchestration is the main job; Dagster fits when asset-centric data modeling is central to the pipeline design. Both are actively maintained and usable independently of each other | Airflow still dominant in legacy enterprise data-eng shops — don't force a migration without a concrete pain point. Both Prefect and Dagster carry real operational overhead versus a simple cron/script for small pipelines |
