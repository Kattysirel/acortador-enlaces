import os
import uuid
from datetime import datetime, timezone

import boto3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

TABLE_NAME = os.environ.get("TABLE_NAME", "short_links")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)

app = FastAPI(title="Acortador de enlaces")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ShortenRequest(BaseModel):
    original_url: HttpUrl


@app.post("/shorten")
def shorten(body: ShortenRequest):
    short_code = str(uuid.uuid4())
    item = {
        "short_code": short_code,
        "original_url": str(body.original_url),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    table.put_item(Item=item)
    return {
        "short_code": short_code,
        "original_url": item["original_url"],
        "short_url": f"{PUBLIC_BASE_URL}/{short_code}",
    }


@app.get("/urls/{short_code}")
def get_url_info(short_code: str):
    item = table.get_item(Key={"short_code": short_code}).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")
    return item


@app.get("/{short_code}")
def redirect(short_code: str):
    item = table.get_item(Key={"short_code": short_code}).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")
    return RedirectResponse(url=item["original_url"], status_code=307)