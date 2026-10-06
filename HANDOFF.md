# HANDOFF — 次セッションへの引継ぎ

新しいセッションに以下のプロンプトを貼り付けてください。

---

```text
G:\prj2\rule-warden の作業を引き継ぎます。

まず以下のファイルを順に読んでください。
1. G:\prj2\rule-warden\README.md （いきさつと「逸脱AIの自浄化の限界」の概念）
2. G:\prj2\rule-warden\docs\adr\0001-requirements-and-architecture.md （確定済み要件 D1〜D8 とコンポーネント図）
3. G:\prj2\rule-warden\docs\adr\0002-rule-parser-design.md （条単位パーサー設計・ドラフト）
4. G:\prj2\rule-warden\docs\adr\0003-sqlite-schema.md （SQLite スキーマ設計・ドラフト）

状態: 要件ヒアリング完了（ADR-0001 確定）。Podman machine 作成と Forgejo 起動は完了。
条単位パーサー設計と SQLite スキーマ設計は ADR-0002/0003 としてドラフト提出済み（林さんレビュー待ち）。実装は未着手。

次の作業候補（林さんの指示を待ってから着手すること）:
- Forgejo 初期設定（ブラウザで http://127.0.0.1:3300/ を開き管理者作成）+ .claude 用リポジトリ作成
- ADR-0002/0003 のレビュー反映 → 承認
- パーサー実装（ADR-0002 準拠。言語・スタックの決定を含む）
- 採点AI・審査AI のモデル選定と連携方式（MCP or API）の検討

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
