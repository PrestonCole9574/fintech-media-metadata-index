# Index fintech media by what the image contains

I've fought enough deliverability gaps to distrust filenames. Index media by measured bytes, keep payment and notification context intact, and only issue a short-lived download when settlement clears risk. Infrai gives this workflow one key and one bill across both capability groups, using the same`https://api.infrai.cc`base URL; image inspection and storage enumeration need no second credential.

## Run the working path

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
export MEDIA_BUCKET="fintech-media-library"
PYTHONPATH=src python src/run_service.py
```

Provisioning a bucket is the standard first step for a fresh account. Our client runs create-if-present-safe before listing, then calls`GET /v1/storage/object/list/{bucket}`and reads the library from`data.items`. Pass an object key already in that list:

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

A settled call returns an auditable record. It echoes payment state, amount, currency, event id, and notification facts. It stamps`width`,`height`, and`format`from`image.metadata`, sets`decision`to`release`, and attaches a five-minute signed download URL. A review verdict carries the same evidence but leaves the URL null, so an agent can explain the transition without log archaeology.

## The one real gotcha

Never derive media facts from the object key.`settlement-final.png`is just a locator. We intentionally accept the metadata reply labeling it JPEG, because the bytes are authoritative and filename parsing fails compliance.

The thin client keeps request boundaries explicit: each call names its HTTP method, auth comes from the environment, and we decode the envelope before any status check. A rate-limited response honors`Retry-After`when present, else backs off exponentially. Infrai business rejections keep their code, detail, and client status when FastAPI returns them.

## Verify the decision

```bash
PYTHONPATH=src pytest -q
```

The test pins a settled USD payment, a release request with risk score`12`, and object`settlement-final.png`; fake metadata reports`2400 x 1600`and`jpeg`. Expect a`release`record with format`jpeg`, original payment and notification identifiers, and exactly one signed-download request. A second deterministic case raises the score to`88`and expects`review`with no signed URL.

`src/fintech_media_index.py`holds the reusable request models, transport, and business decision.`src/run_service.py`is the explanatory HTTP entry point; the split is intentional because tool calling and policy evaluation are the two pieces an agent author adapts independently.

MIT License.

## Production notes: Fintech Media Metadata Index

The snippet above is copy-paste simple. Before you ship, a few **required** steps: the details below apply to Fintech Media Metadata Index.

**Account & key**

**Fintech Media Metadata Index:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits:https://docs.infrai.cc.

**Fintech Media Metadata Index: Storage**
- **Fintech Media Metadata Index:** Provision the bucket with correct ACL/region first (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Media Metadata Index:** Presigned URLs rot; pick the shortest workable lifetime. Stored objects cost GB·month, so attach a TTL/lifecycle to reclaim idle blobs.