"""Forgejo REST API クライアント（stdlib のみ・PR フロー S3 の F 部分）。

認証情報は ~/.config/rule-warden/forgejo-admin.txt（user:/pass:/url: 行形式）
から実行時に読む。値をコード・ログ・例外メッセージに出さない。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

CRED_PATH = Path.home() / ".config" / "rule-warden" / "forgejo-admin.txt"
DEFAULT_BASE = "http://127.0.0.1:3300"


def load_credentials(path: Path = CRED_PATH) -> tuple[str, str]:
    """user:/pass: 行形式の資格情報を読む。見つからなければ ValueError。"""
    user = password = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("user:"):
            user = line.split(":", 1)[1].strip()
        elif line.startswith("pass:"):
            password = line.split(":", 1)[1].strip()
    if not user or not password:
        raise ValueError(f"credentials not found in {path}")
    return user, password


class ForgejoClient:
    def __init__(self, base: str = DEFAULT_BASE,
                 user: str | None = None, password: str | None = None):
        self.base = base.rstrip("/")
        if user is None or password is None:
            user, password = load_credentials()
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self._auth = f"Basic {token}"

    def _req(self, method: str, api_path: str,
             payload: dict | None = None) -> dict | list:
        body = (json.dumps(payload).encode("utf-8")
                if payload is not None else None)
        req = Request(
            f"{self.base}/api/v1{api_path}",
            data=body, method=method,
            headers={"Authorization": self._auth,
                     "Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=15) as resp:
                raw = resp.read()
        except HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(
                f"Forgejo {method} {api_path}: HTTP {e.code} {detail}") from e
        return json.loads(raw) if raw else {}

    def repo_exists(self, repo: str) -> bool:
        """repo は 'owner/name' 形式。"""
        try:
            self._req("GET", f"/repos/{repo}")
            return True
        except RuntimeError:
            return False

    def create_pull_request(self, repo: str, head: str, base_branch: str,
                            title: str, body: str = "") -> dict:
        """PR を作成し {number, html_url, state} を返す。"""
        pr = self._req("POST", f"/repos/{repo}/pulls", {
            "head": head, "base": base_branch,
            "title": title, "body": body,
        })
        return {"number": pr["number"],
                "html_url": pr.get("html_url"),
                "state": pr.get("state")}

    def close_pull_request(self, repo: str, number: int) -> None:
        self._req("PATCH", f"/repos/{repo}/pulls/{number}",
                  {"state": "closed"})
