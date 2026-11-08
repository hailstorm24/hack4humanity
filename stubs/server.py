"""All three stubs in one process on one port, for hosting.

  /v1/...             Bot Management API
  /classifier/v1/...  Classifier API
  /webhook/{bot_id}   Bot Runtime
  /healthz            platform health check

Services still talk to each other over HTTP (management and runtime call
the classifier at CLASSIFIER_URL), so splitting them up later only
means changing that URL.
"""
import os
import sys

PORT = int(os.environ.get("PORT", "8080"))
os.environ.setdefault("HOST", "0.0.0.0")
os.environ.setdefault("CLASSIFIER_URL", f"http://127.0.0.1:{PORT}/classifier/v1")

import classifier  # noqa: E402  (env must be set before importing common)
import management  # noqa: E402
import runtime  # noqa: E402
from common import init_db, serve  # noqa: E402

ROUTES = (
    management.ROUTES
    + [(m, "/classifier" + p, h) for m, p, h in classifier.ROUTES]
    + runtime.ROUTES
    + [("GET", r"/healthz", lambda r, m, b: (200, {"status": "ok"}))]
)

if __name__ == "__main__":
    classifier._check_rules()
    print(f"[stubs] storage: {init_db()}", file=sys.stderr)
    serve(ROUTES, PORT, "stubs")
