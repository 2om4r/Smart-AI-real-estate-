import random
from app import create_app
from extensions import db
from models import User, Property

def fix_agents():
    app = create_app()
    with app.app_context():
        # 1. Guarantee agents exist
        agents_data = [
            ('surooh_agent', 'surooh@smartestate.com', 'govagent123'),
            ('omran_agent', 'omran@smartestate.com', 'govagent123'),
            ('binthani', 'binthani@smartestate.com', 'agent123'),
            ('alhabeeb', 'alhabeeb@smartestate.com', 'agent123')
        ]
        
        agent_map = {}
        for username, email, pwd in agents_data:
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(username=username, email=email, role='agent')
                user.set_password(pwd)
                db.session.add(user)
                db.session.commit()
            agent_map[username] = user

        # 2. Iterate all properties and enforce ownership
        properties = Property.query.all()
        surooh_count = 0
        omran_count = 0
        random_count = 0
        
        for p in properties:
            if p.is_surooh:
                p.agent_id = agent_map['surooh_agent'].id
                surooh_count += 1
            elif p.is_omran:
                p.agent_id = agent_map['omran_agent'].id
                omran_count += 1
            else:
                agent = random.choice([agent_map['binthani'], agent_map['alhabeeb']])
                p.agent_id = agent.id
                random_count += 1

        db.session.commit()
        print(f"✅ Agents fixed. Surooh: {surooh_count}, Omran: {omran_count}, Random: {random_count}")

if __name__ == '__main__':
    fix_agents()
