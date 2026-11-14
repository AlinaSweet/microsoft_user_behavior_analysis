"""Start the local globally linked exploratory dashboard."""

import argparse

from user_behavior_analysis.api.dashboard_server import create_dashboard_server


def main() -> int:
    """Serve full-source analysis on localhost until interrupted.

    Returns:
        Zero after a normal user interrupt.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with create_dashboard_server(args.port) as server:
        print(f"看板一：http://127.0.0.1:{args.port}（Ctrl+C停止）", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("看板已停止。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
