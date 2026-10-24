from pyspark import pipelines as dp
from pyspark.sql import functions as F

# ==============================================================================
# 1. SALES DAILY AGGREGATIONS (LOCAL BUSINESS DATES & LIQUID CLUSTERING)
# ==============================================================================

catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")

@dp.materialized_view(
    name=f"{catalog}.gold_etl.sales_daily",
    comment="Daily aggregated sales by local business date, franchise, and product",
    table_properties={"quality": "gold", "layer": "gold_etl", "access": "engineering_only"},
    cluster_by=["business_date_local", "franchise_id"]
)
@dp.expect("valid_date", "business_date_local >= '2024-04-30' AND business_date_local <= current_date()")
@dp.expect("non_negative_sales", "gross_sales >= 0 AND units_sold >= 0")
def sales_daily():
    """
    Computes daily aggregates.
    Converts event timestamp (UTC) to each franchise's local business date
    using its IANA time zone, avoiding daylight saving/UTC date boundary skew.
    """
    cat = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    df_tx = spark.read.table(f"{cat}.silver.transactions")
    df_fr = spark.read.table(f"{cat}.silver.franchises")

    df_joined = df_tx.join(df_fr, df_tx.franchise_id == df_fr.franchise_id, "inner")

    return (
        df_joined
        .withColumn(
            "business_date_local",
            F.to_date(F.from_utc_timestamp(df_tx.transaction_ts, df_fr.time_zone))
        )
        .groupBy(
            F.col("business_date_local"),
            df_tx.franchise_id,
            df_tx.product
        )
        .agg(
            F.countDistinct(df_tx.transaction_id).alias("transaction_count"),
            F.sum(df_tx.quantity).cast("int").alias("units_sold"),
            F.round(F.sum(df_tx.total_price), 2).cast("decimal(12,2)").alias("gross_sales"),
            F.round(F.avg(df_tx.unit_price), 2).cast("decimal(10,2)").alias("avg_unit_price"),
            F.countDistinct(df_tx.customer_id).alias("distinct_customers")
        )
    )


# ==============================================================================
# 2. CUSTOMER SALES SUMMARY (CURRENT DIMENSION ATTRIBUTES & METRICS)
# ==============================================================================

@dp.materialized_view(
    name=f"{catalog}.gold_etl.customer_sales_summary",
    comment="Customer spend profile and lifetime transaction metrics",
    table_properties={"quality": "gold", "layer": "gold_etl", "access": "engineering_only"},
    cluster_by=["customer_id"]
)
@dp.expect("valid_customer", "customer_id IS NOT NULL AND lifetime_spend >= 0")
def customer_sales_summary():
    """
    Aggregates lifetime spend, volume, and preferences per customer.
    Joins with current customer record (is_current = true).
    """
    cat = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    df_tx = spark.read.table(f"{cat}.silver.transactions")
    df_cust = spark.read.table(f"{cat}.silver.customers").filter(F.col("is_current") == True)

    df_joined = df_tx.join(df_cust, df_tx.customer_id == df_cust.customer_id, "inner")

    return (
        df_joined
        .groupBy(
            df_tx.customer_id,
            df_cust.first_name,
            df_cust.last_name,
            df_cust.email_address,
            df_cust.phone_number,
            df_cust.city,
            df_cust.state,
            df_cust.country
        )
        .agg(
            F.countDistinct(df_tx.transaction_id).alias("lifetime_transactions"),
            F.round(F.sum(df_tx.total_price), 2).cast("decimal(12,2)").alias("lifetime_spend"),
            F.sum(df_tx.quantity).cast("int").alias("lifetime_units"),
            F.min(F.to_date(df_tx.transaction_ts)).alias("first_purchase_date"),
            F.max(F.to_date(df_tx.transaction_ts)).alias("last_purchase_date"),
            F.mode(df_tx.payment_method).alias("preferred_payment_method")
        )
    )


# ==============================================================================
# 3. FRANCHISE PERFORMANCE (OPERATIONS METRICS & SUPPLIER INTEGRATION)
# ==============================================================================

@dp.materialized_view(
    name=f"{catalog}.gold_etl.franchise_performance",
    comment="Franchise operational KPIs, revenue, and supplier compliance",
    table_properties={"quality": "gold", "layer": "gold_etl", "access": "engineering_only"},
    cluster_by=["franchise_id"]
)
def franchise_performance():
    """
    Combines daily sales with franchise characteristics and supplier status.
    """
    cat = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    df_sales = spark.read.table(f"{cat}.gold_etl.sales_daily")
    df_fr = spark.read.table(f"{cat}.silver.franchises")
    df_su = spark.read.table(f"{cat}.silver.suppliers")

    # Aggregate sales by franchise
    df_sales_agg = (
        df_sales
        .groupBy("franchise_id")
        .agg(
            F.round(F.sum("gross_sales"), 2).cast("decimal(14,2)").alias("total_revenue"),
            F.sum("transaction_count").cast("int").alias("total_transactions"),
            F.sum("units_sold").cast("int").alias("total_units"),
            F.countDistinct("business_date_local").alias("active_days")
        )
    )

    return (
        df_fr
        .join(df_sales_agg, df_fr.franchise_id == df_sales_agg.franchise_id, "left")
        .join(df_su, df_fr.supplier_id == df_su.supplier_id, "left")
        .select(
            df_fr.franchise_id,
            df_fr.name.alias("franchise_name"),
            df_fr.city,
            df_fr.district,
            df_fr.country,
            df_fr.size.alias("franchise_size"),
            df_fr.time_zone,
            df_fr.supplier_id.alias("primary_supplier_id"),
            df_su.name.alias("primary_supplier_name"),
            df_su.is_approved.alias("is_supplier_approved"),
            F.coalesce(df_sales_agg.total_revenue, F.lit(0.0).cast("decimal(14,2)")).alias("total_revenue"),
            F.coalesce(df_sales_agg.total_transactions, F.lit(0)).alias("total_transactions"),
            F.coalesce(df_sales_agg.total_units, F.lit(0)).alias("total_units"),
            F.coalesce(df_sales_agg.active_days, F.lit(0)).alias("active_days"),
            df_fr.is_deleted.alias("is_franchise_deleted")
        )
    )
