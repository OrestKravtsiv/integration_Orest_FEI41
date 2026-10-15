$login = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/auth/login" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{
    username = "t5_user_20261015231808"
    password = "Lab-Password-2026"
  }

$body = @{
  client_name = "T8 Test"
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
  -Uri "http://localhost:8000/orders" `
  -Headers @{ Authorization = "Bearer $($login.access_token)" } `
  -ContentType "application/json" `
  -Body $body

"HTTP status: $($response.StatusCode)"
$response.Content