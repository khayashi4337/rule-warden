# HANDOFF — 次セッションへの引継ぎ

新しいセッションに以下のプロンプトを貼り付けてください。

---

```text
G:\prj2\rule-warden の作業を引き継ぎます。

まず以下の2ファイルを順に読んでください。
1. G:\prj2\rule-warden\README.md （いきさつと「逸脱AIの自浄化の限界」の概念）
2. G:\prj2\rule-warden\docs\adr\0001-requirements-and-architecture.md （確定済み要件 D1〜D8 とコンポーネント図）

状態: 要件ヒアリングは完了し ADR-0001 として確定済み。実装は未着手。

次の作業候補（林さんの指示を待ってから着手すること）:
- Podman machine の作成（ストレージは G: ドライブ側。C: は容量不足）
- Forgejo の Podman 上での起動
- .claude ルールを1条単位に分解するパーサーの設計
- SQLite スキーマ設計（承認ステータス: 承認済み/暫定AI承認/審査中/隔離/却下）

環境メモ（このマシン固有、実測済み）:
- exec 既定の bash は C:\Windows\System32\bash.exe（WSL版）に解決され、出力なし終了コード1で失敗する
- Git Bash は G:\Program Files\Git\bin\bash.exe。PowerShell から & "G:\Program Files\Git\bin\bash.exe" -c "..." で使う
- git は PowerShell でそのまま使える（G:\Program Files\Git\cmd\git.exe）
- Podman は I:\tools\Podman\podman.exe にあるが machine 未作成。Docker なし。WSL2 Ubuntu-24.04 稼働中
- C:\Users\user\.claude は git 管理済み、C:\Users\user\.devin は git 未管理

作業上の約束:
- 依頼された課題だけやる。1タスク1コミット。push・公開・破壊的操作は林さんの明示の号令を待つ
- 要件の不確かな点は ADR-0001 の「未決の細部」節を参照し、必要なら林質問ルール（1問ずつ・平易な言葉）で確認する
```

---

## 引継ぎ時に人間がやること

- このリポジトリはローカルのみ（リモートなし）。次セッションで `cd G:\prj2\rule-warden` して開始
- 要件に変更があれば ADR を更新するか新しい ADR を追加する
