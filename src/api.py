from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import uuid
import logging
from datetime import datetime
import os

# Import the agent logic
from .agent import run_agent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Restaurant AI Agent API",
    description="A REST API for the Restaurant AI Agent with RAG capabilities",
    version="1.0.0"
)

# Request/Response models
class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    thread_id: str
    timestamp: str

class HealthResponse(BaseModel):
    status: str
    message: str

# Store for active conversations (in production, use a proper database)
active_threads = {}

# Move API info to /api endpoint instead of root
@app.get("/api", response_model=dict)
async def api_info():
    """API root endpoint with information"""
    return {
        "message": "Restaurant AI Agent API",
        "version": "1.0.0",
        "endpoints": {
            "chat": "/api/chat",
            "health": "/api/health",
            "docs": "/docs",
            "demo": "/demo"
        }
    }

@app.get("/api/health", response_model=HealthResponse)
async def api_health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        message="Restaurant AI Agent API is running"
    )

@app.post("/api/chat", response_model=ChatResponse)
async def api_chat_with_agent(request: ChatRequest):
    """
    Chat with the Restaurant AI Agent
    
    Args:
        request: ChatRequest containing message and optional thread_id
        
    Returns:
        ChatResponse with agent's response, thread_id, and timestamp
    """
    try:
        # Generate thread_id if not provided
        thread_id = request.thread_id or str(uuid.uuid4())
        
        # Log the request
        logger.info(f"Processing chat request for thread {thread_id}: {request.message}")
        
        # Validate input
        if not request.message or not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        # Run the agent
        agent_response = run_agent(request.message.strip(), thread_id)
        
        # Store thread info (for tracking active conversations)
        active_threads[thread_id] = {
            "last_activity": datetime.now().isoformat(),
            "message_count": active_threads.get(thread_id, {}).get("message_count", 0) + 1
        }
        
        # Log the response
        logger.info(f"Agent response for thread {thread_id}: {agent_response[:100]}...")
        
        return ChatResponse(
            response=agent_response,
            thread_id=thread_id,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/api/threads", response_model=dict)
async def api_get_active_threads():
    """Get information about active conversation threads"""
    return {
        "active_threads": len(active_threads),
        "threads": active_threads
    }

@app.delete("/api/threads/{thread_id}")
async def api_clear_thread(thread_id: str):
    """Clear a specific conversation thread"""
    if thread_id in active_threads:
        del active_threads[thread_id]
        return {"message": f"Thread {thread_id} cleared successfully"}
    else:
        raise HTTPException(status_code=404, detail="Thread not found")

@app.delete("/api/threads")
async def api_clear_all_threads():
    """Clear all conversation threads"""
    cleared_count = len(active_threads)
    active_threads.clear()
    return {"message": f"Cleared {cleared_count} threads"}

# Add CORS middleware for production
from fastapi.middleware.cors import CORSMiddleware

# Get allowed origins from environment
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
environment = os.getenv("ENVIRONMENT", "development")

if environment == "production":
    # Production CORS settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )
else:
    # Development CORS settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount static files to serve the built frontend
static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    
    # Mount the built React app
    react_built = os.path.join(static_path, "app")
    if os.path.exists(react_built):
        app.mount("/app", StaticFiles(directory=react_built, html=True), name="react_app")
        
        # Mount React assets at root level for proper serving
        react_assets = os.path.join(react_built, "assets")
        if os.path.exists(react_assets):
            app.mount("/assets", StaticFiles(directory=react_assets), name="react_assets")
            
        # Mount voice files at root level for demo functionality
        voice_path = os.path.join(react_built, "voice")
        if os.path.exists(voice_path):
            app.mount("/voice", StaticFiles(directory=voice_path), name="voice_files")

# Serve favicon files from root
@app.get("/favicon-32x32.png", include_in_schema=False)
async def serve_favicon_32():
    """Serve 32x32 favicon from root"""
    favicon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app", "favicon-32x32.png")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/favicon-16x16.png", include_in_schema=False)
async def serve_favicon_16():
    """Serve 16x16 favicon from root"""
    favicon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app", "favicon-16x16.png")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/utensils.png", include_in_schema=False)
async def serve_utensils_favicon():
    """Serve utensils.png favicon from root"""
    favicon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app", "utensils.png")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/uten.svg", include_in_schema=False)
async def serve_uten_favicon():
    """Serve uten.svg favicon from root"""
    favicon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app", "uten.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon_ico():
    """Serve favicon.ico from root"""
    favicon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/favicon.svg", include_in_schema=False)
async def serve_favicon_svg():
    """Serve favicon.svg from root"""
    favicon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app", "favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Favicon not found")

# Serve React app at root for production
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend():
    """Serve the React frontend application"""
    root = os.path.dirname(os.path.dirname(__file__))
    static_dir = os.path.join(root, "static")
    react_index = os.path.join(static_dir, "app", "index.html")
    
    if os.path.exists(react_index):
        with open(react_index, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    
    # Fallback API info
    return {
        "message": "Restaurant AI Agent API",
        "version": "1.0.0",
        "endpoints": {
            "chat": "/api/chat",
            "health": "/api/health",
            "docs": "/docs",
            "demo": "/demo"
        }
    }

# Demo page endpoint
@app.get("/demo", response_class=HTMLResponse)
async def demo_page():
    """Serve the React demo app if built, otherwise the legacy static page."""
    root = os.path.dirname(os.path.dirname(__file__))
    static_dir = os.path.join(root, "static")
    react_index = os.path.join(static_dir, "app", "index.html")
    legacy_index = os.path.join(static_dir, "index.html")

    try_paths = [react_index, legacy_index]
    for p in try_paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())

    return HTMLResponse(content="""
    <html>
        <head><title>Demo Not Found</title></head>
        <body>
            <h1>Demo page not found</h1>
            <p>Build the React app with <code>cd web && npm install && npm run build</code>.</p>
            <p>Or use the legacy demo at <code>/static/index.html</code> if present.</p>
            <ul>
                <li><a href="/docs">API Documentation</a></li>
                <li><a href="/health">Health Check</a></li>
            </ul>
        </body>
    </html>
    """, status_code=404)

# Catch-all route for React Router (must be last)
@app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def catch_all(full_path: str):
    """Catch-all route to serve React app for client-side routing"""
    # Don't intercept API routes
    if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
        return {"error": "Not found"}
    
    root = os.path.dirname(os.path.dirname(__file__))
    static_dir = os.path.join(root, "static")
    react_index = os.path.join(static_dir, "app", "index.html")
    
    if os.path.exists(react_index):
        with open(react_index, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    
    return {"error": "Frontend not built"}

@app.get("/api/stats")
async def get_api_stats():
    """Get API usage statistics for the demo"""
    from .db import supabase
    
    try:
        # Get total reservations count
        reservations_result = supabase.table("bookings").select("*").execute()
        total_reservations = len(reservations_result.data) if reservations_result.data else 0
        
        return {
            "total_reservations": total_reservations,
            "active_threads": len(active_threads),
            "api_status": "healthy",
            "agent_capabilities": [
                "Table Booking",
                "Menu Search", 
                "Reservation Management",
                "Availability Check",
                "FAQ Support"
            ]
        }
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return {
            "total_reservations": "N/A",
            "active_threads": len(active_threads),
            "api_status": "limited",
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
