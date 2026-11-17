"""Build GitHub Pages without local data or external packages."""

import json
from pathlib import Path

from user_behavior_analysis.service.dashboard_publication import build_site

if __name__ == "__main__":
    print(
        json.dumps(build_site(Path(__file__).resolve().parents[1]), ensure_ascii=False)
    )
