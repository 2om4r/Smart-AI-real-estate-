"""
Seed Surooh integration:
  1. Create surooh_agent user (role=agent)
  2. Import properties from s.db (individual units)
  3. Import projects from surooh.db as grouped properties
"""
import sqlite3, os
from app import create_app
from extensions import db
from models import User, Property
from werkzeug.security import generate_password_hash

# ── City → (lat, lng) lookup ────────────────────────────────────────────────
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

def city_coords(city_str):
    key = city_str.lower().strip()
    for k, v in CITY_COORDS.items():
        if k in key or key in k:
            return v
    return (23.5880, 58.3829)   # Default: Muscat

DB_DIR   = os.path.join(os.path.dirname(__file__), 'instance', 'database')
SUROOH_DB = os.path.join(DB_DIR, 'surooh.db')
S_DB      = os.path.join(DB_DIR, 's.db')

SUROOH_TAG = '[Surooh]'   # prefix to detect existing imports

def seed():
    app = create_app()
    with app.app_context():

        # ── 1. Create surooh_agent ─────────────────────────────────────────
        agent = User.query.filter_by(username='surooh_agent').first()
        if not agent:
            agent = User(
                username='surooh_agent',
                email='surooh@gov.om',
                role='agent',
            )
            agent.set_password('Surooh@2024')
            db.session.add(agent)
            db.session.commit()
            print('✅ Created surooh_agent user (role=agent)')
        else:
            print('ℹ️  surooh_agent already exists, skipping user creation.')

        agent_id = agent.id

        # ── 2. Import individual units from s.db ───────────────────────────
        existing_titles = {p.title for p in Property.query.filter(
            Property.title.like(f'{SUROOH_TAG}%')).all()}

        imported_s = 0
        if os.path.exists(S_DB):
            conn = sqlite3.connect(S_DB)
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM surooh_properties').fetchall()
            conn.close()

            for r in rows:
                title = f"{SUROOH_TAG} {r['Project_Name']} - {r['Property_Type']} #{r['Property_ID']}"
                if title in existing_titles:
                    continue
                price = float(r['Price_OMR']) if r['Price_OMR'] else 80000.0
                beds  = r['Bedrooms'] or 0
                area  = r['Area_m2']  or 0
                ptype = r['Property_Type'] or 'Villa'
                # Normalise type to match existing enum
                type_map = {'twin villa': 'Villa', 'villa': 'Villa',
                            'apartment': 'Apartment', 'townhouse': 'Townhouse'}
                ptype_norm = type_map.get(ptype.lower(), 'Villa')
                desc = (
                    f"This unit is part of the Surooh government housing project '{r['Project_Name']}' "
                    f"in {r['City']}. Type: {ptype}, Bedrooms: {beds}, Area: {area} m². "
                    f"Status: {r['Status']}. "
                    "This property is part of a Surooh government housing project with high investment potential."
                )
                lat, lng = city_coords(r['City'])
                prop = Property(
                    title=title,
                    description=desc,
                    price=price,
                    location=r['City'],
                    type=ptype_norm,
                    size=float(area) if area else None,
                    agent_id=agent_id,
                    is_surooh=True,
                    latitude=lat,
                    longitude=lng,
                )
                db.session.add(prop)
                imported_s += 1
            db.session.commit()
            print(f'✅ Imported {imported_s} units from s.db')
        else:
            print(f'⚠️  s.db not found at {S_DB}')

        # ── 3. Import project-level entries from surooh.db ─────────────────
        imported_p = 0
        if os.path.exists(SUROOH_DB):
            conn = sqlite3.connect(SUROOH_DB)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT sp.*, u.Villas, u."Twin Villas", u.Townhouses, u.Apartments
                FROM surooh_projects sp
                LEFT JOIN units u ON sp."Project Name" = u."Project Name"
            """).fetchall()
            conn.close()

            for r in rows:
                title = f"{SUROOH_TAG} {r['Project Name']} (Project)"
                if title in existing_titles:
                    continue
                invest_str = r['Investment (Million OMR)'] or '0'
                try:
                    invest_omr = float(str(invest_str).replace(',','')) * 1_000_000
                    unit_price = invest_omr / (r['Total Units'] or 1)
                except:
                    unit_price = 85000.0
                villas  = r['Villas']      or 0
                apts    = r['Apartments']  or 0
                twv     = r['Twin Villas'] or 0
                towns   = r['Townhouses']  or 0
                desc = (
                    f"Surooh Government Housing Project '{r['Project Name']}' in {r['City']}, {r['Region']}. "
                    f"Total Units: {r['Total Units']} | Villas: {villas} | Twin Villas: {twv} | "
                    f"Townhouses: {towns} | Apartments: {apts}. "
                    f"Data Type: {r['Data Type']}. "
                    "This property is part of a Surooh government housing project with high investment potential."
                )
                lat, lng = city_coords(r['City'])
                prop = Property(
                    title=title,
                    description=desc,
                    price=round(unit_price, 0),
                    location=r['City'],
                    type='Villa',
                    size=float(r['Area (m2)']) / (r['Total Units'] or 1) if r['Area (m2)'] else None,
                    agent_id=agent_id,
                    is_surooh=True,
                    latitude=lat,
                    longitude=lng,
                    region=r['Region'],
                    total_units=r['Total Units'],
                    villas=villas,
                    apartments=apts,
                    investment_omr=invest_omr,
                    data_type=r['Data Type'],
                )
                db.session.add(prop)
                imported_p += 1
            db.session.commit()
            print(f'✅ Imported {imported_p} projects from surooh.db')
        else:
            print(f'⚠️  surooh.db not found at {SUROOH_DB}')

        total = Property.query.filter_by(is_surooh=True).count()
        print(f'\n🏠 Total Surooh properties in DB: {total}')
        print(f'👤 surooh_agent ID: {agent_id}')

if __name__ == '__main__':
    seed()
