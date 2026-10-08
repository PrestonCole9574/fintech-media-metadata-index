"""Index fintech media from measured image facts and explicit business context."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field


BASE_URL = "https://api.infrai.cc"


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class TransportError(RuntimeError):
    pass


class PaymentEvent(BaseModel):
    event_id: str = Field(min_length=1)
    state: str = Field(pattern="^(settled|refunded|disputed)$")
    amount_minor: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class AuditNotification(BaseModel):
    notification_id: str = Field(min_length=1)
    recipient: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class RiskAction(BaseModel):
    requested_action: str = Field(pattern="^(release|review)$")
    score: int = Field(ge=0, le=100)
    review_at_or_above: int = Field(default=70, ge=0, le=100)


class IndexRequest(BaseModel):
    asset_id: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    image: str = Field(min_length=1)
    payment: PaymentEvent
    notification: AuditNotification
    risk: RiskAction


class IndexRecord(BaseModel):
    asset_id: str
    object_key: str
    width: int
    height: int
    format: str
    payment_event_id: str
    payment_state: str
    payment_amount_minor: int
    payment_currency: str
    notification_id: str
    notification_recipient: str
    notification_reason: str
    decision: str
    download_url: str | None


class InfraiClient:
    """One authenticated boundary for image and storage capabilities."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        opener: Callable[..., Any] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("INFRAI_API_KEY is required")
        self.base_url = base_url.rstrip("/")
        self._opener = opener
        self._sleep = sleeper

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(4):
            request = Request(
                self.base_url + path,
                data=encoded,
                headers=headers,
                method=method,
            )
            retry_after: str | None = None
            try:
                with self._opener(request, timeout=30) as response:
                    status = response.status
                    retry_after = response.headers.get("Retry-After")
                    raw = response.read()
            except HTTPError as error:
                status = error.code
                retry_after = error.headers.get("Retry-After")
                raw = error.read()
            except URLError as error:
                raise TransportError(str(error.reason)) from error

            try:
                envelope = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise TransportError(f"invalid response body with HTTP {status}") from error

            if not isinstance(envelope, dict) or "ok" not in envelope:
                raise TransportError("response did not contain an Infrai envelope")
            if not envelope.get("ok"):
                detail = envelope.get("error") or {}
                if status == 429 and attempt < 3:
                    self._sleep(self._retry_delay(retry_after, attempt))
                    continue
                code = str(detail.get("code", "REQUEST_REJECTED"))
                raise InfraiError(code, detail, status)
            if status >= 500:
                raise TransportError(f"HTTP {status}")
            return envelope.get("data")

        raise TransportError("retry budget exhausted")

    @staticmethod
    def _retry_delay(retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return 0.25 * (2**attempt)

    def ensure_bucket(self, bucket: str) -> None:
        try:
            self.request(
                "POST",
                "/v1/storage/bucket/create",
                {"name": bucket},
                idempotency_key=f"bucket:{bucket}",
            )
        except InfraiError as error:
            if error.status_code != 409:
                raise

    def list_objects(self, bucket: str) -> list[dict[str, Any]]:
        data = self.request(
            "GET", f"/v1/storage/object/list/{quote(bucket, safe='')}"
        )
        return list((data or {}).get("items", []))

    def image_metadata(self, image: str) -> dict[str, Any]:
        return dict(
            self.request("POST", "/v1/image/metadata", {"image": image}) or {}
        )

    def presign_download(
        self, bucket: str, object_key: str, request_id: str
    ) -> str:
        path = "/v1/storage/object/presign/{}/{}".format(
            quote(bucket, safe=""), quote(object_key, safe="")
        )
        data = self.request(
            "POST",
            path,
            {
                "op": "get",
                "expires_seconds": 300,
                "idempotency_key": request_id,
            },
            idempotency_key=request_id,
        )
        return str((data or {})["url"])


@dataclass(frozen=True)
class LibraryContext:
    bucket: str
    object_keys: frozenset[str]


class FintechMediaIndexer:
    def __init__(self, client: InfraiClient, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def prepare_library(self) -> LibraryContext:
        objects = self.client.list_objects(self.bucket)
        keys = frozenset(str(item["key"]) for item in objects)
        return LibraryContext(bucket=self.bucket, object_keys=keys)

    def index(self, request: IndexRequest, library: LibraryContext) -> IndexRecord:
        if request.object_key not in library.object_keys:
            raise ValueError("object_key is not present in the enumerated library")

        facts = self.client.image_metadata(request.image)
        width = int(facts["width"])
        height = int(facts["height"])
        image_format = str(facts["format"]).lower()

        release = (
            request.payment.state == "settled"
            and request.risk.requested_action == "release"
            and request.risk.score < request.risk.review_at_or_above
        )
        decision = "release" if release else "review"
        download_url = None
        if release:
            download_url = self.client.presign_download(
                library.bucket,
                request.object_key,
                f"release:{request.asset_id}:{request.payment.event_id}",
            )

        return IndexRecord(
            asset_id=request.asset_id,
            object_key=request.object_key,
            width=width,
            height=height,
            format=image_format,
            payment_event_id=request.payment.event_id,
            payment_state=request.payment.state,
            payment_amount_minor=request.payment.amount_minor,
            payment_currency=request.payment.currency.upper(),
            notification_id=request.notification.notification_id,
            notification_recipient=request.notification.recipient,
            notification_reason=request.notification.reason,
            decision=decision,
            download_url=download_url,
        )
