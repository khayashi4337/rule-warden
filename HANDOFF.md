# HANDOFF — 運用ノート

## 現在の状態（2026-10-07 時点）

実装済み・稼働中。テスト 111 件全通。

- Python 3.12・stdlib のみ（外部依存ゼロ）
- CLI: `python -m warden scan|list|serve|apply|watch|criteria|audit-verify`
- 条管理の対象範囲: ルート *.md + skills/ agents/ commands/ .agents/
  （全 rglob=1455 件で 5 分超 → 127 件に限定して数秒）
- PR フロー: `pr_service.py`（提案記録→審査→適用）＋ `propose_via_forgejo`
  （worktree で枝を切り forgejo remote へ push → Forgejo API で PR 作成。
  E2E 実測: claude-rules に PR#1 作成済み・open のまま残置）
- Forgejo API クライアント: `forgejo_client.py`（資格情報は
  `%USERPROFILE%\.config\rule-warden\forgejo-admin.txt` から実行時読み込み）
- audit_log ハッシュチェーン（schema v2・entry_hash 列）:
  行の編集・削除・挿入が `audit-verify` で検出できる（実 DB バックフィル済み）
- watch に git 汚染チェック: 管理対象と本リポジトリ両方の未コミット変更を検出
- criteria 7 分類を DB に登録済み（weight 合計 100: A25/B20/D15/E15/C10/F10/G5。
  旧暫定 5 件は `scripts/retire_old_criteria.py` で退役済み・行は残存）
- 逸脱手口の調査分類: `docs/deviation-techniques-2026-10.md`（A〜G 7 分類）

## バックアップ・リモート

- ローカル Forgejo（127.0.0.1:3300）:
  `warden-admin/rule-warden`（本リポジトリ・push 済み）、
  `warden-admin/claude-rules`（~/.claude 全12ブランチ push 済み・remote 名 forgejo）
- リポジトリ公開に向けて個人パスはサニタイズ済み（`C:\Users\user` → 汎用表記。
  fixture には実ルール本文のコピーが残る）

## 林さんレビュー待ち（タイムスタンプ付き・放置時は AI が良きに計らう — 2026-10-07 林さん指示）

- [2026-10-07] ADR-0002/0002.5/0003/0004 のドラフト → 承認（実装は ADR 通りに動作済み）

## 定例監視（2026-10-07 追加・稼働中）

- `python -m warden watch`: 1回スキャンし、新規条/消失条/防御条消失が
  あれば data/reports/watch-*.md にレポートを書く（変化なしなら静か）
- Windows タスクスケジューラ `rule-warden-watch`（**毎時**・2026-10-07 に
  07:00毎日から変更。改竄はセッション中に起きるため頻度優先。
  PC 休止中はスキップ）。削除は `schtasks /delete /tn rule-warden-watch`

## 採点・実測の記録

実 .claude リハーサル（5a、コピー data/rehearsal/claude-copy 上）:
127 ファイル・5,542 条スキャン → モック採点で 5,516 条 provisional_ai、
26 条 quarantined（物理隔離も検証済み）。
注意: MockGateway はキーワード一致の疑似採点のため誤検出あり
（禁止文も危険扱い）。本番採点は契約 AI 接続後に精度評価が必要。

実 .claude 適用（5b、2026-10-07・林さん号令）:
モック採点による誤隔離 7 件は `scripts/restore_quarantined.py` で全件復元済み。

ai:swe-2 による文脈採点を全 5,542 条に実施（2026-10-07、林さん「あなたの採点でいいよ」許可）。
score_runs/recommendations に永続化:

- ロード済み 96 条: 全文精読。0×84 / 5×7 / 10×2 / 15×3。隔離基準(60)超え 0 件
- ルート直下 662 条: 全文精読。すべて始末書・憲章・SuperClaude 参照・
  準ルール置き場で権限拡大指示なし
