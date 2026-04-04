# Hook script to lint Python files with ruff/ty and TypeScript files with eslint after edits
# PowerShell version for Windows compatibility

# Read JSON input from stdin
# PowerShell automatically populates $input for pipeline input
$jsonInput = $null
if ($input) {
    # If input comes from pipeline
    $jsonInput = $input | Out-String
} else {
    # Try reading from stdin directly
    try {
        $jsonInput = [Console]::In.ReadToEnd()
    } catch {
        # If that fails, try reading line by line
        $lines = @()
        while ($line = [Console]::In.ReadLine()) {
            $lines += $line
        }
        $jsonInput = $lines -join "`n"
    }
}

# Parse JSON
$filePath = $null
try {
    if (-not [string]::IsNullOrWhiteSpace($jsonInput)) {
        $json = $jsonInput | ConvertFrom-Json
        $filePath = $json.file_path
    }
} catch {
    # If JSON parsing fails, try to extract file_path manually
    if ($jsonInput -match '"file_path"\s*:\s*"([^"]+)"') {
        $filePath = $matches[1]
    }
}

# Check if file path is empty
if ([string]::IsNullOrWhiteSpace($filePath)) {
    exit 0
}

# Normalize path separators
$filePath = $filePath -replace '\\', '/'

# Get the workspace root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$backendDir = Join-Path $workspaceRoot "backend"
$frontendDir = Join-Path $workspaceRoot "frontend"

# Check if file is a Python file
if ($filePath -match '\.py$') {
    # Python file - check if it's in backend
    $pyprojectPath = Join-Path $backendDir "pyproject.toml"
    if (-not (Test-Path $pyprojectPath)) {
        exit 0
    }

    # Check if the edited file is within the backend directory structure
    $backendPathNormalized = $backendDir -replace '\\', '/'
    $workspacePathNormalized = $workspaceRoot -replace '\\', '/'
    if ($filePath -notlike "$backendPathNormalized*" -and $filePath -notlike "$workspacePathNormalized/backend*") {
        exit 0
    }

    # Change to backend directory
    Push-Location $backendDir
    if ($LASTEXITCODE -ne 0) {
        exit 0
    }

    try {
        # Get relative path from backend directory
        $relPath = $filePath -replace [regex]::Escape($backendPathNormalized + "/"), ""
        $relPath = $relPath -replace "^/", ""

        # Run ruff check with --fix on the specific file
        Write-Host "Running ruff check on $relPath..." -ForegroundColor Yellow
        & uv run ruff check $relPath --fix 2>&1

        # Run ruff format on the specific file
        Write-Host "Running ruff format on $relPath..." -ForegroundColor Yellow
        & uv run ruff format $relPath 2>&1

        # Run ty check (checks whole project, but that's fine)
        # Only run if the file is in the src directories configured in ty.toml
        if ($relPath -like "tunetrove_backend/*" -or $relPath -like "tests/*") {
            Write-Host "Running ty check..." -ForegroundColor Yellow
            & uv run ty check 2>&1 | Select-Object -First 50
        }
    } finally {
        Pop-Location
    }

# Check if file is a TypeScript file
} elseif ($filePath -match '\.(ts|tsx)$') {
    # TypeScript file - check if it's in frontend
    $packageJsonPath = Join-Path $frontendDir "package.json"
    if (-not (Test-Path $packageJsonPath)) {
        exit 0
    }

    # Check if the edited file is within the frontend directory structure
    $frontendPathNormalized = $frontendDir -replace '\\', '/'
    $workspacePathNormalized = $workspaceRoot -replace '\\', '/'
    if ($filePath -notlike "$frontendPathNormalized*" -and $filePath -notlike "$workspacePathNormalized/frontend*") {
        exit 0
    }

    # Change to frontend directory
    Push-Location $frontendDir
    if ($LASTEXITCODE -ne 0) {
        exit 0
    }

    try {
        # Get relative path from frontend directory
        $relPath = $filePath -replace [regex]::Escape($frontendPathNormalized + "/"), ""
        $relPath = $relPath -replace "^/", ""

        # Run eslint on the specific file with --fix for auto-fixing
        Write-Host "Running eslint on $relPath..." -ForegroundColor Yellow
        & npx eslint $relPath --fix 2>&1
    } finally {
        Pop-Location
    }

} else {
    # Not a supported file type, exit silently
    exit 0
}

exit 0
