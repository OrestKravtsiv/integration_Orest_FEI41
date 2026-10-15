$username = "t5_user_$((Get-Date).ToString('yyyyMMddHHmmss'))"
$body = @{
    username = $username
    password = "Lab-Password-2026"
} | ConvertTo-Json

$response = Invoke-WebRequest -UseBasicParsing `
    -Method Post `
    -Uri "http://localhost:8000/auth/register" `
    -ContentType "application/json" `
    -Body $body

"Username: $username"
"HTTP status: $($response.StatusCode)"
$response.Content