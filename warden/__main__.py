"""CLI エントリ: python -m warden <command>"""

from __future__ import annotations

import argparse
import sys

from warden import __version__, logging_setup
from warden.config import Config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="warden",
        description="rule-warden: .claude ルールの条単位管理",
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command")

    sub.add_parser("scan", help="管理対象を走査して条を抽出・記録する")
    sub.add_parser("list", help="一覧を表示する（統合リスト・危険度順）")
    sub.add_parser("apply", help="暫定適用・隔離/復元を実行する")
    sub.add_parser("serve", help="Web UI サーバを起動する（オンデマンド）")

    return p


def main(argv: list[str] | None = None) -> int:
    logging_setup.setup()
    args = build_parser().parse_args(argv)
    config = Config()

    if args.command is None:
        build_parser().print_help()
        return 0

    from warden.orchestrator import review_list, scan
    from warden.store import WardenStore

    if args.command in ("scan", "list"):
        config.data_dir.mkdir(parents=True, exist_ok=True)
        store = WardenStore(config.db_path)
        store.init_schema()
        try:
            if args.command == "scan":
                stats = scan(store, config.agent.name, config.agent.root)
                print(f"scan: {stats}")
            else:
                items = review_list(store)
                for it in items:
                    print(
                        f"[{it['status']}] score={it['score']} "
                        f"{it['path']} :: {it['heading_path']} :: "
                        f"{it['raw_text'][:60]}"
                    )
                print(f"{len(items)} item(s)")
        finally:
            store.close()
        return 0

    if args.command == "serve":
        config.data_dir.mkdir(parents=True, exist_ok=True)
        store = WardenStore(config.db_path)
        store.init_schema()
        from warden.webapp import serve as web_serve

        web_serve(store, config.agent.root)
        return 0

    # apply はフェーズ 5 のリハーサルで接続
    print(f"[not implemented] {args.command} (db={config.db_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
