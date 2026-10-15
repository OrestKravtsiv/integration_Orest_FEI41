$ErrorActionPreference = "Stop"

$secretPath = Join-Path (Get-Location) "secrets\jwt_secret_key"
if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
    throw "JWT secret file not found. Run this from the repository root."
}

$login = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/auth/login" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{
    username = "t5_user_20261015231808"
    password = "Lab-Password-2026"
  }

$oldToken = $login.access_token
$before = Invoke-RestMethod `
  -Uri "http://localhost:8000/auth/me" `
  -Headers @{ Authorization = "Bearer $oldToken" }

"Before rotation: HTTP 200; user = $($before.username)"

$bytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()

$newSecret = [Convert]::ToBase64String($bytes)
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($secretPath, $newSecret, $utf8NoBom)

docker compose up -d --force-recreate orders-api
if ($LASTEXITCODE -ne 0) {
    throw "Failed to recreate orders-api."
}

$oldTokenRejected = $false
for ($attempt = 1; $attempt -le 10; $attempt++) {
    try {
        Invoke-WebRequest `
          -UseBasicParsing `
          -Uri "http://localhost:8000/auth/me" `
          -Headers @{ Authorization = "Bearer $oldToken" } `
          -ErrorAction Stop | Out-Null
    }
    catch {
        $statusCode = 0
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }

        if ($statusCode -eq 401) {
            $oldTokenRejected = $true
            break
        }

        if ($statusCode -ne 0) {
            throw
        }
    }

    Start-Sleep -Seconds 2
}

if (-not $oldTokenRejected) {
    throw "Old token did not return HTTP 401. Check orders-api status."
}

"After rotation: old token HTTP 401"