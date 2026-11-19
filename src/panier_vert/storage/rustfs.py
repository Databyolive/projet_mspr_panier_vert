
import os
from io import BytesIO
from pathlib import Path

import boto3
import pandas as pd

from dotenv import load_dotenv
from botocore.config import Config
from botocore.exceptions import ClientError


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()


RUSTFS_ENDPOINT = os.getenv(
    "RUSTFS_ENDPOINT",
    "http://localhost:9100"
)

RUSTFS_BUCKET = os.getenv(
    "RUSTFS_BUCKET",
    "panier-vert"
)

RUSTFS_ACCESS_KEY = os.getenv("RUSTFS_ACCESS_KEY")
RUSTFS_SECRET_KEY = os.getenv("RUSTFS_SECRET_KEY")


# ============================================================
# CONNEXION S3 / RUSTFS
# ============================================================

s3 = boto3.client(
    "s3",
    endpoint_url=RUSTFS_ENDPOINT,
    aws_access_key_id=RUSTFS_ACCESS_KEY,
    aws_secret_access_key=RUSTFS_SECRET_KEY,
    region_name="us-east-1",
    config=Config(signature_version="s3v4")
)


# ============================================================
# BUCKET
# ============================================================

def ensure_bucket(bucket=RUSTFS_BUCKET):
    """Vérifie l'existence du bucket et le crée si nécessaire."""

    try:
        s3.head_bucket(Bucket=bucket)
        print(f"Bucket existant : {bucket}")

    except ClientError:
        s3.create_bucket(Bucket=bucket)
        print(f"Bucket créé : {bucket}")


# ============================================================
# UPLOAD FICHIER LOCAL
# ============================================================

def upload_file_to_bronze(
    local_path,
    source,
    filename=None,
    bucket=RUSTFS_BUCKET
):
    """Envoie un fichier local dans la couche Bronze."""

    local_path = Path(local_path)

    if not local_path.exists():
        raise FileNotFoundError(local_path)

    filename = filename or local_path.name

    object_key = f"bronze/{source}/{filename}"

    s3.upload_file(
        str(local_path),
        bucket,
        object_key
    )

    print(f"Fichier envoyé : s3://{bucket}/{object_key}")

    return object_key


# ============================================================
# UPLOAD DATAFRAME EN PARQUET
# ============================================================

def upload_dataframe_to_bronze(
    df,
    source,
    filename,
    bucket=RUSTFS_BUCKET
):
    """Envoie un DataFrame au format Parquet dans Bronze."""

    buffer = BytesIO()

    df.to_parquet(
        buffer,
        engine="pyarrow",
        index=False
    )

    buffer.seek(0)

    object_key = f"bronze/{source}/{filename}"

    s3.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream"
    )

    print(f"DataFrame envoyé : s3://{bucket}/{object_key}")
    print(f"Lignes : {len(df):,}")

    return object_key


# ============================================================
# LISTE DES OBJETS
# ============================================================

def list_bronze_objects(
    prefix="bronze/",
    bucket=RUSTFS_BUCKET
):
    """Liste les fichiers stockés dans Bronze."""

    response = s3.list_objects_v2(
        Bucket=bucket,
        Prefix=prefix
    )

    objects = response.get("Contents", [])

    for obj in objects:
        print(
            f"{obj['Key']} | "
            f"{obj['Size'] / 1024:.2f} Ko"
        )

    return objects