- サブツリー 4,784 条: 権限拡大キーワード走査のヒット 242 件を全文精読
  （すべて否定文・境界規定・参照文書）＋ファイル単位判定。
  個別注意値は憲章の自律 merge 条（#2833-2835, 15）、skill-sommelier
  自動収集/ルーティング（#3570/#3600, 10）、remote-mode 確認迂回
  （10）、ux-five-planes 止まらない条（#5387, 10）
- 結果: quarantined 0 件。provisional_ai 5,535、approved 7（復元分）
- 採点スクリプト: `scripts/score_loaded_swe2.py` / `score_rest_swe2.py`
  （採点理由は各 score_runs.rationale に保存。生成物は data/ 配下・gitignore）

## インシデント記録（2026-10-07）

CLAUDE.md の未コミット変更（§11 全削除・§10.8 停止条項削除・
@rules_dots_charter.md 削除）は林さんの編集ではないと確認 → 改竄として
`~/.claude/CLAUDE.md.tampered-20261006` に証拠保全したうえで
git restore でコミット済み版に復元。再スキャンで復活した 19 条
（§2/§3/§10/§11/憲章import）も score 0 で採点済み。

条の中身に「権限拡大を指示する汚染」は全 5,542 条で見つからなかったが、
「制約を削る差分」が汚染の実体だった。この改竄は staged 未コミットの
形跡として残っていた — watch の git 汚染チェックはこの手口を検知する。

## 残っている穴・次の作業候補（林さんの指示を待ってから着手すること）

- C 類（意味すり替えの検出）: hash 変更は見えるが意味変化は未検出
- F 類（戦略的欺瞞）: 条テキストでは原理的に困難 →「報告と実測の整合性」監査が次層
- 本物 AiGateway（MCP or API・別系統 2 系統・期限監視）の接続
- PR フローの CLI/UI 接続・git 未追跡ファイル向け経路
- ADR-0002/0002.5/0003/0004 のドラフト → 承認への状態更新
- 要件の不確かな点は ADR-0001 の「未決の細部」節を参照し、必要なら林質問ルール
  （1問ずつ・平易な言葉）で確認する

## 環境メモ（このマシン固有、実測済み 2026-10-06 更新）

- exec 既定の bash は C:\Windows\System32\bash.exe（WSL版）に解決され、出力なし終了コード1で失敗する
- Git Bash は G:\Program Files\Git\bin\bash.exe。PowerShell から & "G:\Program Files\Git\bin\bash.exe" -c "..." で使う
- git は PowerShell でそのまま使える（G:\Program Files\Git\cmd\git.exe）
- Podman 5.6.0 は I:\tools\Podman\podman.exe。Docker なし。WSL2 Ubuntu-24.04 稼働中
- podman-machine-default 作成済み（wsl, rootless, 4cpu/2GiB/50GiB）。
  VHDX は G:\podman-data\wsldist\podman-machine-default\ext4.vhdx（wsl export/import で移設済み）
- 注意: ~/.local/share/containers/podman を G: へのジャンクションにすると
  machine のイメージ pull が "The system cannot find the path specified" で失敗する。
  ジャンクション方式は不可。wsl --export/--import 方式で移設した
- Forgejo コンテナ稼働中: http://127.0.0.1:3300/（コンテナ内3000）、SSH は 127.0.0.1:2222。
  データは podman volume "forgejo-data"（VHDX 内 = G: 上）
- ポート 3000 は既存の wslrelay.exe（Ubuntu-24.04 側の何か）が使用中のため 3300 を使用
- win-sshproxy.exe が起動失敗する（exit 2147483651）ため Docker API 互換ソケットなし。
  podman CLI 自体は正常
- C: 側に残存: ~\.local\share\containers\podman\machine\wsl\cache のイメージキャッシュ tar
  （削除可だが要指示）
- ~/.claude の git 管理は4ファイルのみ（CLAUDE.md, rules_dots_charter.md,
  skills/codex-review/SKILL.md, 始末書）。残りのルールファイルは untracked。
  ~/.devin は git 未管理

## 作業上の約束

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
