"""
OMRAN Integration Seed:
  1. Create omran_agent user (role=agent)
  2. Import 500 properties from O.db into main Property table
"""
import sqlite3, os
from app import create_app
from extensions import db
from models import User, Property

DB_DIR  = os.path.join(os.path.dirname(__file__), 'instance', 'database')
O_DB    = os.path.join(DB_DIR, 'O.db')
OMRAN_TAG = '[OMRAN]'

# ── Project specific coordinates ──────────────────────────────────────────
PROJECT_COORDS = {
    'Al Mouj Muscat':         (23.6194, 58.2793),
    'Saraya Bandar Jissah':   (23.5503, 58.6382),
    'Jebel Sifah':            (23.4088, 58.7890),
    'Hawana Salalah':         (17.0322, 54.3003),
    'Yiti Sustainable City':  (23.5300, 58.6700),
}

CITY_COORDS = {
    'muscat':         (23.5880, 58.3829),
    'al amerat':      (23.5100, 58.5200),
    'barka':          (23.6958, 57.8833),
    'nakhal':         (23.3733, 57.8336),
    'sohar':          (24.3473, 56.7269),
    'salalah':        (17.0151, 54.0924),
    'bidbid':         (23.4850, 58.0850),
    'al buraimi':     (24.2333, 55.7833),
    'nizwa':          (22.9333, 57.5333),
    'sur':            (22.5667, 59.5289),
    'duqm':           (19.6572, 57.7022),
    'muscat bosher':  (23.5670, 58.3330),
    'muscat al khoud':(23.6100, 58.1950),
}

def get_coords(project_name, city_name):
    # Try project match first
    for p, coords in PROJECT_COORDS.items():
        if p.lower() in project_name.lower():
            return coords
    
    # Fallback to city
    if not city_name: return (23.5880, 58.3829)
    key = city_name.lower().strip()
    for k, v in CITY_COORDS.items():
        if k in key or key in k:
            return v
    return (23.5880, 58.3829)

import random
def apply_jitter(lat, lng):
    # Add small random offset so multiple properties in same project don't stack
    jitter_lat = (random.random() - 0.5) * 0.005
    jitter_lng = (random.random() - 0.5) * 0.005
    return lat + jitter_lat, lng + jitter_lng

# Type normalisation
TYPE_MAP = {
    'villa':     'Villa',
    'apartment': 'Apartment',
    'townhouse': 'Townhouse',
    'land':      'Land',
    'office':    'Office',
}

def seed():
    app = create_app()
    with app.app_context():

        # ── 1. Create omran_agent ─────────────────────────────────────────
        agent = User.query.filter_by(username='omran_agent').first()
        if not agent:
            agent = User(
                username='omran_agent',
                email='omran@realestate.om',
                role='agent',
            )
            agent.set_password('123456')
            db.session.add(agent)
            db.session.commit()
            print('✅ Created omran_agent (role=agent)')
        else:
            print('ℹ️  omran_agent already exists.')

        agent_id = agent.id

        # ── 2. Clean existing OMRAN data ──────────────────────────────────
        deleted = Property.query.filter_by(is_omran=True).delete()
        db.session.commit()
        if deleted:
            print(f'🗑️  Deleted {deleted} existing OMRAN properties for clean re-seed.')

        # ── 3. Import from O.db ────────────────────────────────────────────
        if not os.path.exists(O_DB):
            print(f'❌ O.db not found at {O_DB}')
            return

        conn = sqlite3.connect(O_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT * FROM omran_properties').fetchall()
        conn.close()

        imported = 0
        for i, r in enumerate(rows, 1):
            ptype  = TYPE_MAP.get((r['property_type'] or 'villa').lower(), 'Villa')
            title  = f"{OMRAN_TAG} {r['project_name']} - {ptype} #{i}"

            desc = (
                r['description'] or
                f"OMRAN Group property in {r['project_name']}, {r['city']}. "
                f"Type: {ptype}. High investment potential."
            )
            city_name = r['city'] or 'Muscat'
            proj_name = r['project_name'] or ''
            
            base_lat, base_lng = get_coords(proj_name, city_name)
            lat, lng = apply_jitter(base_lat, base_lng)

            prop = Property(
                title=title,
                description=desc,
                price=float(r['price_omr'] or 100000),
                location=city_name,
                type=ptype,
                size=None,
                agent_id=agent_id,
                is_omran=True,
                is_surooh=False,
                latitude=lat,
                longitude=lng,
            )
            db.session.add(prop)
            imported += 1

        db.session.commit()
        total = Property.query.filter_by(is_omran=True).count()
        print(f'✅ Imported {imported} OMRAN properties from O.db')
        print(f'🏠 Total OMRAN properties in DB: {total}')
        print(f'👤 omran_agent ID: {agent_id}')

if __name__ == '__main__':
    seed()
