"""Run the student website:  python -m web   then open http://127.0.0.1:8600

On a host:  python -m web --host 0.0.0.0 --port 7860 --workers 2   (with HIMSIM_WEB_BUNDLE set; see web/bundle.py)
"""

from __future__ import annotations

import argparse
import logging

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="HimSim student website")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8600)
    parser.add_argument("--workers", type=int, default=1, help="processes; each loads the glacier and warms up itself")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run("web.api:app", host=args.host, port=args.port, workers=args.workers, proxy_headers=True,
                forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
