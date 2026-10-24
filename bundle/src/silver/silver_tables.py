from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# ==============================================================================
# 1. TRANSACTIONS FACT TABLE (CLEANSED, CONFORMED, DEDUPLICATED VIA AUTO CDC)
# ==============================================================================

@dp.temporary_view(name="conformed_bronze_transactions")
def conformed_bronze_transactions():
    """
    Transforms Bronze transactions:
    - Renames to snake_case standard (transaction_id, customer_id, franchise_id, transaction_ts)
    - Casts monetary columns to DECIMAL(10,2) (authoritative, never silently recomputed)
    - Normalizes payment_method to lowercase
    - Minimizes personal payment data: tokenizes cardNumber to last four digits and drops raw number
    - Derives transaction_date_utc for daily partitioning/clustering
    """
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    return (
        spark.readStream.table(f"{catalog}.bronze.transactions")
        .select(
            F.col("transactionID").cast("int").alias("transaction_id"),
            F.col("customerID").cast("int").alias("customer_id"),
            F.col("franchiseID").cast("int").alias("franchise_id"),
            F.col("dateTime").cast("timestamp").alias("transaction_ts"),
            F.to_date(F.col("dateTime")).alias("transaction_date_utc"),
            F.col("product"),
            F.col("quantity").cast("int").alias("quantity"),
            F.col("unitPrice").cast("decimal(10,2)").alias("unit_price"),
            F.col("totalPrice").cast("decimal(10,2)").alias("total_price"),
            F.lower(F.trim(F.col("paymentMethod"))).alias("payment_method"),
            F.substring(F.col("cardNumber").cast("string"), -4, 4).alias("payment_card_last_four"),
            F.col("_source_file"),
            F.col("_source_system"),
            F.col("_schema_version"),
            F.col("_ingested_at"),
            F.col("_batch_ts")
        )
    )

catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")

dp.create_streaming_table(
    name=f"{catalog}.silver.transactions",
    comment="Cleansed and deduplicated transactions fact table clustered on date and franchise",
    table_properties={"quality": "silver", "layer": "silver", "source": "POS"},
    cluster_by=["transaction_date_utc", "franchise_id"],
    expect_all={
        "valid_keys": "transaction_id IS NOT NULL AND customer_id IS NOT NULL AND franchise_id IS NOT NULL",
        "valid_prices": "unit_price > 0 AND total_price >= unit_price"
    }
)

dp.create_auto_cdc_flow(
    target=f"{catalog}.silver.transactions",
    source="conformed_bronze_transactions",
    keys=["transaction_id"],
    sequence_by="transaction_ts",
    stored_as_scd_type=1
)


# ==============================================================================
# 2. CUSTOMERS DIMENSION (SCD TYPE 2 HISTORIZATION VIA AUTO CDC)
# ==============================================================================

@dp.temporary_view(name="conformed_bronze_customers")
def conformed_bronze_customers():
    """
    Transforms Bronze customers:
    - Renames to snake_case standard (customer_id, postal_zip_code)
    - Conforms postal_zip_code to STRING to accommodate alphanumeric codes
    - Passes tracked attributes for SCD Type 2 change detection
    """
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    return (
        spark.readStream.table(f"{catalog}.bronze.customers")
        .select(
            F.col("customerID").cast("int").alias("customer_id"),
            F.col("first_name"),
            F.col("last_name"),
            F.col("email_address"),
            F.col("phone_number"),
            F.col("address"),
            F.col("city"),
            F.col("state"),
            F.col("country"),
            F.col("continent"),
            F.col("postal_zip_code").cast("string").alias("postal_zip_code"),
            F.col("gender"),
            F.col("_source_file"),
            F.col("_source_system"),
            F.col("_schema_version"),
            F.col("_ingested_at"),
            F.col("_batch_ts")
        )
    )

dp.create_streaming_table(
    name=f"{catalog}.silver.customers_scd2",
    comment="Internal SCD Type 2 customer history table managed by Lakeflow Auto CDC",
    table_properties={"quality": "silver_internal", "layer": "silver", "source": "CRM"},
    cluster_by=["customer_id"]
)

dp.create_auto_cdc_flow(
    target=f"{catalog}.silver.customers_scd2",
    source="conformed_bronze_customers",
    keys=["customer_id"],
    sequence_by="_batch_ts",
    stored_as_scd_type=2,
    track_history_column_list=[
        "email_address", "phone_number", "address", "city", 
        "state", "country", "postal_zip_code"
    ]
)

@dp.materialized_view(
    name=f"{catalog}.silver.customers",
    comment="Cleansed customer dimension with SCD Type 2 history conforming to foundation time semantics",
    table_properties={"quality": "silver", "layer": "silver", "source": "CRM"},
    cluster_by=["customer_id"]
)
def customers():
    """
    Conforms the SCD Type 2 system columns (__START_AT, __END_AT) into the standardized
    foundation columns: effective_from_ts, effective_to_ts, and is_current.
    """
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    return (
        spark.read.table(f"{catalog}.silver.customers_scd2")
        .select(
            F.col("customer_id"),
            F.col("first_name"),
            F.col("last_name"),
            F.col("email_address"),
            F.col("phone_number"),
            F.col("address"),
            F.col("city"),
            F.col("state"),
            F.col("country"),
            F.col("continent"),
            F.col("postal_zip_code"),
            F.col("gender"),
            F.col("__START_AT").alias("effective_from_ts"),
            F.col("__END_AT").alias("effective_to_ts"),
            F.col("__END_AT").isNull().alias("is_current"),
            F.col("_source_file"),
            F.col("_source_system"),
            F.col("_schema_version"),
            F.col("_ingested_at")
        )
    )


