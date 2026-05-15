# =============================================================================
# ai_utils.py — Ahmed 2.0 Smart AI Chatbot Engine
# محرك الشات بوت الذكي أحمد 2.0
# =============================================================================
import os
import re
import json
import random
import statistics
from openai import OpenAI
from models import Property, Area, ChatLog, User
from extensions import db

# ── مفتاح API (من متغيرات البيئة فقط - للأمان) ──
# API Key from environment variables only - for security
api_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# =============================================================================
# FEATURE 4 — مصدر واحد لنسب النمو
# Single source of truth for growth rates
# =============================================================================
GROWTH_RATES = {
    "muscat": 0.06,
    "salalah": 0.05,
    "barka": 0.07,
    "sohar": 0.06,
}
DEFAULT_GROWTH = 0.055
DEFAULT_RENTAL_YIELD = 0.06  # 6%

# ── تحويل أسماء المدن من العربية إلى الإنجليزية ──
# Arabic to English city name mapping
CITY_MAP_AR_EN = {
    "مسقط": "muscat",
    "صلالة": "salalah",
    "بركاء": "barka",
    "صحار": "sohar",
}

# ── نسبة العائد حسب نوع العقار ──
# ROI assumption by property type
def get_roi_assumption(prop_type):
    t = (prop_type or '').lower()
    if 'apartment' in t: return 7.0
    if 'villa' in t: return 4.5
    if 'townhouse' in t: return 6.0
    if 'commercial' in t: return 8.0
    if 'land' in t: return 9.0
    return 5.0

# =============================================================================
# دوال مساعدة — Helper Functions
# =============================================================================

# ── كشف اللغة — Language Detection ──
def detect_language(text):
    """Detect if text is Arabic or English using Unicode range."""
    if re.search(r'[\u0600-\u06FF]', text):
        return 'ar'
    return 'en'

# ── تطبيع اسم المدينة — Normalize city name ──
def normalize_city(city_str):
    """Convert Arabic city names to English lowercase key."""
    if not city_str:
        return None
    city_lower = city_str.strip().lower()
    # Check Arabic mapping first
    for ar_name, en_name in CITY_MAP_AR_EN.items():
        if ar_name in city_str:
            return en_name
    # Check English names
    for en_name in GROWTH_RATES:
        if en_name in city_lower:
            return en_name
    return city_lower

# ── الحصول على نسبة النمو — Get growth rate for a city ──
def get_growth_rate(city_key):
    """Get growth rate for a normalized city key."""
    if not city_key:
        return DEFAULT_GROWTH
    return GROWTH_RATES.get(city_key, DEFAULT_GROWTH)

# ── حساب العائد على الاستثمار — ROI Calculation ──
def calculate_roi_full(price, city_key, prop_type):
    """Full ROI calculation returning a dict of financial metrics."""
    growth_rate = get_growth_rate(city_key)
    rental_yield = DEFAULT_RENTAL_YIELD
    roi = (growth_rate * 100) + (rental_yield * 100)
    yearly_income = price * rental_yield
    value_1y = price * (1 + growth_rate)
    value_5y = price * ((1 + growth_rate) ** 5)
    return {
        "growth_rate": round(growth_rate * 100, 1),
        "roi": round(roi, 1),
        "yearly_income": round(yearly_income, 0),
        "value_1y": round(value_1y, 0),
        "value_5y": round(value_5y, 0),
    }

