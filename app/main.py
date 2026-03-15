from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .database import engine, Base
from .routes import router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SnapURL",
    description="A fast and simple URL shortener with analytics",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "SnapURL is running 🚀"}

@app.get("/")
def serve_home():
    return FileResponse("static/index.html")

@app.get("/analytics.html")
def serve_analytics():
    return FileResponse("static/analytics.html")

app.include_router(router)
