-- ==============================================================================
-- BUSINESS RULE QUALITY CHECKS (FOUR RULE FAMILIES LOGGED ATOMICALLY)
-- ==============================================================================

INSERT INTO IDENTIFIER(:catalog || '.gold_etl.quality_results')
-- Rule 1: Counts - Transaction Count Reconciliation
SELECT
  current_timestamp() AS run_timestamp,
  'Counts' AS rule_family,
  'transaction_count_reconciliation' AS rule_name,
  concat('Gold: ', cast(g.cnt as string), ', Silver: ', cast(s.cnt as string)) AS observed_value,
  'Gold transaction_count == Silver distinct transaction_id count' AS expected_condition,
  CASE WHEN g.cnt = s.cnt THEN 'PASS' ELSE 'FAIL' END AS status,
  'Reconciles total sold transactions between Silver fact and Gold daily aggregates' AS details
FROM 
  (SELECT coalesce(sum(transaction_count), 0) AS cnt FROM IDENTIFIER(:catalog || '.gold_etl.sales_daily')) g
CROSS JOIN
  (SELECT count(distinct transaction_id) AS cnt FROM IDENTIFIER(:catalog || '.silver.transactions')) s

UNION ALL

-- Rule 2: Sums - Non-Negative Revenue & Gross Sales Reconciliation
SELECT
  current_timestamp() AS run_timestamp,
  'Sums' AS rule_family,
  'revenue_non_negative_and_reconciled' AS rule_name,
  concat('Min Sales: ', cast(g.min_s as string), ', Gold Rev: ', cast(g.sum_rev as string), ', Silver Rev: ', cast(s.sum_rev as string)) AS observed_value,
  'MIN(gross_sales) >= 0 AND Gold SUM(gross_sales) == Silver SUM(total_price)' AS expected_condition,
  CASE WHEN g.min_s >= 0 AND abs(g.sum_rev - s.sum_rev) < 0.01 THEN 'PASS' ELSE 'FAIL' END AS status,
  'Guarantees revenue validity and financial consistency across medallion layers' AS details
FROM 
  (SELECT coalesce(min(gross_sales), 0) AS min_s, coalesce(sum(gross_sales), 0) AS sum_rev FROM IDENTIFIER(:catalog || '.gold_etl.sales_daily')) g
CROSS JOIN
  (SELECT coalesce(sum(total_price), 0) AS sum_rev FROM IDENTIFIER(:catalog || '.silver.transactions')) s

UNION ALL

-- Rule 3: Distinct Growth - Franchise Key Integrity
SELECT
  current_timestamp() AS run_timestamp,
  'Distinct Growth' AS rule_family,
  'franchise_cardinality_integrity' AS rule_name,
  concat('Active Gold Franchises: ', cast(g.cnt as string), ', Total Registered: ', cast(s.cnt as string)) AS observed_value,
  'Gold active franchises <= Silver registered franchises AND > 0' AS expected_condition,
  CASE WHEN g.cnt <= s.cnt AND g.cnt > 0 THEN 'PASS' ELSE 'FAIL' END AS status,
  'Guarantees that joins have not exploded entity keys and active franchises are within bounds' AS details
FROM 
  (SELECT count(distinct franchise_id) AS cnt FROM IDENTIFIER(:catalog || '.gold_etl.sales_daily')) g
CROSS JOIN
  (SELECT count(distinct franchise_id) AS cnt FROM IDENTIFIER(:catalog || '.silver.franchises')) s

UNION ALL

-- Rule 4: Date Bounds - Operating Window Validity
SELECT
  current_timestamp() AS run_timestamp,
  'Date Bounds' AS rule_family,
  'local_business_date_boundaries' AS rule_name,
  concat('Min Date: ', cast(min_d as string), ', Max Date: ', cast(max_d as string)) AS observed_value,
  'MIN(date) >= 2024-04-30 AND MAX(date) <= CURRENT_DATE()' AS expected_condition,
  CASE WHEN min_d >= '2024-04-30' AND max_d <= current_date() THEN 'PASS' ELSE 'FAIL' END AS status,
  'Ensures no transactions with invalid timestamps, ancient history, or future dates (accounting for UTC-10 local store operating dates)' AS details
FROM 
  (SELECT min(business_date_local) AS min_d, max(business_date_local) AS max_d FROM IDENTIFIER(:catalog || '.gold_etl.sales_daily'));
