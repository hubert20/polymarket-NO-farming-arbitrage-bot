# Backdate all commits evenly from StartDate to EndDate (UTC).
param(
    [string]$StartDate = "2026-04-04T09:00:00Z",
    [string]$EndDate = "2026-07-06T17:00:00Z"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Set-Location ..

$commits = @(git rev-list --reverse HEAD)
if ($commits.Count -eq 0) { throw "No commits found." }

$start = [DateTimeOffset]::Parse($StartDate)
$end = [DateTimeOffset]::Parse($EndDate)
$spanSec = ($end.ToUnixTimeSeconds() - $start.ToUnixTimeSeconds())

$lines = New-Object System.Collections.Generic.List[string]
[void]$lines.Add("case `"`$GIT_COMMIT`" in")
for ($i = 0; $i -lt $commits.Count; $i++) {
    $ratio = if ($commits.Count -eq 1) { 0 } else { $i / ($commits.Count - 1) }
    $epoch = $start.ToUnixTimeSeconds() + [long][math]::Round($spanSec * $ratio)
    $hash = $commits[$i]
    [void]$lines.Add("$hash)")
    [void]$lines.Add("  export GIT_AUTHOR_DATE=`"$epoch`"")
    [void]$lines.Add("  export GIT_COMMITTER_DATE=`"$epoch`"")
    [void]$lines.Add("  ;;")
}
[void]$lines.Add("esac")

$filterPath = Join-Path (Get-Location) "scripts\git-date-filter.sh"
[System.IO.File]::WriteAllText($filterPath, ($lines -join "`n") + "`n")

# Git Bash path: C:/Users/... (no drive colon escape needed for source)
$bashFilter = ($filterPath -replace '\\', '/')
$bashFilter = $bashFilter -replace '^([A-Za-z]):', '/$1'
$bashFilter = $bashFilter.ToLower()

$bash = "C:\Program Files\Git\bin\bash.exe"
$envFilter = ". `"$bashFilter`""
$env:GIT_FILTER_BRANCH_SQUELCH_WARNING = "1"

& git -c filter.branch.simplify=false filter-branch -f --env-filter $envFilter HEAD

Remove-Item $filterPath -Force -ErrorAction SilentlyContinue
if (Test-Path .git/refs/original) {
    git for-each-ref --format="%(refname)" refs/original | ForEach-Object { git update-ref -d $_ }
}

Write-Host "`nCommit dates (first 5):"
git log --reverse --format="%h %ad %s" --date=short | Select-Object -First 5
Write-Host "`nCommit dates (last 5):"
git log --format="%h %ad %s" --date=short | Select-Object -First 5
