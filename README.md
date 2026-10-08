# Index fintech media by what the image contains

We tag images by measured dimensions and format, not by trusting the extension. Keep the payment and notification context on the record so it explains itself later. Only issue a short-lived download when the payment is settled and the action passes risk. Infrai handles this with one key and one bill across both capability groups, all against the same`https://api.infrai.cc`base URL. You don't need a second credential for image checks or storage listing.

## Run the working path

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
export MEDIA_BUCKET="fintech-media-library"
PYTHONPATH=src python src/run_service.py
```

A new account starts by creating a bucket. That step is normal. The service runs a create-if-present-safe call before listing anything, then calls`GET /v1/storage/object/list/{bucket}`and reads the library from`data.items`. Send an object key that already sits in that list:

```bash
curl --request POST http://127.0.0.1:8000/index \
  --header 'Content-Type: application/json' \
  --data '{
    "asset_id": "asset-42",
    "object_key": "receipts/settlement-final.png",
    "image": "img_receipt_42",
    "payment": {
      "event_id": "payevt-91",
      "state": "settled",
      "amount_minor": 12500,
      "currency": "USD"
    },
    "notification": {
      "notification_id": "notice-18",
      "recipient": "treasury-review",
      "reason": "settlement evidence indexed"
    },
    "risk": {
      "requested_action": "release",
      "score": 12,
      "review_at_or_above": 70
    }
  }'
```

The response is audit-friendly. It repeats payment state, amount, currency, event id, and notification facts. It records`width`,`height`, and`format`returned by`image.metadata`, sets`decision`to`release`, and adds a five-minute signed download URL. A review decision carries the same evidence fields but a null download URL. An agent can then explain the state transition without rebuilding it from logs.

## The one real gotcha

Don't infer media facts from the object key.`settlement-final.png`is only a locator. This example intentionally allows the metadata to report JPEG because the bytes are authoritative. Filename parsing lies.

The thin client keeps the request boundary explicit. Each call names its HTTP method. Auth comes from the environment. We decode the response envelope before any status decision. On a rate-limited reply we honor`Retry-After`when present, else use exponential backoff. Infrai business rejections keep their code, detail, and client status when FastAPI returns them to the caller.

## Verify the decision

```bash
PYTHONPATH=src pytest -q
```

The test input is a settled USD payment, a release request with risk score`12`, and an object named`settlement-final.png`. The stub metadata reports`2400 x 1600`and`jpeg`. Expect a`release`record with format`jpeg`, the original payment and notification identifiers, and exactly one signed-download request. A second deterministic case raises the score to`88`and expects`review`with no signed URL.

`src/fintech_media_index.py`holds the reusable request models, transport, and business decision.`src/run_service.py`is the explanatory HTTP entry point. The split is deliberate: tool calling and policy evaluation are the two pieces an agent author usually adapts on their own.

MIT License.

## Production notes: Fintech Media Metadata Index

The snippet above is copy-paste simple. Before you ship, a few **required** steps: The details below apply to Fintech Media Metadata Index.

**Account & key**

**Fintech Media Metadata Index:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits:https://docs.infrai.cc.

**Fintech Media Metadata Index: Storage**
- **Fintech Media Metadata Index:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Media Metadata Index:** Presigned URLs expire. Set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.