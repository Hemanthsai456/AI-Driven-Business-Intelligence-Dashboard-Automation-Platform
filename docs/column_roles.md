# Column Semantic Roles Specification

This document defines the semantic roles assigned to dataset columns within the **AI-Driven Business Intelligence & Dashboard Automation Platform**.

## Overview

In analytical systems and automated dashboard generation, data types alone (e.g., `integer`, `float`, `string`, `datetime`) are insufficient to determine how a column should be used. Semantic roles explicitly define the analytical function a column serves.

> **Important:** Datatype and semantic role are fundamentally different concepts.  
> For example, a numeric column containing `customer_id` (e.g., `100452`) has an integer data type, but its semantic role is **IDENTIFIER**, not **MEASURE**, because summing or averaging customer IDs is mathematically meaningless.

---

## Semantic Role Definitions

### 1. MEASURE
A field whose values represent quantities that can meaningfully participate in numerical aggregation or statistical analysis.

- **Characteristics:** Numerical, quantitative, aggregatable via functions like `SUM`, `AVG`, `MIN`, `MAX`, `STDDEV`.
- **Examples:** `revenue`, `units_sold`, `profit_margin`, `temperature`, `response_time_ms`.

### 2. DIMENSION
A field used to categorize, group, filter, or segment records.

- **Characteristics:** Categorical, qualitative, discrete text, status codes, boolean flags, or hierarchical groups.
- **Examples:** `region`, `product_category`, `customer_segment`, `order_status`, `is_active`.

### 3. DATETIME
A field representing a date or timestamp that can support temporal analysis.

- **Characteristics:** Expresses time points or temporal intervals; supports time-series aggregation (by day, month, quarter, year), trend analysis, and time-based filtering.
- **Examples:** `created_at`, `transaction_date`, `shipment_timestamp`, `dob`.

### 4. IDENTIFIER
A field primarily used to identify records or entities rather than represent an analytical quantity.

- **Characteristics:** Unique or pseudo-unique keys, foreign keys, surrogate keys, system UUIDs, or record IDs.
- **Examples:** `order_id`, `customer_id`, `sku_code`, `transaction_hash`, `user_guid`.

### 5. UNKNOWN
A field whose semantic role cannot yet be reliably determined.

- **Characteristics:** Unclassified column prior to semantic profiling or user specification; default initial state during raw ingestion before profiling and role inference are executed.
- **Examples:** Newly imported columns with mixed, ambiguous, or un-analyzed contents.
