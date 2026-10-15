$login = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/auth/login" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{
    username = "t5_user_20261015231808"
    password = "Lab-Password-2026"
  }

$t11Token = $login.access_token
$t11Path = (Resolve-Path ".\secrets\jwt_secret_key").Path
$t11OldSecret = [System.IO.File]::ReadAllText($t11Path)

$before = Invoke-RestMethod `
  -Uri "http://localhost:8000/auth/me" `
  -Headers @{ Authorization = "Bearer $t11Token" }

"Before rotation: HTTP 200; authenticated user = $($before.username)"