from openai import OpenAI
from models import Property, Area, ChatLog
from extensions import db
import statistics
import os
import json
import re
import random
# 🔥 API KEY (Fetched ONLY from Environment Variables for Security)
api_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

def get_roi_assumption(prop_type):
    if prop_type == 'Apartment': return 7.0
    if prop_type == 'Villa': return 4.5
    if prop_type == 'Townhouse': return 6.0
    if prop_type == 'Commercial': return 8.0
    return 5.0

# 📊 حساب السكور المتقدم
def calculate_score(p, avg_price=100000):
    price = float(p.get('price', avg_price))
    ptype = p.get('type', 'Unknown')
    location = p.get('location', '')

    area = None
    if location:
        area = Area.query.filter(Area.name.ilike(f"%{location}%")).first()

    location_score = 60
    demand = 50
    growth = 50

    if area:
        location_score = area.score # 0-100
        demand = area.demand
        growth = area.price_growth

    price_ratio = 1.0
    if avg_price > 0:
        price_ratio = price / avg_price

    if price_ratio < 0.8: price_score = 90
    elif price_ratio < 1.0: price_score = 80
    elif price_ratio < 1.2: price_score = 60
    else: price_score = 40

    roi = get_roi_assumption(ptype)
    roi_score = min(roi * 10, 100) # e.g. 8% roi -> 80 score

    # score formula
    score = (location_score * 0.3) + (price_score * 0.2) + (roi_score * 0.2) + (demand * 0.15) + (growth * 0.15)
    return min(max(int(score), 0), 100)


# 📊 ملخص البورتفوليو (مهم للداشبورد)
def portfolio_summary(properties):
    if not properties:
        return {
            "total": 0,
            "avg_price": 0,
            "portfolio_score": 0,
            "type_distribution": {},
            "avg_roi": 0
        }

    prices = [float(p.get('price', 0)) for p in properties if p.get('price')]
    avg_price = statistics.mean(prices) if prices else 0

    type_dist = {}
    rois = []
    for p in properties:
        t = p.get("type", "Other")
        type_dist[t] = type_dist.get(t, 0) + 1
        rois.append(get_roi_assumption(t))

    scores = [calculate_score(p, avg_price) for p in properties]
    portfolio_score = int(statistics.mean(scores)) if scores else 0
    avg_roi = statistics.mean(rois) if rois else 0

    return {
        "total": len(properties),
        "avg_price": int(avg_price),
        "portfolio_score": portfolio_score,
        "type_distribution": type_dist,
        "avg_roi": round(avg_roi, 1)
    }


# 🏆 AI Recommendation (PRO)
def recommend_investment(properties):
    if not properties:
        return None

    prices = [float(p.get('price', 0)) for p in properties if p.get('price')]
    avg_price = statistics.mean(prices) if prices else 100000

    scored = []
    for p in properties:
        s = calculate_score(p, avg_price)
        scored.append({**p, "score": s, "roi": get_roi_assumption(p.get('type', 'Unknown'))})

    scored.sort(key=lambda x: x["score"], reverse=True)

    best = scored[0]
    worst_2 = scored[-2:] if len(scored) >= 2 else []

    # AI Reasoning Logic
    reason = "Chosen because: "
    if float(best.get('price', avg_price)) < avg_price:
        reason += "- price is below market avg (< OMR " + str(int(avg_price)) + "). "
    if best['roi'] >= 6.0:
        reason += "- high rental demand (" + str(best['roi']) + "% ROI). "
    if best['score'] > 80:
        reason += "- extremely strong future growth potential. "
    
    if reason == "Chosen because: ":
        reason = "Chosen because of a balanced mix of location and demand factors."

    risk_level = "low" if best['score'] > 75 else "medium" if best['score'] > 50 else "high"

    return {
        "best_project": best.get("location", "Unknown"),
        "type": best.get("type", "Unknown"),
        "score": best["score"],
        "roi": best["roi"],
        "predicted_growth": "5-8%",  
        "reason": reason,
        "risk_level": risk_level,
        "avg_price": int(avg_price),
        "top_3": scored[:3],
        "worst_2": worst_2
    }

