from app import create_app, db
from models import Property, Area, User
import sys
import os

app = create_app()
app.app_context().push()

# Ensure we have an admin or agent
user = User.query.first()

# Create 3 properties in Khasab (Musandam)
for i in range(3):
    p = Property(
        title=f"Khasab Villa {i+1}",
        description="A beautiful villa in Khasab",
        price=75000 + (i * 1000),
        location="Khasab, Musandam",
        city="Khasab",
        type="Villa",
        latitude=26.1833 + (i * 0.001),
        longitude=56.2500 + (i * 0.001),
        agent_id=user.id
    )
    db.session.add(p)

db.session.commit()

# Run the zone discovery
scripts_dir = os.path.join(app.root_path, 'scripts')
if scripts_dir not in sys.path:
    sys.path.append(scripts_dir)

from zone_discovery import scan_and_update_zones
scan_and_update_zones(db.session, Property, Area)

# Verify
area = Area.query.filter(Area.name.like('%Khasab%')).first()
if area:
    print(f"SUCCESS: Created Area '{area.name}' at {area.latitude}, {area.longitude} with {area.listing_count} properties.")
else:
    print("FAILED: Did not create new Area.")
