"""Serve the local EDA application with bounded read-only aggregate routes."""

import io
import json
from functools import lru_cache
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urlsplit

import duckdb
import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.models.dashboard_models import DashboardFilter
from user_behavior_analysis.service.interactive_eda import query_dashboard
from user_behavior_analysis.service.interactive_eda import validate_dashboard_filter


def _source_options(source: Path, fingerprint: str) -> dict[str, Any]:
    """Read immutable bounds and category IDs for the filter controls.

    Args:
        source: Verified key-frequency source path.
        fingerprint: Startup SHA-256 of the source.

    Returns:
        Observed calendar limits and exact category identifiers.
    """
    with duckdb.connect() as connection:
        relation = connection.read_parquet(str(source))
        relation.create_view("source")
        bounds = require_result_row(
            connection.execute(
                ("SELECT MIN(event_time),MAX(event_time) FROM s" + "ource")
            ).fetchone()
        )
        categories = connection.execute(
            ("SELECT DISTINCT category_id FROM source ORDER" + " BY category_id")
        ).fetchall()
    return {
        "start": str(bounds[0].date()),
        "end": str(bounds[1].date()),
        "categories": [r[0] for r in categories],
        "source_sha256": fingerprint,
    }


def create_dashboard_server(port: int, source_path: Path | None = None) -> HTTPServer:
    """Bind a local-only app without exposing arbitrary project files.

    Args:
        port: Explicit local TCP port.
        source_path: Optional isolated fixture; defaults to the complete key table.

    Returns:
        Server owned and shut down by the caller.

    Raises:
        ValueError: A port or project-contained source is invalid.
    """
    if not 1024 <= port <= 65535:
        raise ValueError("Choose a port between 1024 and 65535")
    source = project_output_path(
        source_path or "data/processed/base_raw_v2/key_hour/data.parquet"
    )
    fingerprint = sha256_file(source)
    options = _source_options(source, fingerprint)
    assets = PROJECT_ROOT / "src/user_behavior_analysis/assets/eda"

    @lru_cache(maxsize=8)
    def calculate(request: DashboardFilter) -> dict[str, Any]:
        """Cache a bounded number of exact global-filter combinations.

        Args:
            request: Immutable explicit analysis population.

        Returns:
            Recomputed full-source aggregates and their immutable source fingerprint.
        """
        return dict(query_dashboard(request, source), source_sha256=fingerprint)

    class Handler(BaseHTTPRequestHandler):
        """Route only known assets and bounded aggregate queries."""

        def _send(self, content: bytes, kind: str, status: int = 200) -> None:
            """Send one explicit content type and length without external resources.

            Args:
                content: Already encoded response body.
                kind: Explicit MIME content type.
                status: HTTP status code.
            """
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            """Serve validated read-only GET requests; framework callback name.

            Notes:
                Raw internal exceptions are logged locally and not shown in the UI.
            """
            parsed = urlsplit(self.path)
            mapping = {
                "/": ("dashboard.html", "text/html; charset=utf-8"),
                "/dashboard.js": (
                    "dashboard.js",
                    "application/javascript; charset=utf-8",
                ),
                "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
            }
            try:
                if parsed.path in mapping:
                    name, kind = mapping[parsed.path]
                    self._send((assets / name).read_bytes(), kind)
                    return
                if parsed.path == "/api/options":
                    payload = options
                elif parsed.path in {"/api/data", "/api/export"}:
                    parameters = parse_qs(parsed.query, keep_blank_values=True)
                    if any(len(value) != 1 for value in parameters.values()):
                        raise ValueError("Duplicate filter")
                    raw = {key: value[0] for key, value in parameters.items()}
                    table = raw.pop("table", "")
                    request = validate_dashboard_filter(raw)
                    payload = calculate(request)
                    if parsed.path == "/api/export":
                        tables = {
                            key: value
                            for key, value in payload.items()
                            if isinstance(value, list)
                        }
                        if table not in tables:
                            raise ValueError("Unknown export table")
                        content = io.StringIO()
                        pd.DataFrame(tables[table]).to_csv(content, index=False)
                        self._send(
                            content.getvalue().encode("utf-8-sig"),
                            "text/csv; charset=utf-8",
                        )
                        return
                else:
                    self._send(b"Not found", "text/plain", 404)
                    return
                self._send(
                    json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(),
                    "application/json; charset=utf-8",
                )
            except ValueError as error:
                self._send(
                    json.dumps(
                        {"error": "筛选条件无效，请检查日期与分群。"},
                        ensure_ascii=False,
                    ).encode(),
                    "application/json; charset=utf-8",
                    400,
                )
                self.log_error("Invalid filter: %s", error)
            except (OSError, duckdb.Error) as error:
                self._send(
                    json.dumps(
                        {"error": "统计暂未完成，请重试或查看本地运行日志。"},
                        ensure_ascii=False,
                    ).encode(),
                    "application/json; charset=utf-8",
                    500,
                )
                self.log_error("Query failed: %s", error)

    server = HTTPServer(("127.0.0.1", port), Handler)
    return server
