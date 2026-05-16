"""
Migration script: imports real Oman property listings from cleaned_full_data
into the Flask app's Property and PropertyImage tables.
"""
import sqlite3
import os
from app import create_app
from extensions import db
from models import User, Property, PropertyImage

# ── paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.abspath(os.path.dirname(__file__))
SOURCE_DB  = os.path.join(BASE_DIR, "instance", "database", "realestate.db")

# ── subcategory  →  Property.type mapping ────────────────────────────────────
CATEGORY_MAP = {
    "villas for sale":       "Villa",
    "villas for rent":       "Villa",
    "apartments for sale":   "Apartment",
    "apartments for rent":   "Apartment",
    "lands for sale":        "Land",
    "lands for rent":        "Land",
    "offices for sale":      "Office",
    "offices for rent":      "Office",
    "commercial for sale":   "Commercial",
    "commercial for rent":   "Commercial",
    "buildings for sale":    "Building",
    "buildings for rent":    "Building",
    "townhouses for sale":   "Townhouse",
    "townhouses for rent":   "Townhouse",
}

def map_type(subcategory: str) -> str:
    if not subcategory:
        return "Other"
    key = subcategory.strip().lower()
    for k, v in CATEGORY_MAP.items():
        if k in key:
            return v
    return "Other"

def extract_size(title: str, surface_id) -> float:
    """Try to get size in m² from surface highlight or title."""
    if surface_id:
        try:
            return float(str(surface_id).replace(",", ""))
        except Exception:
            pass
    # fall back: scan title for e.g. "426 m2"
    import re
    m = re.search(r"(\d[\d,]*)\s*m2", title or "", re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except Exception:
            pass
    return 0.0


app = create_app()

with app.app_context():
    # Make sure Flask app tables exist
    db.create_all()

    # Get (or create) the agent user that will own imported listings
    agent = User.query.filter_by(email="agent@smartestate.com").first()
    if not agent:
        agent = User(username="agent_john", email="agent@smartestate.com", role="agent")
        agent.set_password("agent123")
        db.session.add(agent)
        db.session.commit()
        print("Created default agent user.")

    # ── read rows from source DB ──────────────────────────────────────────────
    src_conn = sqlite3.connect(SOURCE_DB)
    src_conn.row_factory = sqlite3.Row
    src_cur  = src_conn.cursor()

    src_cur.execute("""
        SELECT
            id,
            title,
            fullDescription,
            descriptionPreview,
            price,
            city,
            neighborhood,
            subcategory,
            imageUrl,
            "allImages/0"  AS img0,
            "allImages/1"  AS img1,
            "allImages/2"  AS img2,
            "allImages/3"  AS img3,
            "allImages/4"  AS img4,
            "highlights/Surface/0/id" AS surface,
            "highlights/Rooms/0/value" AS bedrooms,
            "highlights/Bathrooms/0/value" AS bathrooms
        FROM cleaned_full_data
    """)
    rows = src_cur.fetchall()
    src_conn.close()

    imported = 0
    skipped  = 0

    for row in rows:
        title = (row["title"] or "").strip()
        if not title:
            skipped += 1
            continue

        price = 0.0
        try:
            price = float(row["price"] or 0)
        except Exception:
            pass

        # Build location string
        city         = row["city"] or ""
        neighborhood = row["neighborhood"] or ""
        location     = f"{city}, {neighborhood}".strip(", ") if neighborhood else city

        description = (row["fullDescription"] or row["descriptionPreview"] or
                       f"{title} located in {location}.")

        prop_type = map_type(row["subcategory"])
        size      = extract_size(title, row["surface"])

        # Collect image URLs (skip empties)
        image_urls = []
        for col in ["imageUrl", "img0", "img1", "img2", "img3", "img4"]:
            url = row[col]
            if url and url.startswith("http") and url not in image_urls:
                image_urls.append(url)

        # Create property record
        prop = Property(
            title       = title,
            description = description,
            price       = price,
            location    = location,
            type        = prop_type,
            size        = size if size else None,
            agent_id    = agent.id,
        )
        db.session.add(prop)
        db.session.flush()  # get prop.id before committing

        # Add image records (store the full URL as filename — routes must handle this)
        for img_url in image_urls[:5]:   # max 5 images per property
            img = PropertyImage(image_filename=img_url, property_id=prop.id)
            db.session.add(img)

        imported += 1

    db.session.commit()
    print(f"\n✅  Import complete: {imported} properties imported, {skipped} skipped.")
    print(f"    Total properties in DB: {Property.query.count()}")
