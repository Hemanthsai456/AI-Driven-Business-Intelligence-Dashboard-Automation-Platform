# Orchestrator Multi-Provider Benchmark Evaluation Report

**Total Prompts**: 22  
**Passed**: 20 / 22  
**Overall Accuracy**: 90.9%  
**High-Agreement Wrong Rate**: 10.0% (2/20)

## Agreement & Consensus-Failure Analysis (Q3 Risk)

| Metric | Count | Percentage |
| :--- | :--- | :--- |
| Total Consensus Prompts (Agreement = 1.0) | 20 | 90.9% |
| Consensus on Correct Signature | 18 | 81.8% |
| **Consensus on WRONG Signature** | **2** | **9.1%** |
| **High-Agreement Wrong Rate** | **2/20** | **10.0%** |
| Non-Consensus / Dissenting Providers | 2 | 9.1% |

> [!WARNING]
> **Agreement-on-Wrong-Answer Risk Detected**: In **2** case(s), all 3 providers independently agreed on an incorrect plan signature. High-agreement wrong rate is **10.0%**. Because consensus was 100% (agreement = 1.0), the ranker awarded maximum agreement bonus, crowning the erroneous plan as winner without detection. This validates the Q3 architectural limitation.

## Per-Prompt Evaluation Details

| # | Prompt | Dataset | Category | Agreement | Status | Consensus Analysis | Winning Signature |
| :-: | :--- | :--- | :--- | :-: | :-: | :--- | :--- |
| 1 | Total revenue by product ID | `Sales_2024.csv` | `grouping_dimension` | `1.00` | PASS | Consensus on Correct | `SUM(TotalSales) BY ProductID` |
| 2 | Monthly sales trend for 2024 | `Sales_2024.csv` | `time_granularity` | `1.00` | PASS | Consensus on Correct | `SUM(TotalSales) BY Date:month` |
| 3 | Top customers by total quantity purchased | `Sales_2024.csv` | `grouping_dimension` | `1.00` | PASS | Consensus on Correct | `SUM(Quantity) BY CustomerID` |
| 4 | Average unit price across product categories | `Products.csv` | `grouping_dimension` | `1.00` | PASS | Consensus on Correct | `AVG(UnitPrice) BY Category` |
| 5 | Store count by region | `Stores.csv` | `grouping_dimension` | `1.00` | PASS | Consensus on Correct | `COUNT(StoreID) BY Region` |
| 6 | Store sales performance | `Sales_2024.csv` | `metric_ambiguity` | `0.67` | PASS | Dissenting / Disambiguated | `SUM(TotalSales) BY StoreID` |
| 7 | Customer sales aggregation | `Sales_2024.csv` | `aggregation_ambiguity` | `0.67` | PASS | Dissenting / Disambiguated | `SUM(TotalSales) BY CustomerID` |
| 8 | Quarterly revenue for 2024 | `Sales_2024.csv` | `time_granularity` | `1.00` | PASS | Consensus on Correct | `SUM(TotalSales) BY Date:quarter` |
| 9 | Daily sales volume | `Sales_2024.csv` | `time_granularity` | `1.00` | PASS | Consensus on Correct | `SUM(Quantity) BY Date:day` |
| 10 | Total sales for Store 101 | `Sales_2024.csv` | `filter_scope` | `1.00` | **FAIL** | Consensus on WRONG (Risk Triggered) | `UNANSWERABLE` |
| 11 | Average order value by store | `Sales_2024.csv` | `aggregation_ambiguity` | `1.00` | PASS | Consensus on Correct | `AVG(TotalSales) BY StoreID` |
| 12 | High value sales over 500 dollars | `Sales_2024.csv` | `filter_scope` | `1.00` | PASS | Consensus on Correct | `SUM(TotalSales) WHERE TotalSales > 500` |
| 13 | Sales volume by product in 2025 | `Sales_2025.csv` | `grouping_dimension` | `1.00` | PASS | Consensus on Correct | `SUM(Quantity) BY ProductID` |
| 14 | Customer count by region | `Customers.csv` | `grouping_dimension` | `1.00` | PASS | Consensus on Correct | `COUNT(CustomerID) BY Region` |
| 15 | Customer count by segment | `Customers.csv` | `grouping_dimension` | `1.00` | PASS | Consensus on Correct | `COUNT(CustomerID) BY Segment` |
| 16 | Monthly sales trend for 2025 | `Sales_2025.csv` | `time_granularity` | `1.00` | PASS | Consensus on Correct | `SUM(TotalSales) BY Date:month` |
| 17 | Overall total revenue across entire year | `Sales_2024.csv` | `metric_ambiguity` | `1.00` | PASS | Consensus on Correct | `SUM(TotalSales)` |
| 18 | Product count per category | `Products.csv` | `grouping_dimension` | `1.00` | PASS | Consensus on Correct | `COUNT(ProductID) BY Category` |
| 19 | Customer churn rate and retention probability | `Sales_2024.csv` | `unanswerable` | `1.00` | PASS | Consensus on Correct | `UNANSWERABLE` |
| 20 | Marketing ROI and customer acquisition cost | `Products.csv` | `unanswerable` | `1.00` | PASS | Consensus on Correct | `UNANSWERABLE` |
| 21 | Net profit margin after supplier cost | `Sales_2024.csv` | `unanswerable` | `1.00` | PASS | Consensus on Correct | `UNANSWERABLE` |
| 22 | Show ambiguous store performance metric | `Sales_2024.csv` | `metric_ambiguity` | `1.00` | **FAIL** | Consensus on WRONG (Risk Triggered) | `AVG(UnitPrice) BY StoreID` |
