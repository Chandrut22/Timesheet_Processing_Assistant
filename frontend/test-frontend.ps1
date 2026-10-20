<#
  Acceptance checks for the frontend container (nginx in front of the backend).

  From backend/:
    docker compose build frontend; docker compose up -d
    ..\frontend\test-frontend.ps1                 # or: -BaseUrl http://localhost:8080

  Works in Windows PowerShell 5.1 and PowerShell 7. Asks for an admin email and
  password; nothing is stored. Exit code = number of failed checks.
#>
param(
  [string]$BaseUrl = "http://localhost:8080"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

$BaseUrl = $BaseUrl.TrimEnd("/")

# One HttpClient for everything. Cookies are handled by hand so we can inspect Set-Cookie.
$handler = New-Object System.Net.Http.HttpClientHandler
$handler.UseCookies = $false
$handler.AllowAutoRedirect = $false
$client = New-Object System.Net.Http.HttpClient($handler)
$client.Timeout = [TimeSpan]::FromSeconds(180)

$results = New-Object System.Collections.Generic.List[object]

function Add-Result([int]$Number, [string]$Name, [bool]$Ok, [string]$Detail) {
  $results.Add([pscustomobject]@{ Number = $Number; Name = $Name; Ok = $Ok; Detail = $Detail })
  $label = if ($Ok) { "PASS" } else { "FAIL" }
  $color = if ($Ok) { "Green" } else { "Red" }
  Write-Host ("[{0}] {1}. {2}" -f $label, $Number, $Name) -ForegroundColor $color
  if ($Detail) { Write-Host ("       " + $Detail) }
}

function Send([string]$Method, [string]$Path, $Content = $null, [hashtable]$Headers = @{}) {
  $req = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::new($Method), "$BaseUrl$Path")
  foreach ($k in $Headers.Keys) { [void]$req.Headers.TryAddWithoutValidation($k, [string]$Headers[$k]) }
  if ($null -ne $Content) { $req.Content = $Content }
  $res = $client.SendAsync($req).GetAwaiter().GetResult()
  $body = $res.Content.ReadAsStringAsync().GetAwaiter().GetResult()
  $mediaType = if ($res.Content.Headers.ContentType) { $res.Content.Headers.ContentType.MediaType } else { "" }
  $cacheControl = if ($res.Headers.CacheControl) { $res.Headers.CacheControl.ToString() } else { "" }
  $setCookies = @()
  $values = $null
  if ($res.Headers.TryGetValues("Set-Cookie", [ref]$values)) { $setCookies = @($values) }
  $server = if ($res.Headers.Server) { $res.Headers.Server.ToString() } else { "" }
  [pscustomobject]@{
    Status = [int]$res.StatusCode; Body = $body; MediaType = $mediaType
    CacheControl = $cacheControl; SetCookies = $setCookies; Server = $server
  }
}

function Json([string]$Text) { try { return $Text | ConvertFrom-Json } catch { return $null } }

function Run([int]$Number, [string]$Name, [scriptblock]$Check) {
  try { & $Check } catch { Add-Result $Number $Name $false ("Error: " + $_.Exception.Message) }
}

Write-Host "Testing $BaseUrl`n"

# 1. Health check
Run 1 "GET /healthz -> 200" {
  $r = Send "GET" "/healthz"
  Add-Result 1 "GET /healthz -> 200" ($r.Status -eq 200) "status $($r.Status)"
}

# 2. App shell
$indexHtml = ""
Run 2 "GET / -> 200 HTML with the root div" {
  $r = Send "GET" "/"
  $script:indexHtml = $r.Body
  $ok = $r.Status -eq 200 -and $r.MediaType -eq "text/html" -and $r.Body -match '<div id="root"'
  Add-Result 2 "GET / -> 200 HTML with the root div" $ok "status $($r.Status), $($r.MediaType)"
}

# 3. Deep link (SPA fallback)
Run 3 "Deep link /timesheets/<id> -> 200 HTML" {
  $r = Send "GET" "/timesheets/00000000-0000-0000-0000-000000000000"
  $ok = $r.Status -eq 200 -and $r.MediaType -eq "text/html" -and $r.Body -match '<div id="root"'
  Add-Result 3 "Deep link /timesheets/<id> -> 200 HTML" $ok "status $($r.Status), $($r.MediaType)"
}

# 4. core-service through /api (prefix removed)
Run 4 "GET /api/health -> 200 JSON from core-service" {
  $r = Send "GET" "/api/health"
  $ok = $r.Status -eq 200 -and $r.MediaType -eq "application/json" -and $null -ne (Json $r.Body)
  Add-Result 4 "GET /api/health -> 200 JSON from core-service" $ok "status $($r.Status), body $($r.Body)"
}

# 5-7. Sign in, refresh with the cookie, /api/me
$email = Read-Host "Admin email"
$secure = Read-Host "Admin password" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

