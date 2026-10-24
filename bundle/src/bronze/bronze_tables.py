from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(
    name="transactions",
    comment="Raw transactions landed as-is from POS file extracts",
    table_properties={"quality": "bronze", "layer": "bronze", "source": "POS"}
)
def transactions():
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    path = f"/Volumes/{catalog}/landing/extracts/transactions"
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("header", "true")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(path)
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_source_system", F.lit("POS"))
        .withColumn("_schema_version", F.lit("v1.0"))
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn(
            "_batch_ts",
            F.to_timestamp(
                F.regexp_extract(F.col("_metadata.file_path"), r"transactions_(\d{10})\.csv", 1),
                "yyyyMMddHH"
            )
        )
    )

@dp.table(
    name="customers",
    comment="Raw customers landed as-is from CRM snapshots",
    table_properties={"quality": "bronze", "layer": "bronze", "source": "CRM"}
)
def customers():
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    path = f"/Volumes/{catalog}/landing/extracts/customers"
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("header", "true")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(path)
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_source_system", F.lit("CRM"))
        .withColumn("_schema_version", F.lit("v1.0"))
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn(
            "_batch_ts",
            F.to_timestamp(
                F.regexp_extract(F.col("_metadata.file_path"), r"customers_(\d{10})\.csv", 1),
                "yyyyMMddHH"
            )
        )
    )

@dp.table(
    name="franchises",
    comment="Raw franchises reference landed as-is from Franchise Registry",
    table_properties={"quality": "bronze", "layer": "bronze", "source": "FRANCHISE_REGISTRY"}
)
def franchises():
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    path = f"/Volumes/{catalog}/landing/extracts/franchises"
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("header", "true")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(path)
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_source_system", F.lit("FRANCHISE_REGISTRY"))
        .withColumn("_schema_version", F.lit("v1.0"))
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn(
            "_batch_ts",
            F.to_timestamp(
                F.regexp_extract(F.col("_metadata.file_path"), r"franchises_(\d{10})\.csv", 1),
                "yyyyMMddHH"
            )
        )
    )

@dp.table(
    name="suppliers",
    comment="Raw suppliers reference landed as-is from Supplier Registry",
    table_properties={"quality": "bronze", "layer": "bronze", "source": "SUPPLIER_REGISTRY"}
)
def suppliers():
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    path = f"/Volumes/{catalog}/landing/extracts/suppliers"
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("header", "true")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(path)
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_source_system", F.lit("SUPPLIER_REGISTRY"))
        .withColumn("_schema_version", F.lit("v1.0"))
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn(
            "_batch_ts",
            F.to_timestamp(
                F.regexp_extract(F.col("_metadata.file_path"), r"suppliers_(\d{10})\.csv", 1),
                "yyyyMMddHH"
            )
        )
    )

@dp.table(
    name="franchise_time_zones",
    comment="Franchise IANA time zone reference seed mapping franchiseID to timezone",
    table_properties={"quality": "bronze", "layer": "bronze", "source": "REFERENCE_SEED"}
)
def franchise_time_zones():
    catalog = spark.conf.get("bakehouse.catalog", "bakehouse_dev")
    path = f"/Volumes/{catalog}/landing/extracts/time_zones"
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("header", "true")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(path)
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_source_system", F.lit("REFERENCE_SEED"))
        .withColumn("_schema_version", F.lit("v1.0"))
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn(
            "_batch_ts",
            F.to_timestamp(
                F.regexp_extract(F.col("_metadata.file_path"), r"franchise_time_zones_(\d{10})\.csv", 1),
                "yyyyMMddHH"
            )
        )
    )
