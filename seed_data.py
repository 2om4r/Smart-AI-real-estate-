from app import create_app
from extensions import db
from models import User, Property, PropertyImage
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    db.create_all()

    # Create Admin User
    if not User.query.filter_by(email='admin@smartestate.com').first():
        admin = User(username='admin', email='admin@smartestate.com', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        print("Admin user created.")

    # Create Agent User
    if not User.query.filter_by(email='agent@smartestate.com').first():
        agent = User(username='agent_john', email='agent@smartestate.com', role='agent')
        agent.set_password('agent123')
        db.session.add(agent)
        print("Agent user created.")
    
    # Create Customer User
    if not User.query.filter_by(email='customer@gmail.com').first():
        customer = User(username='customer_jane', email='customer@gmail.com', role='customer')
        customer.set_password('customer123')
        db.session.add(customer)
        print("Customer user created.")
    
    db.session.commit()

    # Get the agent for relationship
    agent = User.query.filter_by(email='agent@smartestate.com').first()

    # Create Dummy Properties
    if not Property.query.first():
        p1 = Property(
            title="Luxury Villa in Muscat",
            description="A stunning 5-bedroom villa with sea view, private pool, and modern amenities.",
            price=250000,
            location="Muscat, Al Mouj",
            type="Villa",
            size=450,
            agent=agent,
            latitude=23.6087,
            longitude=58.5117
        )
        
        p2 = Property(
            title="Modern Apartment in Salalah",
            description="Spacious 2-bedroom apartment near the beach, fully furnished.",
            price=85000,
            location="Salalah, Dahariz",
            type="Apartment",
            size=120,
            agent=agent,
            latitude=17.0151,
            longitude=54.0924
        )

        p3 = Property(
            title="Commercial Land in Sohar",
            description="Prime location for commercial development.",
            price=150000,
            location="Sohar, Industrial Area",
            type="Land",
            size=1000,
            agent=agent,
            latitude=24.3473,
            longitude=56.7269
        )

        db.session.add_all([p1, p2, p3])
        db.session.commit()
        print("Dummy properties created.")
    else:
        print("Properties already exist.")
