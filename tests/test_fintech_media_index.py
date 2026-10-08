from fintech_media_index import (
    AuditNotification,
    FintechMediaIndexer,
    IndexRequest,
    LibraryContext,
    PaymentEvent,
    RiskAction,
)


class FakeInfraiClient:
    def __init__(self) -> None:
        self.presign_calls: list[tuple[str, str, str]] = []

    def list_objects(self, bucket: str) -> list[dict[str, object]]:
        assert bucket == "fintech-media-library"
        return [{"key": "receipts/settlement-final.png"}]

    def image_metadata(self, image: str) -> dict[str, object]:
        assert image == "img_receipt_42"
        return {"width": 2400, "height": 1600, "format": "jpeg"}

    def presign_download(self, bucket: str, key: str, request_id: str) -> str:
        self.presign_calls.append((bucket, key, request_id))
        return "https://download.example/signed-receipt"


def make_request(score: int) -> IndexRequest:
    return IndexRequest(
        asset_id="asset-42",
        object_key="receipts/settlement-final.png",
        image="img_receipt_42",
        payment=PaymentEvent(
            event_id="payevt-91",
            state="settled",
            amount_minor=12500,
            currency="USD",
        ),
        notification=AuditNotification(
            notification_id="notice-18",
            recipient="treasury-review",
            reason="settlement evidence indexed",
        ),
        risk=RiskAction(requested_action="release", score=score),
    )


def test_prepare_library_only_enumerates_existing_bucket() -> None:
    client = FakeInfraiClient()
    indexer = FintechMediaIndexer(client, "fintech-media-library")  # type: ignore[arg-type]

    library = indexer.prepare_library()

    assert library == LibraryContext(
        bucket="fintech-media-library",
        object_keys=frozenset({"receipts/settlement-final.png"}),
    )


def test_measured_format_and_low_risk_release_drive_the_record() -> None:
    client = FakeInfraiClient()
    indexer = FintechMediaIndexer(client, "fintech-media-library")  # type: ignore[arg-type]
    library = LibraryContext(
        bucket="fintech-media-library",
        object_keys=frozenset({"receipts/settlement-final.png"}),
    )

    record = indexer.index(make_request(score=12), library)

    assert (record.width, record.height, record.format) == (2400, 1600, "jpeg")
    assert record.decision == "release"
    assert record.payment_event_id == "payevt-91"
    assert (record.payment_amount_minor, record.payment_currency) == (12500, "USD")
    assert record.notification_id == "notice-18"
    assert client.presign_calls == [
        (
            "fintech-media-library",
            "receipts/settlement-final.png",
            "release:asset-42:payevt-91",
        )
    ]


def test_high_risk_asset_stays_in_review_without_a_download() -> None:
    client = FakeInfraiClient()
    indexer = FintechMediaIndexer(client, "fintech-media-library")  # type: ignore[arg-type]
    library = LibraryContext(
        bucket="fintech-media-library",
        object_keys=frozenset({"receipts/settlement-final.png"}),
    )

    record = indexer.index(make_request(score=88), library)

    assert record.decision == "review"
    assert record.download_url is None
    assert client.presign_calls == []
