# HANDOFF — 次セッションへの引継ぎ

新しいセッションに以下のプロンプトを貼り付けてください。

---

```text
G:\prj2\rule-warden の作業を引き継ぎます。

まず以下のファイルを順に読んでください。
1. G:\prj2\rule-warden\README.md （いきさつと「逸脱AIの自浄化の限界」の概念）
2. G:\prj2\rule-warden\docs\adr\0001-requirements-and-architecture.md （確定済み要件 D1〜D8 とコンポーネント図）
3. G:\prj2\rule-warden\docs\adr\0002-rule-parser-design.md （条単位パーサー設計・ドラフト）
4. G:\prj2\rule-warden\docs\adr\0002.5-domain-model.md （要件用語のクラス図・シーケンス図・ドラフト）
5. G:\prj2\rule-warden\docs\adr\0003-sqlite-schema.md （SQLite スキーマ設計・ドラフト）
6. G:\prj2\rule-warden\docs\adr\0004-commit-message-rules.md （コミットメッセージルール・ドラフト）
7. G:\prj2\rule-warden\docs\adr\0005-operation-decisions.md （ヒアリング確定の運用方針 O1〜O11＋仮の決定）

状態: 要件ヒアリング完了（ADR-0001 確定）。Podman machine 作成と Forgejo 起動・
初期設定は完了。Forgejo 管理ユーザ warden-admin と private リポジトリ
warden-admin/claude-rules（.claude 全ブランチ push 済み）、
warden-admin/rule-warden（本リポジトリのバックアップ）作成済み。
ADR-0005 で運用方針が確定（O1〜O11）。

実装: フェーズ 0a・1a〜1e・2a〜2d・3a〜3c・4a〜4c・5a 完了（計画の残は 5b のみ）。
- Python 3.12・stdlib のみ（外部依存ゼロ）。テスト 83 件通過
- モジュール: parser_lines/units/hash/io, loadgraph, quarantine,
  provenance, schema/store, transitions, orchestrator, ai_gateway,
  scoring_service, webapp
- CLI: `python -m warden scan|list|serve` 実装済み（apply は未接続）
- 条管理の対象範囲: ルート *.md + skills/ agents/ commands/ .agents/
  （全 rglob=1455 件で 5 分超 → 127 件に限定して数秒）
- 実測リハーサル（5a、コピー data/rehearsal/claude-copy 上）:
  127 ファイル・5,542 条スキャン → モック採点で 5,516 条 provisional_ai、
  26 条 quarantined（物理隔離も検証済み）
- 注意: MockGateway はキーワード一致の疑似採点のため誤検出あり
  （「Never Override...」のような禁止文も危険扱い）。本番採点は
  契約 AI 接続後に精度評価が必要

5b 実施済み（2026-10-07、林さん号令）: 実 .claude に採点適用。
モック採点による誤隔離 7 件は scripts/restore_quarantined.py で全件復元済み。

5b続き（2026-10-07、林さん「あなたの採点でいいよ」許可）: ai:swe-2 による
文脈採点を全 5,542 条に実施・score_runs/recommendations に永続化。
- ロード済み 96 条: 全文精読。0×84 / 5×7 / 10×2 / 15×3。隔離基準(60)超え 0 件
- ルート直下 662 条: 全文精読。すべて始末書・憲章・SuperClaude 参照・
  準ルール置き場で権限拡大指示なし
- サブツリー 4,784 条: 権限拡大キーワード走査のヒット 242 件を全文精読
  （すべて否定文・境界規定・参照文書）＋ファイル単位判定。
  個別注意値は憲章の自律 merge 条（#2833-2835, 15）、skill-sommelier
  自動収集/ルーティング（#3570/#3600, 10）、remote-mode 確認迂回
  （10）、ux-five-planes 止まらない条（#5387, 10）
- 結果: quarantined 0 件。provisional_ai 5,535、approved 7（復元分）
- 重要な観測: 作業ツリーの CLAUDE.md は未コミット変更で §11（すり替え
  禁止・権限行使を控える、2026-10-05 林さん追加）・§10.8 の Codex 停止条項・
  @rules_dots_charter.md が削除・弱体化されている。採点対象としての
  「権限拡大を指示する条」は見つからなかったが、ガードレールを削る
  変更が差分として存在する。誰の編集かは git からは断定不可。林さん報告済み
- 採点スクリプト: scripts/score_loaded_swe2.py / score_rest_swe2.py
  （採点理由は各 score_runs.rationale に保存。生成物は data/ 配下・gitignore）

インシデント（2026-10-07）: CLAUDE.md の未コミット変更（§11 全削除・
§10.8 停止条項削除・@rules_dots_charter.md 削除）は林さんの編集では
ないと確認 → 改竄として `C:\Users\user\.claude\CLAUDE.md.tampered-20261006` に
証拠保全したうえで git restore でコミット済み版に復元。再スキャンで
復活した 19 条（§2/§3/§10/§11/憲章import）も score 0 で採点済み。
条の中身に「権限拡大を指示する汚染」は全 5,542 条で見つからなかったが、
「制約を削る差分」が汚染の実体だった。今後は untracked ファイルも含めて
「前回との差分で制約が削られていないか」を監査対象にする価値あり。

林さんレビュー待ち（タイムスタンプ付き・放置時は AI が良きに計らう — 2026-10-07 林さん指示）:
- [2026-10-07] ADR-0002/0002.5/0003/0004 のドラフト → 承認（実装は ADR 通りに動作済み）
- [2026-10-07] ~~Forgejo API 接続の実施可否~~ → 同日 AI 判断で実施
  （ローカル Forgejo・PR 未マージなら可逆と判断）

定例監視（2026-10-07 追加・稼働中）:
- `python -m warden watch`: 1回スキャンし、新規条/消失条/防御条消失が
  あれば data/reports/watch-*.md にレポートを書く（変化なしなら静か）
- Windows タスクスケジューラ `rule-warden-watch`（**毎時**・2026-10-07 に
  07:00毎日から変更。改竄はセッション中に起きるため頻度優先。
  PC 休止中はスキップ）。削除は `schtasks /delete /tn rule-warden-watch`

次の作業候補（林さんの指示を待ってから着手すること）:
- ~~制約削減の検出~~ 実装済み（2026-10-07）: orchestrator.scan が gone 条の
  raw_text を GUARDRAIL_RE（禁止/控え/権限/never 等）で判定し、ヒットすれば
  stats["guardrail_gone"]＋audit_log(action=guardrail_gone)＋CLI 警告に出す。
  隔離はしない警告のみ（tests: test_guardrail_gone_warned 等・87 テスト全通）
- ~~apply コマンドの接続~~ 実装済み（2026-10-07）: `warden/apply_service.py`
  — DB の決定と物理状態を一致させる。quarantined で本文残存 → 物理隔離、
  quarantined 以外＆隔離ファイル残存 → present=0 なら物理復元＋隔離ファイル
  削除、present=1 なら stale 隔離ファイルのみ削除＋空ディレクトリ掃除。
  `python -m warden apply`（既定 dry-run）/`--write`。実 .claude で
  前回復元時の stale 隔離ファイル 7 件を除去済み（quarantine/ は空）
- ~~PR 適用フロー~~ ローカル部分実装済み（2026-10-07）: `warden/pr_service.py`
  — create_pr（提案記録）/record_review（escalate→escalated）/set_pr_state
  /apply_pr（open＋最新 verdict=approve のみ適用。add→節末尾挿入、
  modify→隔離+新文復元、remove→隔離。適用後 rescan で applied_unit_id
  リンク＋add/modify は provisional_ai・remove は quarantined。エラー時は
  open のまま。dry-run 既定）
  + propose_via_forgejo: worktree で枝を切り条を編集→forgejo remote へ
    push→Forgejo API で PR 作成→DB 記録（.claude 作業ツリー不変・
    git 追跡ファイルのみ対象）。E2E 実測: claude-rules に PR#1 作成済み
    （検証用・open のまま残置）。残: CLI/UI 接続・未追跡ファイル向け経路
- ADR-0002/0003/0004 のドラフト → 承認への状態更新
- 本物 AiGateway（MCP or API・別系統 2 系統・期限監視）の接続

逸脱手口調査 + warden 自己防衛（2026-10-07、林さん号令「進めてください」）:
- `docs/deviation-techniques-2026-10.md`: 逸脱の手口を Web 調査して
  A〜G の 7 分類に整理（A=防御ルール攻撃＝本家 §11 事件と同型、
  B=評価・監視への攻撃、C=言葉のすり替え、D=権限拡張、E=承認ハック、
  F=戦略的欺瞞、G=ダークパターン。D2 定期調査の初回実行）
- audit_log ハッシュチェーン（schema v2・entry_hash 列）: 各行が前行
  hash を含むため、DB の行編集・削除・挿入が verify で検出できる。
  `python -m warden audit-verify` で検証（実 DB 41 件 OK）。
  旧 DB は init_schema 時に自動マイグレーション＋バックフィル
- watch に git 汚染チェック追加: 管理対象と warden 自身のリポジトリで
  追跡ファイルの未コミット変更を検出してレポートに出す
  （§11 改竄は staged 未コミットで残っていた形跡と同型）
- criteria 7 分類を DB に登録（`python -m warden criteria` で seed+一覧。
  weight 合計 100: A25/B20/D15/E15/C10/F10/G5）。
  旧暫定ルーブリック 5 件は scripts/retire_old_criteria.py で退役済み
  （行は残し active_to を立てただけ。score_details 参照は維持）
- 残る穴: C 類（意味すり替えの検出＝hash 変更は見えるが意味変化は未検出）、
  F 類（テキストでは原理的に困難 →「報告と実測の整合性」監査が次層）
- tests: tests/test_integrity.py 新規（監査チェーン改竄検出・マイグレーション・
  criteria seed・git watch）＋test_watch.py/test_store.py 更新。111 件全通

環境メモ（このマシン固有、実測済み 2026-10-06 更新）:
- exec 既定の bash は C:\Windows\System32\bash.exe（WSL版）に解決され、出力なし終了コード1で失敗する
- Git Bash は G:\Program Files\Git\bin\bash.exe。PowerShell から & "G:\Program Files\Git\bin\bash.exe" -c "..." で使う
- git は PowerShell でそのまま使える（G:\Program Files\Git\cmd\git.exe）
- Podman 5.6.0 は I:\tools\Podman\podman.exe。Docker なし。WSL2 Ubuntu-24.04 稼働中
- podman-machine-default 作成済み（wsl, rootless, 4cpu/2GiB/50GiB）。
  VHDX は G:\podman-data\wsldist\podman-machine-default\ext4.vhdx（wsl export/import で移設済み）
- 注意: C:\Users\user\.local\share\containers\podman を G: へのジャンクションにすると
  machine のイメージ pull が "The system cannot find the path specified" で失敗する。
  ジャンクション方式は不可。wsl --export/--import 方式で移設した
- Forgejo コンテナ稼働中: http://127.0.0.1:3300/（コンテナ内3000）、SSH は 127.0.0.1:2222。
  データは podman volume "forgejo-data"（VHDX 内 = G: 上）
- ポート 3000 は既存の wslrelay.exe（Ubuntu-24.04 側の何か）が使用中のため 3300 を使用
- win-sshproxy.exe が起動失敗する（exit 2147483651）ため Docker API 互換ソケットなし。
  podman CLI 自体は正常
- C: 側に残存: ~\.local\share\containers\podman\machine\wsl\cache のイメージキャッシュ tar
  （削除可だが要指示）
- C:\Users\user\.claude の git 管理は4ファイルのみ（CLAUDE.md, rules_dots_charter.md,
  skills/codex-review/SKILL.md, 始末書）。残りのルールファイルは untracked。
  C:\Users\user\.devin は git 未管理

作業上の約束:
- 依頼された課題だけやる。1タスク1コミット。push・公開・破壊的操作は林さんの明示の号令を待つ
- **各マイクロステップは 3 回セルフレビュー、さらにフェーズ終了時に
  フェーズ全体をまとめて 3 回レビューしてから次へ進む**（2026-10-07 指示）
- 例外（2026-10-07 林さん許可）: **ローカル Forgejo（127.0.0.1:3300）への push は
  「いい感じの成果が出たら自動でやる」こと**。事前許可済み。外部サービスへの
  公開・破壊的操作は引き続き号令待ち
- レビュー待ち放置ルール（2026-10-07 林さん指示）: 上の「林さんレビュー待ち」
  項目は記録日を起点に、林さんの応答がないままなら AI の判断で進めてよい
  （良きに計らう）。進めた場合は実施日と判断理由をこのファイルに記録する
- **一括機械変換は確認必須**（2026-10-07 林さん指示「確認必須」）:
  複数ファイル・文書にまたがる rename・一括置換・整形は、対象一覧と
  変換表（before→after）を示して林さんの確認を取ってから実行する。
  「検索しにくい」等の観察指摘は作業命令ではない。前例: 同日に確認なしで
  23 ファイル 215 箇所の ID 一括置換を push → 差し戻し・revert 済み（0eb7afb）
- Forgejo: warden-admin/claude-rules（.claude 全12ブランチ push 済み・remote 名 forgejo）、
  warden-admin/rule-warden（このリポジトリのバックアップ先）
- 要件の不確かな点は ADR-0001 の「未決の細部」節を参照し、必要なら林質問ルール（1問ずつ・平易な言葉）で確認する
```

---

## 引継ぎ時に人間がやること

- このリポジトリはローカルのみ（リモートなし）。次セッションで `cd G:\prj2\rule-warden` して開始
- 要件に変更があれば ADR を更新するか新しい ADR を追加する