# ==============================================================================
# 3. FRANCHISES DIMENSION (TIME ZONE ENRICHMENT & SOFT DELETE TRACKING)
# ==============================================================================

@dp.materialized_view(
    name=f"{catalog}.silver.franchises",
    comment="Cleansed franchises dimension enriched with IANA time zone and soft-delete tracking",
    table_properties={"quality": "silver", "layer": "silver", "source": "FRANCHISE_REGISTRY"},
    cluster_by=["franchise_id"]
)
def franchises():
    """
    Transforms Bronze franchises:
    - Renames to snake_case standard (franchise_id, supplier_id)
    - Enriches with IANA time zone from franchise_time_zones seed
    - Detects deletions across snapshots: if missing from latest batch, is_deleted = TRUE
    """
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    df_raw = spark.read.table(f"{catalog}.bronze.franchises")
    df_tz = spark.read.table(f"{catalog}.bronze.franchise_time_zones")

    # Find the maximum batch timestamp across all loaded snapshots
    df_max_batch = df_raw.select(F.max(F.col("_batch_ts")).alias("current_batch_ts"))

    # Rank records to pick the latest version and detect missing records
    w_fran = Window.partitionBy("franchiseID").orderBy(F.col("_batch_ts").desc())
    w_fran_all = Window.partitionBy("franchiseID")

    df_ranked = (
        df_raw
        .withColumn("rn", F.row_number().over(w_fran))
        .withColumn("franchise_last_batch_ts", F.max(F.col("_batch_ts")).over(w_fran_all))
        .filter(F.col("rn") == 1)
    )

    return (
        df_ranked.crossJoin(df_max_batch)
        .join(df_tz, df_ranked.franchiseID == df_tz.franchise_id, "left")
        .select(
            F.col("franchiseID").cast("int").alias("franchise_id"),
            F.col("name"),
            F.col("city"),
            F.col("district"),
            F.col("zipcode"),
            F.col("country"),
            F.col("size"),
            F.col("longitude").cast("double").alias("longitude"),
            F.col("latitude").cast("double").alias("latitude"),
            F.col("supplierID").cast("int").alias("supplier_id"),
            F.coalesce(df_tz.time_zone, F.lit("UTC")).alias("time_zone"),
            (F.col("franchise_last_batch_ts") < F.col("current_batch_ts")).alias("is_deleted"),
            F.when(
                F.col("franchise_last_batch_ts") < F.col("current_batch_ts"),
                F.col("current_batch_ts")
            ).otherwise(F.col("franchise_last_batch_ts")).alias("_changed_at"),
            df_ranked["_source_file"],
            df_ranked["_source_system"],
            df_ranked["_schema_version"],
            df_ranked["_ingested_at"]
        )
    )


# ==============================================================================
# 4. SUPPLIERS DIMENSION (FLAG CONVERSION & SOFT DELETE TRACKING)
# ==============================================================================

@dp.materialized_view(
    name=f"{catalog}.silver.suppliers",
    comment="Cleansed suppliers dimension with boolean approval flag and soft-delete tracking",
    table_properties={"quality": "silver", "layer": "silver", "source": "SUPPLIER_REGISTRY"},
    cluster_by=["supplier_id"]
)
def suppliers():
    """
    Transforms Bronze suppliers:
    - Renames to snake_case standard (supplier_id)
    - Converts approved flag ('Y'/'N') to boolean is_approved
    - Tracks soft deletes across snapshots: is_deleted = TRUE if missing from latest batch
    """
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    df_raw = spark.read.table(f"{catalog}.bronze.suppliers")

    # Find the maximum batch timestamp across all loaded snapshots
    df_max_batch = df_raw.select(F.max(F.col("_batch_ts")).alias("current_batch_ts"))

    w_supp = Window.partitionBy("supplierID").orderBy(F.col("_batch_ts").desc())
    w_supp_all = Window.partitionBy("supplierID")

    df_ranked = (
        df_raw
        .withColumn("rn", F.row_number().over(w_supp))
        .withColumn("supplier_last_batch_ts", F.max(F.col("_batch_ts")).over(w_supp_all))
        .filter(F.col("rn") == 1)
    )

    return (
        df_ranked.crossJoin(df_max_batch)
        .select(
            F.col("supplierID").cast("int").alias("supplier_id"),
            F.col("name"),
            F.col("ingredient"),
            F.col("continent"),
            F.col("city"),
            F.col("district"),
            F.col("size"),
            F.col("longitude").cast("double").alias("longitude"),
            F.col("latitude").cast("double").alias("latitude"),
            (F.upper(F.trim(F.col("approved"))) == "Y").alias("is_approved"),
            (F.col("supplier_last_batch_ts") < F.col("current_batch_ts")).alias("is_deleted"),
            F.when(
                F.col("supplier_last_batch_ts") < F.col("current_batch_ts"),
                F.col("current_batch_ts")
            ).otherwise(F.col("supplier_last_batch_ts")).alias("_changed_at"),
            df_ranked["_source_file"],
            df_ranked["_source_system"],
            df_ranked["_schema_version"],
            df_ranked["_ingested_at"]
        )
    )
