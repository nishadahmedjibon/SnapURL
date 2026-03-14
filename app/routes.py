import random
import string
import redis
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .database import get_db
from .models import URL, Analytics
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Redis connection
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True
)

# --- Helper function ---
def generate_short_code(length=6):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=length))

# --- Request body model ---
class URLRequest(BaseModel):
    original_url: str

# --- Routes ---

@router.post("/shorten")
def shorten_url(request: URLRequest, db: Session = Depends(get_db)):
    # Generate unique short code
    short_code = generate_short_code()
    while db.query(URL).filter(URL.short_code == short_code).first():
        short_code = generate_short_code()

    # Save to database
    new_url = URL(
        original_url=request.original_url,
        short_code=short_code
    )
    db.add(new_url)
    db.commit()
    db.refresh(new_url)

    # Save to Redis immediately
    redis_client.setex(f"url:{short_code}", 86400, request.original_url)

    return {
        "original_url": request.original_url,
        "short_url": f"{BASE_URL}/{short_code}",
        "short_code": short_code
    }


@router.get("/analytics/{short_code}")
def get_analytics(short_code: str, db: Session = Depends(get_db)):
    url_entry = db.query(URL).filter(URL.short_code == short_code).first()
    if not url_entry:
        raise HTTPException(status_code=404, detail="Short URL not found")

    return {
        "original_url": url_entry.original_url,
        "short_url": f"{BASE_URL}/{short_code}",
        "total_clicks": url_entry.click_count,
        "created_at": url_entry.created_at,
        "recent_clicks": [
            {
                "clicked_at": a.clicked_at,
                "ip_address": a.ip_address,
                "user_agent": a.user_agent
            }
            for a in url_entry.analytics[-10:]
        ]
    }


@router.get("/{short_code}")
def redirect_url(short_code: str, request: Request, db: Session = Depends(get_db)):

    # Step 1 — Check Redis first (fast)
    cached_url = redis_client.get(f"url:{short_code}")
    if cached_url:
        url_entry = db.query(URL).filter(URL.short_code == short_code).first()
        if url_entry:
            url_entry.click_count += 1
            analytics = Analytics(
                url_id=url_entry.id,
                ip_address=request.client.host,
                user_agent=request.headers.get("user-agent")
            )
            db.add(analytics)
            db.commit()
        return RedirectResponse(url=cached_url)

    # Step 2 — Not in Redis, check PostgreSQL
    url_entry = db.query(URL).filter(URL.short_code == short_code).first()
    if not url_entry:
        raise HTTPException(status_code=404, detail="Short URL not found")

    # Step 3 — Save to Redis for next time
    redis_client.setex(f"url:{short_code}", 86400, url_entry.original_url)

    # Step 4 — Save analytics
    analytics = Analytics(
        url_id=url_entry.id,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent")
    )
    db.add(analytics)
    url_entry.click_count += 1
    db.commit()

    return RedirectResponse(url=url_entry.original_url)
