"""Seed investment area data into the database."""
from app import create_app
from extensions import db
from models import Area

AREAS = [
    # name, lat, lng, avg_price(OMR), demand, price_growth, services, listing_count
    ("Al Mouj (The Wave), Muscat",  23.6087, 58.5117, 285000, 95, 88, 92, 80),
    ("Qurum, Muscat",               23.5872, 58.3721, 195000, 90, 82, 95, 75),
    ("Al Khuwair, Muscat",          23.6020, 58.3620, 165000, 85, 76, 88, 70),
    ("Bousher, Muscat",             23.5670, 58.3330, 145000, 80, 70, 82, 68),
    ("Airport Heights, Muscat",     23.5937, 58.2880, 125000, 78, 68, 78, 65),
    ("Al Hail, Muscat",             23.6350, 58.2250, 115000, 72, 62, 74, 60),
    ("Ghubrah, Muscat",             23.6133, 58.3483, 155000, 82, 74, 85, 72),
    ("Azaiba, Muscat",              23.5960, 58.3120, 140000, 76, 65, 80, 62),
    ("Amerat, Muscat",              23.5100, 58.5200,  85000, 65, 58, 68, 55),
    ("Muscat Al Khoud",             23.6100, 58.1950, 105000, 68, 60, 72, 58),
    ("Muttrah, Muscat",             23.6120, 58.5680, 110000, 60, 55, 70, 52),
    ("Mawaleh, Muscat",             23.4980, 58.3950,  75000, 55, 50, 65, 48),
    ("Sohar, Al Batinah",           24.3473, 56.7269,  65000, 58, 52, 62, 50),
    ("Salalah, Dhofar",             17.0151, 54.0924,  78000, 62, 57, 66, 54),
    ("Nizwa, Ad Dakhiliyah",        22.9333, 57.5333,  55000, 45, 42, 55, 40),
    ("Sur, Ash Sharqiyah",          22.5667, 59.5289,  42000, 38, 35, 48, 35),
    ("Barka, Al Batinah",           23.6958, 57.8833,  68000, 50, 46, 58, 45),
    ("Duqm, Al Wusta",              19.6572, 57.7022,  95000, 70, 80, 55, 48),
]

def seed():
    app = create_app()
    with app.app_context():
        if Area.query.count() > 0:
            print("Areas already seeded — skipping.")
            return
        for name, lat, lng, avg_price, demand, pg, svcs, lc in AREAS:
            area = Area(
                name=name, latitude=lat, longitude=lng,
                avg_price=avg_price, demand=demand,
                price_growth=pg, services=svcs, listing_count=lc
            )
            db.session.add(area)
        db.session.commit()
        print(f"✅ Seeded {len(AREAS)} investment areas.")

if __name__ == '__main__':
    seed()
