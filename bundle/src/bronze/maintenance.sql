-- Off-hours Maintenance for Bronze Tables
BEGIN
  OPTIMIZE IDENTIFIER(:catalog || '.bronze.transactions');
  OPTIMIZE IDENTIFIER(:catalog || '.bronze.customers');
  OPTIMIZE IDENTIFIER(:catalog || '.bronze.franchises');
  OPTIMIZE IDENTIFIER(:catalog || '.bronze.suppliers');
  OPTIMIZE IDENTIFIER(:catalog || '.bronze.franchise_time_zones');

  ANALYZE TABLE IDENTIFIER(:catalog || '.bronze.transactions') COMPUTE STATISTICS FOR ALL COLUMNS;
  ANALYZE TABLE IDENTIFIER(:catalog || '.bronze.customers') COMPUTE STATISTICS FOR ALL COLUMNS;
  ANALYZE TABLE IDENTIFIER(:catalog || '.bronze.franchises') COMPUTE STATISTICS FOR ALL COLUMNS;
  ANALYZE TABLE IDENTIFIER(:catalog || '.bronze.suppliers') COMPUTE STATISTICS FOR ALL COLUMNS;
  ANALYZE TABLE IDENTIFIER(:catalog || '.bronze.franchise_time_zones') COMPUTE STATISTICS FOR ALL COLUMNS;
END;
