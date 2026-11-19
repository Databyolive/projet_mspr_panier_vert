"""Accès au data lake RustFS (API S3) avec boto3."""
import boto3
from botocore.exceptions import ClientError

from panier_vert import settings


def client_s3():
    return boto3.client(
        "s3",
        endpoint_url=settings.RUSTFS_ENDPOINT,
        aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
        aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
    )


def creer_bucket() -> None:
    s3 = client_s3()
    try:
        s3.head_bucket(Bucket=settings.LAKE_BUCKET)
        print(f"Bucket '{settings.LAKE_BUCKET}' déjà présent")
    except ClientError:
        s3.create_bucket(Bucket=settings.LAKE_BUCKET)
        print(f"Bucket '{settings.LAKE_BUCKET}' créé")


def envoyer_dossier(dossier_local, prefixe: str) -> int:
    """Copie tous les fichiers d'un dossier local vers s3://bucket/<prefixe>/ (ex. raw/instacart)."""
    from pathlib import Path

    s3, n = client_s3(), 0
    racine = Path(dossier_local)
    for f in racine.rglob("*"):
        if f.is_file():
            cle = f"{prefixe}/{f.relative_to(racine).as_posix()}"
            s3.upload_file(str(f), settings.LAKE_BUCKET, cle)
            n += 1
    print(f"{n} fichier(s) envoyé(s) vers s3://{settings.LAKE_BUCKET}/{prefixe}")
    return n