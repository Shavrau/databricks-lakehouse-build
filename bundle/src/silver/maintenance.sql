-- Off-hours Maintenance for Silver Streaming Tables
BEGIN
  OPTIMIZE IDENTIFIER(:catalog || '.silver.transactions');
  OPTIMIZE IDENTIFIER(:catalog || '.silver.customers_scd2');

  ANALYZE TABLE IDENTIFIER(:catalog || '.silver.transactions') COMPUTE STATISTICS FOR ALL COLUMNS;
  ANALYZE TABLE IDENTIFIER(:catalog || '.silver.customers_scd2') COMPUTE STATISTICS FOR ALL COLUMNS;
END;
