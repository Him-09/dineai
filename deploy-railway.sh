#!/bin/bash

# Railway Deployment Script for Restaurant AI Agent
# This script helps prepare and deploy the application to Railway

echo "🚂 Railway Deployment Script for Restaurant AI Agent"
echo "=================================================="

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Please install it first:"
    echo "   npm install -g @railway/cli"
    echo "   or"
    echo "   curl -fsSL https://railway.app/install.sh | sh"
    exit 1
fi

echo "✅ Railway CLI found"

# Check if user is logged in
if ! railway whoami &> /dev/null; then
    echo "🔐 Please log in to Railway first:"
    echo "   railway login"
    exit 1
fi

echo "✅ Railway authentication verified"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "📝 Please edit .env file with your actual API keys before deploying"
    echo "   Required: OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY"
    read -p "Press Enter after you've updated .env file..."
fi

# Check if static/app exists (built frontend)
if [ ! -d "static/app" ]; then
    echo "❌ Built frontend not found at static/app"
    echo "   Please build your frontend first:"
    echo "   cd web && npm install && npm run build"
    echo "   Then copy the dist folder to static/app"
    exit 1
fi

echo "✅ Built frontend found"

# Initialize Railway project if not exists
if [ ! -f "railway.toml" ]; then
    echo "🚀 Initializing Railway project..."
    railway init
fi

# Set environment variables
echo "🔧 Setting up environment variables..."
echo "Please set the following environment variables in Railway dashboard:"
echo "1. OPENAI_API_KEY"
echo "2. SUPABASE_URL" 
echo "3. SUPABASE_KEY"
echo "4. SUPABASE_SERVICE_ROLE_KEY (optional)"
echo "5. LIVEKIT_URL (optional, for voice features)"
echo "6. LIVEKIT_API_KEY (optional, for voice features)"
echo "7. LIVEKIT_API_SECRET (optional, for voice features)"
echo "8. ALLOWED_ORIGINS (your domain, e.g., https://yourapp.railway.app)"
echo "9. ENVIRONMENT=production"

read -p "Have you set all required environment variables in Railway? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "Please set environment variables first using:"
    echo "   railway variables set OPENAI_API_KEY=your_key_here"
    echo "   railway variables set SUPABASE_URL=your_url_here"
    echo "   etc..."
    exit 1
fi

# Deploy
echo "🚀 Deploying to Railway..."
railway deploy

echo "✅ Deployment complete!"
echo "🌐 Your app should be available at your Railway app URL"
echo "📊 Check deployment status: railway status"
echo "📋 View logs: railway logs"