$refreshCookie = $null
$accessToken = $null

Run 5 "POST /auth/login -> 200, HttpOnly cookie with Path=/auth" {
  $payload = @{ email = $email; password = $password } | ConvertTo-Json -Compress
  $content = New-Object System.Net.Http.StringContent($payload, [Text.Encoding]::UTF8, "application/json")
  $r = Send "POST" "/auth/login" $content
  $cookie = $r.SetCookies | Where-Object { $_ -match '(?i)path=/auth' -and $_ -match '(?i)httponly' } | Select-Object -First 1
  $token = (Json $r.Body).access_token
  if ($cookie) { $script:refreshCookie = ($cookie -split ";")[0].Trim() }
  if ($token) { $script:accessToken = $token }
  $ok = $r.Status -eq 200 -and [bool]$cookie -and [bool]$token
  $detail = "status $($r.Status); Set-Cookie: " + (($r.SetCookies | ForEach-Object { ($_ -split ";", 2)[1] }) -join " | ")
  Add-Result 5 "POST /auth/login -> 200, HttpOnly cookie with Path=/auth" $ok $detail
}
$password = $null

Run 6 "POST /auth/refresh with the cookie -> 200 new token" {
  if (-not $refreshCookie) { Add-Result 6 "POST /auth/refresh with the cookie -> 200 new token" $false "no refresh cookie from check 5"; return }
  $r = Send "POST" "/auth/refresh" $null @{ Cookie = $refreshCookie }
  $token = (Json $r.Body).access_token
  if ($token) { $script:accessToken = $token }
  Add-Result 6 "POST /auth/refresh with the cookie -> 200 new token" ($r.Status -eq 200 -and [bool]$token) "status $($r.Status)"
}

Run 7 "GET /api/me with the token -> 200 with the role" {
  if (-not $accessToken) { Add-Result 7 "GET /api/me with the token -> 200 with the role" $false "no access token"; return }
  $r = Send "GET" "/api/me" $null @{ Authorization = "Bearer $accessToken" }
  $role = (Json $r.Body).role
  Add-Result 7 "GET /api/me with the token -> 200 with the role" ($r.Status -eq 200 -and [bool]$role) "status $($r.Status), role '$role'"
}

# 8. Caching headers
Run 8 "Cache-Control: immutable on /assets/*.js, no-cache on index.html" {
  if (-not $indexHtml) { $script:indexHtml = (Send "GET" "/").Body }
  $m = [regex]::Match($indexHtml, 'src="(/assets/[^"]+\.js)"')
  if (-not $m.Success) { Add-Result 8 "Cache-Control: immutable on /assets/*.js, no-cache on index.html" $false "no /assets/*.js in index.html"; return }
  $asset = Send "GET" $m.Groups[1].Value
  $index = Send "GET" "/"
  $assetOk = $asset.Status -eq 200 -and $asset.CacheControl -match "immutable" -and $asset.CacheControl -match "max-age=31536000"
  $indexOk = $index.CacheControl -match "no-cache"
  Add-Result 8 "Cache-Control: immutable on /assets/*.js, no-cache on index.html" ($assetOk -and $indexOk) `
    ("asset '$($asset.CacheControl)'; index '$($index.CacheControl)'")
}

# 9. A ~20 MB upload must get past nginx (the backend may refuse the size; that's fine)
Run 9 "~20 MB upload through /api/uploads: no 413 from nginx" {
  if (-not $accessToken) { Add-Result 9 "~20 MB upload through /api/uploads: no 413 from nginx" $false "no access token"; return }
  $bytes = New-Object byte[] (20MB)
  $file = New-Object System.Net.Http.ByteArrayContent(,$bytes)
  $file.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("text/plain")
  $form = New-Object System.Net.Http.MultipartFormDataContent
  $form.Add($file, "files", "nginx-size-check.txt")
  $r = Send "POST" "/api/uploads" $form @{ Authorization = "Bearer $accessToken" }
  # nginx's own 413 is an HTML page; a backend answer (even 413) is JSON.
  $nginx413 = $r.Status -eq 413 -and $r.MediaType -ne "application/json"
  $detail = "status $($r.Status), $($r.MediaType)"
  if ($r.Status -ge 200 -and $r.Status -lt 300) { $detail += " (the backend accepted it: delete that test submission)" }
  Add-Result 9 "~20 MB upload through /api/uploads: no 413 from nginx" (-not $nginx413 -and $r.Status -ne 0) $detail
}

$failed = @($results | Where-Object { -not $_.Ok }).Count
$passed = $results.Count - $failed
Write-Host ""
$summaryColor = if ($failed -eq 0) { "Green" } else { "Red" }
Write-Host ("Total: {0} passed, {1} failed (of {2})" -f $passed, $failed, $results.Count) -ForegroundColor $summaryColor
$client.Dispose()
exit $failed
