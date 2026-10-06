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
    ap_apply = sub.add_parser(
        "apply", help="DB の決定と物理状態を一致させる（隔離/復元）")
    ap_apply.add_argument(
        "--write", action="store_true",
        help="実際にファイルを書き換える（既定は dry-run 表示のみ）")
    sub.add_parser("serve", help="Web UI サーバを起動する（オンデマンド）")
    sub.add_parser("watch", help="定例スキャン（変化時のみレポート出力）")

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
                if stats.get("guardrail_gone"):
                    print("!! 防御系の条が消えています（改竄疑い・要確認）:")
                    for g in stats["guardrail_gone"]:
                        loc = "loaded" if g["loaded"] else "non-loaded"
                        print(f"   #{g['unit_id']} [{loc}] "
                              f"{g['path']}: {g['text']}")
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

    if args.command == "apply":
        config.data_dir.mkdir(parents=True, exist_ok=True)
        store = WardenStore(config.db_path)
        store.init_schema()
        try:
            from warden.apply_service import apply_decisions

            stats = apply_decisions(
                store, config.agent.root, dry_run=not args.write)
            mode = "WRITE" if args.write else "dry-run"
            print(f"apply [{mode}]:")
            for key in ("quarantined", "restored", "stale_removed",
                        "skipped"):
                for it in stats[key]:
                    print(f"  {key}: {it}")
            print(f"apply [{mode}]: done")
        finally:
            store.close()
        return 0

    if args.command == "watch":
        config.data_dir.mkdir(parents=True, exist_ok=True)
        store = WardenStore(config.db_path)
        store.init_schema()
        try:
            from warden.watch import watch_once

            res = watch_once(store, config.agent.name, config.agent.root,
                             config.data_dir / "reports")
            if res["changed"]:
                print(f"watch: 変化あり → {res['report']}")
            else:
                print("watch: 変化なし")
        finally:
            store.close()
        return 0

    print(f"[not implemented] {args.command} (db={config.db_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
