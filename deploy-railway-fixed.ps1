# Railway Deployment Script for Restaurant AI Agent (PowerShell)
# This script helps prepare and deploy the application to Railway

Write-Host "Railway Deployment Script for Restaurant AI Agent" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green

# Check if Railway CLI is installed
try {
    railway --version | Out-Null
    Write-Host "Railway CLI found" -ForegroundColor Green
} catch {
    Write-Host "Railway CLI not found. Please install it first:" -ForegroundColor Red
    Write-Host "   npm install -g @railway/cli" -ForegroundColor Yellow
    Write-Host "   or download from: https://railway.app/cli" -ForegroundColor Yellow
    exit 1
}

# Check if user is logged in
try {
    railway whoami | Out-Null
    Write-Host "Railway authentication verified" -ForegroundColor Green
} catch {
    Write-Host "Please log in to Railway first:" -ForegroundColor Yellow
    Write-Host "   railway login" -ForegroundColor Yellow
    exit 1
}

# Check if .env file exists
if (-Not (Test-Path ".env")) {
    Write-Host ".env file not found. Creating from template..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "Please edit .env file with your actual API keys before deploying" -ForegroundColor Yellow
    Write-Host "   Required: OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY" -ForegroundColor Yellow
    Read-Host "Press Enter after you have updated .env file"
}

# Check if static/app exists (built frontend)
if (-Not (Test-Path "static/app")) {
    Write-Host "Built frontend not found at static/app" -ForegroundColor Red
    Write-Host "   Please build your frontend first:" -ForegroundColor Yellow
    Write-Host "   cd web && npm install && npm run build" -ForegroundColor Yellow
    Write-Host "   Then copy the dist folder to static/app" -ForegroundColor Yellow
    exit 1
}

Write-Host "Built frontend found" -ForegroundColor Green

# Initialize Railway project if not exists
if (-Not (Test-Path "railway.toml")) {
    Write-Host "Initializing Railway project..." -ForegroundColor Blue
    railway init
}

# Set environment variables
Write-Host "Setting up environment variables..." -ForegroundColor Blue
Write-Host "Please set the following environment variables in Railway dashboard:" -ForegroundColor Yellow
Write-Host "1. OPENAI_API_KEY" -ForegroundColor Cyan
Write-Host "2. SUPABASE_URL" -ForegroundColor Cyan
Write-Host "3. SUPABASE_KEY" -ForegroundColor Cyan
Write-Host "4. SUPABASE_SERVICE_ROLE_KEY - optional" -ForegroundColor Cyan
Write-Host "5. LIVEKIT_URL - optional for voice features" -ForegroundColor Cyan
Write-Host "6. LIVEKIT_API_KEY - optional for voice features" -ForegroundColor Cyan
Write-Host "7. LIVEKIT_API_SECRET - optional for voice features" -ForegroundColor Cyan
Write-Host "8. ALLOWED_ORIGINS - your domain e.g. https://yourapp.railway.app" -ForegroundColor Cyan
Write-Host "9. ENVIRONMENT=production" -ForegroundColor Cyan

$confirm = Read-Host "Have you set all required environment variables in Railway? (y/n)"
if ($confirm -ne "y") {
    Write-Host "Please set environment variables first using:" -ForegroundColor Yellow
    Write-Host "   railway variables set OPENAI_API_KEY=your_key_here" -ForegroundColor Cyan
    Write-Host "   railway variables set SUPABASE_URL=your_url_here" -ForegroundColor Cyan
    Write-Host "   etc..." -ForegroundColor Cyan
    exit 1
}

# Deploy
Write-Host "Deploying to Railway..." -ForegroundColor Blue
railway deploy

Write-Host "Deployment complete!" -ForegroundColor Green
Write-Host "Your app should be available at your Railway app URL" -ForegroundColor Green
Write-Host "Check deployment status: railway status" -ForegroundColor Yellow
Write-Host "View logs: railway logs" -ForegroundColor Yellow