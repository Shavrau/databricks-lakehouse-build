-- ==============================================================================
-- GOLD CONSUMER-FACING VIEWS (CONTRACT & DYNAMIC PII REDACTION)
-- ==============================================================================

-- 1. Daily Sales View (Pushdown-friendly, explicit columns)
CREATE OR REPLACE VIEW IDENTIFIER(:catalog || '.gold.v_sales_daily')
COMMENT 'Consumer view of daily sales performance by local franchise business date, franchise, and product'
AS
SELECT
  business_date_local,
  franchise_id,
  product,
  transaction_count,
  units_sold,
  gross_sales,
  avg_unit_price,
  distinct_customers
FROM IDENTIFIER(:catalog || '.gold_etl.sales_daily');

-- 2. Customer Sales Summary View (with Dynamic PII Redaction via Unity Catalog)
CREATE OR REPLACE VIEW IDENTIFIER(:catalog || '.gold.v_customer_sales_summary')
COMMENT 'Consumer view of customer lifetime spend with dynamic PII redaction (unmasked for pii-readers)'
AS
SELECT
  customer_id,
  CASE 
    WHEN is_account_group_member('pii-readers') THEN first_name 
    ELSE concat(substring(first_name, 1, 1), '***') 
  END AS first_name,
  CASE 
    WHEN is_account_group_member('pii-readers') THEN last_name 
    ELSE concat(substring(last_name, 1, 1), '***') 
  END AS last_name,
  CASE 
    WHEN is_account_group_member('pii-readers') THEN email_address 
    ELSE regexp_replace(email_address, '^(.)(.*)(@.*)$', '$1***$3') 
  END AS email_address,
  CASE 
    WHEN is_account_group_member('pii-readers') THEN phone_number 
    ELSE concat('***-***-', right(phone_number, 4)) 
  END AS phone_number,
  city,
  state,
  country,
  lifetime_transactions,
  lifetime_spend,
  lifetime_units,
  first_purchase_date,
  last_purchase_date,
  preferred_payment_method
FROM IDENTIFIER(:catalog || '.gold_etl.customer_sales_summary');

-- 3. Franchise Operations Performance View
CREATE OR REPLACE VIEW IDENTIFIER(:catalog || '.gold.v_franchise_performance')
COMMENT 'Consumer view of franchise operational KPIs, revenue, and supplier status'
AS
SELECT
  franchise_id,
  franchise_name,
  city,
  district,
  country,
  franchise_size,
  time_zone,
  primary_supplier_id,
  primary_supplier_name,
  is_supplier_approved,
  total_revenue,
  total_transactions,
  total_units,
  active_days,
  is_franchise_deleted
FROM IDENTIFIER(:catalog || '.gold_etl.franchise_performance');
