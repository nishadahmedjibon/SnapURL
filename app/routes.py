import random
import string
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .database import get_db
from .models import URL, Analytics
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

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

    return {
        "original_url": request.original_url,
        "short_url": f"{BASE_URL}/{short_code}",
        "short_code": short_code
    }


@router.get("/{short_code}")
def redirect_url(short_code: str, request: Request, db: Session = Depends(get_db)):
    # Find URL in database
    url_entry = db.query(URL).filter(URL.short_code == short_code).first()
    if not url_entry:
        raise HTTPException(status_code=404, detail="Short URL not found")

    # Save analytics
    analytics = Analytics(
        url_id=url_entry.id,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent")
    )
    db.add(analytics)

    # Update click count
    url_entry.click_count += 1
    db.commit()

    # Redirect to original URL
    return RedirectResponse(url=url_entry.original_url)


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
