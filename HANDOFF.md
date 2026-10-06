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

次の作業候補（林さんの指示を待ってから着手すること）:
- ~~制約削減の検出~~ 実装済み（2026-10-07）: orchestrator.scan が gone 条の
  raw_text を GUARDRAIL_RE（禁止/控え/権限/never 等）で判定し、ヒットすれば
  stats["guardrail_gone"]＋audit_log(action=guardrail_gone)＋CLI 警告に出す。
  隔離はしない警告のみ（tests: test_guardrail_gone_warned 等・87 テスト全通）
- apply コマンドの接続、PR 適用フロー（pull_requests/proposed_units/reviews）
- ADR-0002/0003/0004 のドラフト → 承認への状態更新
- 本物 AiGateway（MCP or API・別系統 2 系統・期限監視）の接続

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
- Forgejo: warden-admin/claude-rules（.claude 全12ブランチ push 済み・remote 名 forgejo）、
  warden-admin/rule-warden（このリポジトリのバックアップ先）
- 要件の不確かな点は ADR-0001 の「未決の細部」節を参照し、必要なら林質問ルール（1問ずつ・平易な言葉）で確認する
```

---

## 引継ぎ時に人間がやること

- このリポジトリはローカルのみ（リモートなし）。次セッションで `cd G:\prj2\rule-warden` して開始
- 要件に変更があれば ADR を更新するか新しい ADR を追加する
