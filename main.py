from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import os

# TODO: Add routers for different features

app = FastAPI(
    title="Raahi Backend API",
    description="API for the Raahi travel companion app.",
    version="0.1.0",
)

# Configure CORS (Cross-Origin Resource Sharing)
# This allows your frontend to communicate with the backend.
origins = [
    "http://localhost",
    "http://localhost:8080",  # Frontend server port
    "http://127.0.0.1:8080",  # Alternative frontend server address
    "http://localhost:8000",  # FastAPI server port
    "http://127.0.0.1:8000",  # Alternative FastAPI server address
    # Add your deployed frontend URL here later
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["Root"])
def read_root():
    """Redirect to the frontend index.html"""
    return RedirectResponse(url="/frontend/index.html")

# Include the routers
from api.routers import auth, trips, weather, wishlist, ai, journal, packing, gphotos

# Mount all routers with the /api prefix
app.include_router(auth.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(weather.router, prefix="/api")
app.include_router(wishlist.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(journal.router, prefix="/api")
app.include_router(packing.router, prefix="/api")
app.include_router(gphotos.router, prefix="/api")

# Mount the frontend static files
# Check if the frontend directory exists relative to the current file
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

# TODO: Add other routers

# TODO: Include the routers once they are created
# from api.routers import auth, trips, ...
# app.include_router(auth.router)
# app.include_router(trips.router) 