# =============================================================================
# تصنيف النية — Intent Classification
# =============================================================================
def classify_intent(message):
    """Classify user message into one of 4 intents."""
    msg = message.lower()

    # Intent A: AGENT_BEST_PROPERTIES
    agent_patterns_en = [
        r"best properties?\s*(of|from|by)\s+(\w+)",
        r"top investment\s+(\w+)",
        r"(\w+)\s*properties",
        r"recommend.*from\s+(\w+)",
        r"(\w+)\s*agent",
        r"properties?\s*(of|from|by)\s+(\w+)",
    ]
    agent_patterns_ar = [
        r"أفضل عقارات\s+(\S+)",
        r"عقارات\s+(\S+)",
        r"أحسن استثمار\s+(?:عند|من)\s+(\S+)",
    ]
    for p in agent_patterns_en:
        if re.search(p, msg):
            return "AGENT_BEST_PROPERTIES"
    for p in agent_patterns_ar:
        if re.search(p, message):
            return "AGENT_BEST_PROPERTIES"

    # Intent B: ROI_CALCULATION
    roi_keywords_en = ["calculate roi", "calculate profit", "investment return",
                       "how much profit", "interest rate", "roi for", "roi of"]
    roi_keywords_ar = ["احسب الفائدة", "احسب نسبة الربح", "كم العائد",
                       "نسبة الاستثمار", "احسب الربح", "العائد على"]
    if any(k in msg for k in roi_keywords_en) or any(k in message for k in roi_keywords_ar):
        return "ROI_CALCULATION"

    # Intent C: PROPERTY_SEARCH
    search_keywords_en = ["show me", "find me", "search for", "apartments in",
                          "villas in", "properties in", "land in"]
    search_keywords_ar = ["عقارات في", "شقق في", "فلل في", "أراضي في",
                          "ابحث عن", "وريني", "عرض"]
    if any(k in msg for k in search_keywords_en) or any(k in message for k in search_keywords_ar):
        return "PROPERTY_SEARCH"

    # Intent D: GENERAL_QUESTION
    return "GENERAL_QUESTION"

# =============================================================================
# استخراج اسم الوكيل — Extract Agent Name
# =============================================================================
def extract_agent(message):
    """Extract agent name from message using fuzzy matching against DB."""
    msg_lower = message.lower()
    agents = User.query.filter_by(role='agent').all()
    best_match = None
    for agent in agents:
        uname = agent.username.lower()
        fname = (agent.full_name or '').lower()
        if uname in msg_lower or fname in msg_lower:
            best_match = agent
            break
        # Partial match
        if len(uname) > 3 and uname[:4] in msg_lower:
            best_match = agent
    # Also check Arabic text directly
    if not best_match:
        for agent in agents:
            uname = agent.username.lower()
            if uname in message:
                best_match = agent
                break
    return best_match

# =============================================================================
# استخراج بيانات العقار — Extract Property Params
# =============================================================================
def extract_property_params(message):
    """Extract city, type, and price from user message."""
    msg = message.lower()
    # City detection
    city = None
    all_cities = list(GROWTH_RATES.keys()) + list(CITY_MAP_AR_EN.keys())
    for c in all_cities:
        if c in msg or c in message:
            city = normalize_city(c)
            break

    # Type detection
    prop_type = None
    type_map = {
        'villa': 'Villa', 'فيلا': 'Villa', 'فلل': 'Villa',
        'apartment': 'Apartment', 'شقة': 'Apartment', 'شقق': 'Apartment',
        'land': 'Land', 'أرض': 'Land', 'أراضي': 'Land',
        'commercial': 'Commercial', 'تجاري': 'Commercial',
        'townhouse': 'Townhouse',
    }
    for keyword, ptype in type_map.items():
        if keyword in msg or keyword in message:
            prop_type = ptype
            break

    # Price extraction
    price = None
    price_match = re.search(r'(\d[\d,]*\.?\d*)\s*(?:omr|rial|OMR|ر\.ع|ريال)?', msg)
    if price_match:
        price_str = price_match.group(1).replace(',', '')
        try:
            price = float(price_str)
        except ValueError:
            pass

    return city, prop_type, price

# =============================================================================
# حساب السكور المتقدم — Advanced Score Calculation
# =============================================================================
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
        location_score = area.score
        demand = area.demand
        growth = area.price_growth

    price_ratio = price / avg_price if avg_price > 0 else 1.0
    if price_ratio < 0.8: price_score = 90
    elif price_ratio < 1.0: price_score = 80
    elif price_ratio < 1.2: price_score = 60
    else: price_score = 40

    roi = get_roi_assumption(ptype)
    roi_score = min(roi * 10, 100)
    score = (location_score * 0.3) + (price_score * 0.2) + (roi_score * 0.2) + (demand * 0.15) + (growth * 0.15)
    return min(max(int(score), 0), 100)

# =============================================================================
# ملخص البورتفوليو — Portfolio Summary
# =============================================================================
def portfolio_summary(properties):
    if not properties:
        return {"total": 0, "avg_price": 0, "portfolio_score": 0,
                "type_distribution": {}, "avg_roi": 0}
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
    return {"total": len(properties), "avg_price": int(avg_price),
            "portfolio_score": portfolio_score, "type_distribution": type_dist,
            "avg_roi": round(avg_roi, 1)}

