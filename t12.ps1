$ErrorActionPreference = "Stop"
$baseUrl = "http://localhost:8000"

$login = Invoke-RestMethod `
  -Method Post `
  -Uri "$baseUrl/auth/login" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{
    username = "t5_user_20261015231808"
    password = "Lab-Password-2026"
  }

$headers = @{ Authorization = "Bearer $($login.access_token)" }

docker compose stop forecast-api
if ($LASTEXITCODE -ne 0) {
    throw "Could not stop forecast-api."
}

try {
    $body = @{
        client_name = "T12 Forecast Down"
        gr_liv_area = 1800
        total_bsmt_sf = 1000
        garage_area = 500
        year_built = 2005
        overall_qual = 7
        ms_zoning = "RL"
    } | ConvertTo-Json

    $response = Invoke-WebRequest `
      -UseBasicParsing `
      -Method Post `
      -Uri "$baseUrl/orders" `
      -Headers $headers `
      -ContentType "application/json" `
      -Body $body `
      -TimeoutSec 30

    $order = $response.Content | ConvertFrom-Json
    "HTTP status: $($response.StatusCode)"
    "Order ID: $($order.id)"
    "predicted_price: $($order.predicted_price)"

    if ($response.StatusCode -ne 201 -or $null -ne $order.predicted_price) {
        throw "Unexpected result; expected HTTP 201 and null predicted_price."
    }
}
finally {
    docker compose start forecast-api
}