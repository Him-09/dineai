# Create DigitalOcean Upload Package
# This script creates a clean package for DigitalOcean deployment

Write-Host "Creating DigitalOcean deployment package..." -ForegroundColor Green

# Create deployment directory
$deployDir = "digitalocean-deploy"
if (Test-Path $deployDir) {
    Remove-Item $deployDir -Recurse -Force
}
New-Item -ItemType Directory -Path $deployDir | Out-Null

# Copy essential files
$filesToCopy = @(
    "src",
    "static/app", 
    ".do",
    "Dockerfile",
    "requirements.txt", 
    ".dockerignore",
    "Procfile"
)

Write-Host "Copying essential files..." -ForegroundColor Yellow

foreach ($file in $filesToCopy) {
    if (Test-Path $file) {
        if (Test-Path $file -PathType Container) {
            # It's a directory
            Copy-Item $file -Destination $deployDir -Recurse
            Write-Host "✅ Copied directory: $file" -ForegroundColor Green
        } else {
            # It's a file
            Copy-Item $file -Destination $deployDir
            Write-Host "✅ Copied file: $file" -ForegroundColor Green
        }
    } else {
        Write-Host "⚠️  Not found: $file" -ForegroundColor Yellow
    }
}

# Check package size
$packageSize = Get-ChildItem $deployDir -Recurse | Where-Object {!$_.PSIsContainer} | Measure-Object -Property Length -Sum
Write-Host "`nPackage ready!" -ForegroundColor Green
Write-Host "📁 Location: $deployDir" -ForegroundColor Cyan
Write-Host "📊 Size: $([math]::Round($packageSize.Sum / 1MB, 2)) MB" -ForegroundColor Cyan
Write-Host "📦 Files: $($packageSize.Count)" -ForegroundColor Cyan

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Zip the '$deployDir' folder" -ForegroundColor White
Write-Host "2. Upload to DigitalOcean App Platform" -ForegroundColor White
Write-Host "3. Configure environment variables" -ForegroundColor White

# Create zip file
Write-Host "`nCreating zip file..." -ForegroundColor Yellow
$zipPath = "dineai-digitalocean-deploy.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path "$deployDir\*" -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host "✅ Created: $zipPath" -ForegroundColor Green
Write-Host "📤 Ready to upload to DigitalOcean!" -ForegroundColor Green