# 🤖 الشات
def get_ai_response(prompt, user_id=None):
    msg_lower = prompt.lower()

    # 1. Quick intercept for Favorite / Contact
    # check for favorites
    if any(word in msg_lower for word in ["احفظ", "favorite", "like", "save"]):
        # Return generic add_favorite action format (frontend expects this)
        # We need a property_id. We'll pick the top one from DB just as fallback or require frontend context
        recent = db.session.query(Property).order_by(Property.id.desc()).first()
        prop_id = recent.id if recent else 1
        return {
            "action": "add_favorite",
            "property_id": prop_id
        }

    # check for contact
    if any(word in msg_lower for word in ["contact", "تواصل", "رسالة", "message"]):
        recent = db.session.query(Property).order_by(Property.id.desc()).first()
        a_id = recent.agent_id if recent else 1
        return {
            "action": "send_message",
            "agent_id": a_id,
            "message": prompt
        }

    # 2. Extract Intent from LLM
    history = []
    if user_id:
        logs = ChatLog.query.filter_by(user_id=user_id).order_by(ChatLog.timestamp.desc()).limit(8).all()
        for l in reversed(logs):
            history.append({"role": "user", "content": l.user_message})
            history.append({"role": "assistant", "content": l.bot_response})

    system_msg = {
        "role": "system", 
        "content": (
            "You are Ahmed, a top-tier real estate AI agent in Oman. "
            "You MUST automatically detect the language (Arabic or English) and reply ONLY in the exact JSON format. "
            "Your job is to parse the user's intent to exact structured data. "
            "Extract: \n"
            "- location (e.g. Muscat, Salalah, Barka, Sohar, Al Mouj)\n"
            "- property_type (Villa, Apartment, Land)\n"
            "- budget (numeric max price. Use 0 if unspecified)\n"
            "- intent (search, investment, compare, contact)\n"
            "- text (Your conversational response to the user in their language, addressing their request naturally.)\n"
            "\n"
            "Respond ONLY with valid JSON exactly matching this format: \n"
            "{\n"
            "  \"location\": \"...\",\n"
            "  \"property_type\": \"...\",\n"
            "  \"budget\": 0,\n"
            "  \"intent\": \"...\",\n"
            "  \"text\": \"...\"\n"
            "}"
        )
    }

    messages = [system_msg] + history + [{"role": "user", "content": prompt}]

    ai_text = "I am looking for the best options for you... 🏘️" if "english" not in msg_lower else "جاري البحث عن أفضل الخيارات لك... 🏘️"
    
    extracted_data = {
        "location": "", "property_type": "", "budget": 0, "intent": "search", "text": ai_text
    }
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={ "type": "json_object" }
        )
        extracted_data = json.loads(response.choices[0].message.content.strip())
        ai_text = extracted_data.get("text", ai_text)
    except Exception as e:
        print("ERROR openai:", str(e))

    # 3. Smart Search & Filters
    query = Property.query

    loc = extracted_data.get("location", "")
    if loc and loc.strip() and str(loc).lower() not in ["none", "null"]:
        query = query.filter(Property.location.ilike(f"%{loc}%"))

    ptype = extracted_data.get("property_type", "")
    if ptype and str(ptype).lower() not in ["none", "null", "any"]:
        if "villa" in str(ptype).lower():
            query = query.filter_by(type="Villa")
        elif "apartment" in str(ptype).lower():
            query = query.filter_by(type="Apartment")
        elif "land" in str(ptype).lower():
            query = query.filter_by(type="Land")

    budget = extracted_data.get("budget", 0)
    try:
        if float(budget) > 0:
            query = query.filter(Property.price <= float(budget))
    except:
        pass

    results = query.all()
    
    # 4. Fallback if no result
    if not results and loc:
        # STRICT LOCATION LOGIC: If no results, do not return properties from another city
        is_arabic = bool(re.search("[\u0600-\u06FF]", ai_text))
        if is_arabic:
            ai_text = f"عذراً، لا نملك عقارات تطابق بحثك حالياً في {loc}. المشكلة قد تكون في نوع العقار أو المدينة.\n\nهل يمكنك توسيع نطاق البحث أو تجربة مناطق قريبة؟ 🏡"
        else:
            ai_text = f"Sorry, we don't currently have exact matches in {loc}. Please consider expanding your search criteria or checking nearby areas. 🏡"

    # 5. Sort Properties
    if extracted_data.get("intent", "search") == "investment" or "best investment" in msg_lower or "استثم" in msg_lower:
        results.sort(key=lambda x: get_roi_assumption(x.type or 'Unknown'), reverse=True)
    elif "cheapest" in msg_lower or "ارخص" in msg_lower:
        results.sort(key=lambda x: x.price if x.price else float('inf'))
    else:
        prices = [float(p.price) for p in results if p.price]
        avg = sum(prices)/len(prices) if prices else 100000
        results.sort(key=lambda x: calculate_score({'price': x.price, 'type': x.type, 'location': x.location}, avg), reverse=True)

    top_results = results[:4]

    # 6. Dynamic Unique Reasons Generator
    _reason_templates = {
        "Villa": [
            "High demand for luxury villas in {loc} driven by expat families and tourism growth",
            "Villa market in {loc} shows 8-12% annual appreciation due to limited supply",
            "Premium residential area in {loc} with upcoming infrastructure projects boosting value",
            "{loc} villas benefit from strong rental demand, especially during tourism season",
        ],
        "Apartment": [
            "Apartments in {loc} attract steady rental income from working professionals",
            "Growing urban development in {loc} makes apartments a high-yield short-term investment",
            "Strong occupancy rates in {loc} apartments due to proximity to business districts",
            "{loc} apartment market benefits from government housing initiatives and rising demand",
        ],
        "Land": [
            "Land prices in {loc} are appreciating rapidly due to upcoming development projects",
            "Strategic land location in {loc} with zoning approvals for commercial development",
            "Early-stage land investment in {loc} offers 15-25% growth potential over 5 years",
            "{loc} land benefits from new road and infrastructure connections planned for 2025-2027",
        ],
    }
    _default_reasons = [
        "Strong market fundamentals in {loc} with growing population and economic diversification",
        "Government investment in {loc} infrastructure driving property value appreciation",
        "{loc} is an emerging investment hub with excellent future growth prospects",
    ]
    _used_reasons = set()

    def _get_unique_reason(prop_type, location):
        templates = _reason_templates.get(prop_type, _default_reasons)
        available = [t for t in templates if t not in _used_reasons]
        if not available:
            available = _default_reasons
        chosen = random.choice(available)
        _used_reasons.add(chosen)
        return chosen.format(loc=location)

    # 7. Format Properties with dynamic ROI and unique reasons
    properties_to_return = []
    for i, best_p in enumerate(top_results):
        t_low = (best_p.type or '').lower()
        # Dynamic ROI ranges
        if 'villa' in t_low:
            roi_val = round(random.uniform(6.0, 7.0), 1)
        elif 'apartment' in t_low:
            roi_val = round(random.uniform(7.0, 8.0), 1)
        elif 'land' in t_low:
            roi_val = round(random.uniform(8.0, 10.0), 1)
        else:
            roi_val = round(random.uniform(5.0, 7.0), 1)

        # Under construction bonus
        prop_status = getattr(best_p, 'status', 'available') or 'available'
        if prop_status == 'under_construction':
            roi_val = round(roi_val + 1.5, 1)  # Early investment advantage

        price = float(best_p.price or 0)
        yearly_inc = round(price * (roi_val / 100.0), 0)
        
        # Growth calculations (Realistic dynamic bounds)
        growth_1y = round(random.uniform(0.05, 0.10), 3)
        growth_2y = round(random.uniform(0.12, 0.18), 3)
        growth_5y = round(random.uniform(0.25, 0.45), 3)

        p1 = round(price * (1 + growth_1y), 0)
        p2 = round(price * (1 + growth_2y), 0)
        p5 = round(price * (1 + growth_5y), 0)

        reason = _get_unique_reason(best_p.type or 'Unknown', best_p.location)

        agent_name = "Unknown"
        if best_p.agent:
            agent_name = best_p.agent.username

        properties_to_return.append({
            "id": best_p.id,
            "title": best_p.title,
            "location": best_p.location,
            "price": best_p.price,
            "roi": roi_val,
            "yearly_income": yearly_inc,
            "price_1y": p1,
            "price_2y": p2,
            "price_5y": p5,
            "reason": reason,
            "lat": getattr(best_p, "latitude", 23.5880),
            "lng": getattr(best_p, "longitude", 58.3829),
            "agent": agent_name,
            "agent_id": best_p.agent_id,
            "is_new": getattr(best_p, 'is_new', False),
            "status": prop_status,
        })

    # 8. Add follow-up question
    is_arabic = bool(re.search("[\u0600-\u06FF]", ai_text))
    followups_ar = [
        "هل تفضل سعر معين؟ 💰",
        "هل تبحث عن استثمار طويل أو قصير المدى؟ 📊",
        "هل تريد مقارنة بين هذه الخيارات؟ 🔍",
        "هل تريد التواصل مع الوكيل لأي من هذه العقارات؟ 💬",
    ]
    followups_en = [
        "Do you have a specific budget in mind? 💰",
        "Are you looking for short-term or long-term investment? 📊",
        "Would you like me to compare these options? 🔍",
        "Want to contact an agent for any of these? 💬",
    ]
    followup = random.choice(followups_ar if is_arabic else followups_en)
    if properties_to_return:
        ai_text += "\n\n" + followup

    # 9. Log chat
    if user_id:
        new_log = ChatLog(user_message=prompt, bot_response=ai_text, user_id=user_id)
        db.session.add(new_log)
        db.session.commit()

    # 10. Investment Hotspots from Area table
    investment_hotspots = []
    hotspot_query = Area.query
    if loc and loc.strip() and str(loc).lower() not in ["none", "null"]:
        hotspot_query = hotspot_query.filter(Area.name.ilike(f"%{loc}%"))
    hotspot_areas = hotspot_query.order_by(Area.demand.desc()).limit(5).all()

    if not hotspot_areas:
        hotspot_areas = Area.query.order_by(Area.demand.desc()).limit(5).all()

    for area in hotspot_areas:
        reason_parts = []
        if area.demand > 70: reason_parts.append("high demand")
        if area.price_growth > 60: reason_parts.append("strong price growth")
        if area.services > 60: reason_parts.append("excellent infrastructure")
        if not reason_parts: reason_parts.append("emerging market potential")
        investment_hotspots.append({
            "name": area.name,
            "lat": area.latitude,
            "lng": area.longitude,
            "reason": ", ".join(reason_parts).capitalize()
        })

    return {
        "text": ai_text,
        "properties": properties_to_return,
        "investment_hotspots": investment_hotspots,
    }