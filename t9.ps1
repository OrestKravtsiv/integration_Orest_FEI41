$login = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/auth/login" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{
    username = "t5_user_20261015231808"
    password = "Lab-Password-2026"
  }

$headers = @{ Authorization = "Bearer $($login.access_token)" }

$orderBody = @{
  client_name = "T9 Patch Test"
  gr_liv_area = 1800
  total_bsmt_sf = 1000
  garage_area = 500
  year_built = 2005
  overall_qual = 7
  ms_zoning = "RL"
} | ConvertTo-Json

$order = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/orders" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $orderBody

$patch = Invoke-WebRequest `
  -UseBasicParsing `
  -Method Patch `
  -Uri "http://localhost:8000/orders/$($order.id)" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{ gr_liv_area = 2200 } | ConvertTo-Json)

"Order ID: $($order.id)"
"PATCH HTTP status: $($patch.StatusCode)"
"Before:"
$order | Select-Object gr_liv_area, predicted_price | ConvertTo-Json
"After:"
$patch.Content