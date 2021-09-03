# Databricks notebook source
from pyspark.sql.types import *
from delta.tables import *
from pyspark.sql.utils import AnalysisException
from pyspark.sql.functions import col
import pyspark.sql.functions as f
from pyspark.sql.functions import *
from pyspark.sql.types import *


# COMMAND ----------

# DBTITLE 1,Define Schema for Covid-19 Data for Belgium (https://epistat.sciensano.be/covid)
customSchema = StructType([     
    StructField("PROVINCE", StringType(), True),
    StructField("REGION", StringType(), True),
    StructField("AGEGROUP", StringType(), True),
    StructField("SEX", StringType(), True),
    StructField("CASES", DoubleType(), True)
])

# COMMAND ----------

configs = {"fs.azure.account.auth.type": "OAuth",
          "fs.azure.account.oauth.provider.type": "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider",
          "fs.azure.account.oauth2.client.id": "9f00cf9c-be8f-4763-9122-184ac7d8fd86",
          "fs.azure.account.oauth2.client.secret": "_V13fxqLpffKv5o3_un_31GVyFtt35A_7a",
          "fs.azure.account.oauth2.client.endpoint": "https://login.microsoftonline.com/6d37034b-3c0b-46b0-a541-2c09f979ed46/oauth2/token"}



# COMMAND ----------

# Optionally, you can add <directory-name> to the source URI of your mount point.
dbutils.fs.mount(source = "abfss://landing@demo343.dfs.core.windows.net/", mount_point = "/mnt/lnd", extra_configs = configs)
dbutils.fs.mount(source = "abfss://checkpoint@demo343.dfs.core.windows.net/", mount_point = "/mnt/chk", extra_configs = configs)
dbutils.fs.mount(source = "abfss://autostream@demo343.dfs.core.windows.net/", mount_point = "/mnt/strem", extra_configs = configs)

# COMMAND ----------

spark.conf.set("fs.azure.account.auth.type.demo343.dfs.core.windows.net", "OAuth")
spark.conf.set("fs.azure.account.oauth.provider.type.demo343.dfs.core.windows.net", "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider")
spark.conf.set("fs.azure.account.oauth2.client.id.demo343.dfs.core.windows.net", "9f00cf9c-be8f-4763-9122-184ac7d8fd86")
spark.conf.set("fs.azure.account.oauth2.client.secret.demo343.dfs.core.windows.net", "_V13fxqLpffKv5o3_un_31GVyFtt35A_7a")
spark.conf.set("fs.azure.account.oauth2.client.endpoint.demo343.dfs.core.windows.net", "https://login.microsoftonline.com/6d37034b-3c0b-46b0-a541-2c09f979ed46/oauth2/token")

# COMMAND ----------

queuesas = "BlobEndpoint=https://demo343.blob.core.windows.net/;QueueEndpoint=https://demo343.queue.core.windows.net/;FileEndpoint=https://demo343.file.core.windows.net/;TableEndpoint=https://demo343.table.core.windows.net/;SharedAccessSignature=sv=2020-08-04&ss=q&srt=sco&sp=rwdlacup&se=2021-07-29T17:15:57Z&st=2021-07-29T09:15:57Z&spr=https,http&sig=J52BQv5Q97Lwi1sGLzxMu3%2BQ9QWEGjjtO2EMTx%2FBdow%3D"

# COMMAND ----------

# Read JSON file into dataframe
df = spark.read.json("abfss://landingz@demo343.dfs.core.windows.net/2021-21-08")
df.printSchema()
df.show()

# COMMAND ----------

flightsdf= df.select(explode("flights").alias("flightdetails"))
flightsdf.printSchema()
flightsdf.show()

# COMMAND ----------

flight= flightsdf.select(col("flightdetails.aircraftRegistration").alias("aircraftRegistration"),col("flightdetails.airlineCode").alias("airlineCode"),col("flightdetails.flightName").alias("flightName"),col("flightdetails.flightNumber").alias("flightNumber"),explode("flightdetails.route.destinations").alias("destinations"),col("flightdetails.route.eu").alias("eu"),col("flightdetails.route.visa").alias("visa"))
flight.printSchema()
flight.show()

# COMMAND ----------

# DBTITLE 1,Configuration
df = spark.readStream.format("cloudFiles")\
          .option("cloudFiles.format", "json")\
          .option("cloudFiles.connectionString", queuesas)\
          .option("cloudFiles.resourceGroup", "demorg")\
          .option("cloudFiles.subscriptionId", "ac90002c-698e-4529-95d3-48e20a731732")\
          .option("cloudFiles.tenantId", "6d37034b-3c0b-46b0-a541-2c09f979ed46")\
          .option("cloudFiles.clientId", "9f00cf9c-be8f-4763-9122-184ac7d8fd86")\
          .option("cloudFiles.clientSecret", "_V13fxqLpffKv5o3_un_31GVyFtt35A_7a")\
          .option("cloudFiles.validateOptions", "false")\
          .option("cloudFiles.schemaLocation", "abfss://schema@demo343.dfs.core.windows.net/") \
          .option("checkpointLocation", "abfss://checkpoint@demo343.dfs.core.windows.net/") \
          .load("abfss://landingz@demo343.dfs.core.windows.net/")

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE covid_data
# MAGIC    ( PROVINCE STRING,
# MAGIC    REGION STRING,
# MAGIC    AGEGROUP STRING,
# MAGIC    SEX STRING,
# MAGIC    CASES DOUBLE)
# MAGIC   USING DELTA
# MAGIC   LOCATION 'abfss://bronze@demo343.dfs.core.windows.net/'

# COMMAND ----------

# DBTITLE 1,Function for deduplication of data
def upsert_data(df, epochId):
    deltaTable = DeltaTable.forPath(spark, "abfss://bronze@demo343.dfs.core.windows.net/")
    deltaTable.alias("data").merge(
      df.alias("newData"),
      "data.PROVINCE = newData.PROVINCE and data.AGEGROUP = newData.AGEGROUP and data.SEX = newData.SEX") \
    .whenNotMatchedInsertAll() \
    .execute()  

# COMMAND ----------

# DBTITLE 1,Load data incrementally as it lands on the storage
df.writeStream\
  .format("delta")\
  .trigger(once=True)\
  .foreachBatch(upsert_data)\
  .option("checkpointLocation", "abfss://checkpoint@demo343.dfs.core.windows.net/")\
  .start("abfss://bronze@demo343.dfs.core.windows.net/")

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT count(*) FROM covid_data 

# COMMAND ----------

# DBTITLE 1,Display data
# MAGIC %sql
# MAGIC SELECT * FROM covid_data where PROVINCE = 'Antwerpen'  and AGEGROUP = '40-49' order by CASES

# COMMAND ----------

# MAGIC %sql drop table covid_data
