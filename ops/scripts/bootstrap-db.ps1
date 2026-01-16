param(
  [string]$PgUser = 'tradesync',
  [string]$PgDb   = 'tradesync'
)

Write-Host '[bootstrap-db] Waiting for postgres to be healthy...'

# Find the postgres container (respecting our compose project/environment)
$cid = (docker compose --env-file ..\.env -f .\compose.infra.yml ps -q postgres)
if (-not $cid) {
  Write-Error '[bootstrap-db] Could not find postgres container. Is compose up?'
  exit 1
}

# Simple wait loop for health=healthy
for ($i=1; $i -le 60; $i++) {
  $status = (docker inspect -f "{{.State.Health.Status}}" $cid) 2>$null
  if ($status -eq "healthy") { break }
  Start-Sleep -Seconds 2
}
if ($status -ne "healthy") {
  Write-Error "[bootstrap-db] Postgres not healthy (status=$status)."
  exit 1
}

# Apply schema by piping the SQL file into psql inside the container
$schemaPath = Join-Path $PSScriptRoot '..\sql\schema.sql'
$schemaPath = (Resolve-Path $schemaPath).Path
Write-Host "[bootstrap-db] Applying schema from $schemaPath ..."
type "$schemaPath" | docker exec -i $cid psql -U $PgUser -d $PgDb

if ($LASTEXITCODE -ne 0) {
  Write-Error '[bootstrap-db] Schema apply failed.'
  exit 1
}
Write-Host '[bootstrap-db] Done.'
