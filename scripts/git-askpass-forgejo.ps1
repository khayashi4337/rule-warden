# GIT_ASKPASS 用。Forgejo の認証情報を %USERPROFILE%\.config\rule-warden\
# forgejo-admin.txt から読んで返す（秘密値はこのファイルに書かない）。
$cred = Get-Content "$env:USERPROFILE\.config\rule-warden\forgejo-admin.txt"
$user = ($cred | Where-Object { $_ -like 'user:*' }) -replace '^user:\s*', ''
$pass = ($cred | Where-Object { $_ -like 'pass:*' }) -replace '^pass:\s*', ''
if ($args[0] -match 'Username') { Write-Output $user } else { Write-Output $pass }
