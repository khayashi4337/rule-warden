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
warden-admin/claude-rules を作成済み（.claude 側への push は未実施・要号令）。
ADR-0005 で運用方針が確定（デフォルト暫定承認・要確認は危険度順・バイパスは手動・
準ルールと隔離は分離保持し統合一覧・自動隔離可・復元はサニタイズ版・
修正削除も暫定取込）。ADR-0002〜0004 はドラフト。実装は未着手。

「仮の決定」の解消プラン（実装フェーズと対応付け）:
- フェーズ0: 言語・スタック決定（全ての前提。パーサー実装前に決める）
- フェーズ1: パーサー実装（ADR-0002）→ Rule-Unit trailer 自動挿入、
  非ロード棚卸し、succession 対応付け手順、RuleEngine ロールバックを解消
- フェーズ2: WardenStore + Orchestrator 実装（ADR-0003/0002.5）→
  状態遷移のアプリ層強制、PR 適用のトランザクション境界、
  質問タイムアウト初期値、Orchestrator 依存形を解消
- フェーズ3: AiGateway 実装 → MCP or API 選定、ai_profiles への
  scorer/reviewer モデル登録（別系統・契約済み）、期限監視を解消
- フェーズ4: Web UI 実装 → 統合一覧（union・危険度ソート）、
  bypass_mode 切替 UI を解消

次の作業候補（林さんの指示を待ってから着手すること）:
- .claude リポジトリに Forgejo リモートを追加して push（要号令）
- フェーズ0: アプリの言語・スタック決定
- ADR-0002/0003 のレビュー反映 → 承認
- フェーズ1: パーサー実装（ADR-0002 準拠）

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
- 要件の不確かな点は ADR-0001 の「未決の細部」節を参照し、必要なら林質問ルール（1問ずつ・平易な言葉）で確認する
```

---

## 引継ぎ時に人間がやること

- このリポジトリはローカルのみ（リモートなし）。次セッションで `cd G:\prj2\rule-warden` して開始
- 要件に変更があれば ADR を更新するか新しい ADR を追加する