# =============================================================================
# توصية الاستثمار — Investment Recommendation
# =============================================================================
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
    return {"best_project": best.get("location", "Unknown"), "type": best.get("type", "Unknown"),
            "score": best["score"], "roi": best["roi"], "predicted_growth": "5-8%",
            "reason": reason, "risk_level": risk_level, "avg_price": int(avg_price),
            "top_3": scored[:3], "worst_2": worst_2}

# =============================================================================
# استدعاء OpenAI — Call OpenAI API
# =============================================================================
def call_openai(system_prompt, user_message, temperature=0.4, max_tokens=500):
    """Safe wrapper around OpenAI API call."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[OpenAI ERROR]: {e}")
        return None

# =============================================================================
# معالجة النية A — أفضل عقارات الوكيل
# Handle Intent A — Agent Best Properties
# =============================================================================
def handle_agent_best_properties(message, lang):
    agent = extract_agent(message)
    if not agent:
        if lang == 'ar':
            return {"success": True, "intent": "AGENT_BEST_PROPERTIES", "language": lang,
                    "answer": "عذراً، لم أتمكن من التعرف على اسم الوكيل. يرجى كتابة الاسم بوضوح. 🔍",
                    "properties": []}
        return {"success": True, "intent": "AGENT_BEST_PROPERTIES", "language": lang,
                "answer": "Sorry, I couldn't identify the agent name. Please type it clearly. 🔍",
                "properties": []}

    props = Property.query.filter_by(agent_id=agent.id, status='available').all()
    if not props:
        # Also try without status filter
        props = Property.query.filter_by(agent_id=agent.id).all()

    if not props:
        if lang == 'ar':
            return {"success": True, "intent": "AGENT_BEST_PROPERTIES", "language": lang,
                    "answer": f"عذراً، الوكيل {agent.username} ليس لديه عقارات متاحة حالياً. 🏠",
                    "properties": []}
        return {"success": True, "intent": "AGENT_BEST_PROPERTIES", "language": lang,
                "answer": f"Sorry, agent {agent.username} has no available properties right now. 🏠",
                "properties": []}

    # Calculate ROI for each property and sort
    scored_props = []
    for p in props:
        city_key = normalize_city(p.city or p.location or '')
        roi_data = calculate_roi_full(float(p.price or 0), city_key, p.type)
        scored_props.append((p, roi_data['roi']))
    scored_props.sort(key=lambda x: x[1], reverse=True)
    top3 = scored_props[:3]

    # Build context for LLM
    context_lines = []
    for i, (p, roi) in enumerate(top3, 1):
        context_lines.append(
            f"{i}. {p.type} in {p.location} — Price: {int(p.price)} OMR — ROI: {roi}%"
        )
    context = "\n".join(context_lines)
    reply_lang = "Arabic" if lang == 'ar' else "English"

    system_prompt = (
        f"The user asked about agent {agent.username}'s best investment properties. "
        f"Here are the top {len(top3)} from the database, already ranked by ROI:\n"
        f"{context}\n\n"
        f"Reply in {reply_lang} using this exact structure:\n"
        f"🏆 Best {len(top3)} Investment Properties by {agent.username}:\n"
        f"1. 🏠 [Type] - [Location] | [Price] OMR | ROI: [X]%\n"
        f"2. ...\n3. ...\n\n"
        f"Then add a short 1-2 sentence professional recommendation."
    )
    answer = call_openai(system_prompt, message)
    if not answer:
        # Fallback: build answer manually
        lines = [f"🏆 Best {len(top3)} Investment Properties by {agent.username}:"]
        emojis = {'Villa': '🏡', 'Apartment': '🏢', 'Land': '🌍', 'Townhouse': '🏘️'}
        for i, (p, roi) in enumerate(top3, 1):
            e = emojis.get(p.type, '🏠')
            lines.append(f"{i}. {e} {p.type} - {p.location} | {int(p.price)} OMR | ROI: {roi}%")
        answer = "\n".join(lines)

    # Build properties list for frontend
    props_list = []
    for p, roi in top3:
        props_list.append({
            "id": p.id, "title": p.title, "location": p.location,
            "price": p.price, "roi": roi, "type": p.type,
            "lat": p.latitude, "lng": p.longitude,
            "agent": agent.username, "agent_id": agent.id,
        })

    return {"success": True, "intent": "AGENT_BEST_PROPERTIES", "language": lang,
            "answer": answer, "properties": props_list}

# =============================================================================
# معالجة النية B — حساب العائد على الاستثمار
# Handle Intent B — ROI Calculation
# =============================================================================
def handle_roi_calculation(message, lang):
    city_raw, prop_type, price = extract_property_params(message)

    if not price or price <= 0:
        if lang == 'ar':
            return {"success": True, "intent": "ROI_CALCULATION", "language": lang,
                    "answer": "يرجى تحديد السعر والموقع ونوع العقار لحساب العائد.\nمثال: احسب الفائدة لفيلا في مسقط بسعر 150000 💰",
                    "properties": []}
        return {"success": True, "intent": "ROI_CALCULATION", "language": lang,
                "answer": "Please provide the price, location, and property type to calculate ROI.\nExample: Calculate ROI for a villa in Muscat priced at 150000 OMR 💰",
                "properties": []}

    city_key = city_raw or "muscat"
    display_city = city_key.capitalize()
    display_type = prop_type or "Property"
    roi_data = calculate_roi_full(price, city_key, display_type)
    reply_lang = "Arabic" if lang == 'ar' else "English"

    system_prompt = (
        f"The user asked to calculate the investment return for a {display_type} in "
        f"{display_city} priced at {int(price)} OMR. The calculations are already done — "
        f"present them in {reply_lang} using this exact format:\n\n"
        f"📊 Investment Analysis - {display_type} in {display_city}\n\n"
        f"💰 Price: {int(price)} OMR\n"
        f"📈 Annual Growth Rate: {roi_data['growth_rate']}%\n"
        f"🎯 ROI: {roi_data['roi']}%\n"
        f"💵 Expected Annual Income: {int(roi_data['yearly_income'])} OMR\n"
        f"📅 Value after 1 year: {int(roi_data['value_1y'])} OMR\n"
        f"📅 Value after 5 years: {int(roi_data['value_5y'])} OMR\n\n"
        f"Then write 2 sentences of professional investment advice."
    )
    answer = call_openai(system_prompt, message)
    if not answer:
        # Fallback
        answer = (
            f"📊 Investment Analysis - {display_type} in {display_city}\n\n"
            f"💰 Price: {int(price)} OMR\n"
            f"📈 Annual Growth Rate: {roi_data['growth_rate']}%\n"
            f"🎯 ROI: {roi_data['roi']}%\n"
            f"💵 Expected Annual Income: {int(roi_data['yearly_income'])} OMR\n"
            f"📅 Value after 1 year: {int(roi_data['value_1y'])} OMR\n"
            f"📅 Value after 5 years: {int(roi_data['value_5y'])} OMR"
        )

    return {"success": True, "intent": "ROI_CALCULATION", "language": lang,
            "answer": answer, "properties": []}

# =============================================================================
# معالجة النية C — البحث عن العقارات
# Handle Intent C — Property Search
# =============================================================================
def handle_property_search(message, lang):
    city_raw, prop_type, price = extract_property_params(message)
    query = Property.query

    if city_raw:
        query = query.filter(
            db.or_(
                Property.location.ilike(f"%{city_raw}%"),
                Property.city.ilike(f"%{city_raw}%"),
            )
        )
    if prop_type:
        query = query.filter_by(type=prop_type)
    if price and price > 0:
        query = query.filter(Property.price <= price)

    results = query.limit(5).all()

    if not results:
        if lang == 'ar':
            return {"success": True, "intent": "PROPERTY_SEARCH", "language": lang,
                    "answer": "عذراً، لم أجد عقارات تطابق بحثك. حاول توسيع نطاق البحث. 🏡",
                    "properties": []}
        return {"success": True, "intent": "PROPERTY_SEARCH", "language": lang,
                "answer": "Sorry, no properties matched your search. Try broader criteria. 🏡",
                "properties": []}

    props_list = []
    lines = []
    for i, p in enumerate(results, 1):
        city_key = normalize_city(p.city or p.location or '')
        roi_data = calculate_roi_full(float(p.price or 0), city_key, p.type)
        lines.append(f"{i}. {p.type} in {p.location} — {int(p.price)} OMR (ROI: {roi_data['roi']}%)")
        props_list.append({
            "id": p.id, "title": p.title, "location": p.location,
            "price": p.price, "roi": roi_data['roi'], "type": p.type,
            "lat": p.latitude, "lng": p.longitude,
            "agent": p.agent.username if p.agent else "Unknown",
            "agent_id": p.agent_id,
        })

    if lang == 'ar':
        answer = "🏠 نتائج البحث:\n" + "\n".join(lines)
    else:
        answer = "🏠 Search Results:\n" + "\n".join(lines)

    return {"success": True, "intent": "PROPERTY_SEARCH", "language": lang,
            "answer": answer, "properties": props_list}

# =============================================================================
# معالجة النية D — سؤال عام
# Handle Intent D — General Question
# =============================================================================
def handle_general_question(message, lang):
    reply_lang = "Arabic" if lang == 'ar' else "English"
    system_prompt = (
        f"You are Ahmed 2.0, a professional bilingual real estate assistant for "
        f"Smart Real Estate Oman. Answer politely and concisely in {reply_lang}. "
        f"Only answer questions related to real estate in Oman."
    )
    answer = call_openai(system_prompt, message)
    if not answer:
        if lang == 'ar':
            answer = "مرحباً! أنا أحمد، مساعدك العقاري الذكي. كيف يمكنني مساعدتك اليوم؟ 🏠"
        else:
            answer = "Hello! I'm Ahmed, your smart real estate assistant. How can I help you today? 🏠"

    return {"success": True, "intent": "GENERAL_QUESTION", "language": lang,
            "answer": answer, "properties": []}

# =============================================================================
# الدالة الرئيسية — Main Chat Response Function
# =============================================================================
def get_ai_response(prompt, user_id=None):
    """Main entry point for the AI chatbot — Ahmed 2.0."""
    msg_lower = prompt.lower()

    # ── اعتراض سريع للمفضلة / التواصل ──
    # Quick intercept for Favorite / Contact actions
    if any(word in msg_lower for word in ["احفظ", "favorite", "like", "save"]):
        recent = db.session.query(Property).order_by(Property.id.desc()).first()
        prop_id = recent.id if recent else 1
        return {"action": "add_favorite", "property_id": prop_id}

    if any(word in msg_lower for word in ["contact", "تواصل", "رسالة", "message"]):
        recent = db.session.query(Property).order_by(Property.id.desc()).first()
        a_id = recent.agent_id if recent else 1
        return {"action": "send_message", "agent_id": a_id, "message": prompt}

    # ── كشف اللغة وتصنيف النية ──
    lang = detect_language(prompt)
    intent = classify_intent(prompt)

    # ── توجيه حسب النية ──
    try:
        if intent == "AGENT_BEST_PROPERTIES":
            result = handle_agent_best_properties(prompt, lang)
        elif intent == "ROI_CALCULATION":
            result = handle_roi_calculation(prompt, lang)
        elif intent == "PROPERTY_SEARCH":
            result = handle_property_search(prompt, lang)
        else:
            result = handle_general_question(prompt, lang)
    except Exception as e:
        print(f"[INTENT HANDLER ERROR]: {e}")
        result = {
            "success": False, "intent": intent, "language": lang,
            "answer": "عذراً، حدث خطأ. حاول مرة أخرى. 😅" if lang == 'ar'
                      else "Sorry, an error occurred. Please try again. 😅",
            "properties": []
        }

    # ── تسجيل المحادثة — Log chat ──
    if user_id:
        try:
            new_log = ChatLog(
                user_message=prompt,
                bot_response=result.get("answer", ""),
                user_id=user_id
            )
            db.session.add(new_log)
            db.session.commit()
        except Exception as e:
            print(f"[CHAT LOG ERROR]: {e}")

    # ── التوافق مع الواجهة القديمة — Backward compatibility ──
    # The old frontend expects "text" and "properties" keys
    result["text"] = result.get("answer", "")
    if "investment_hotspots" not in result:
        result["investment_hotspots"] = []

    return result