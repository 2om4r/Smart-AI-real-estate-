# ai_utils.py — Ahmed 2.0: AI Real Estate Assistant for Oman
# المساعد الذكي "أحمد 2.0" — تحليل النوايا، البحث العقاري، الاستثمار، الذاكرة المحادثاتية

import os
import json
import re
import random
import time
import statistics

from openai import OpenAI
from models import Property, Area, ChatLog, Conversation
from extensions import db

# ─── OpenAI Client ────────────────────────────────────────────────────────────
# يُحمَّل المفتاح من متغيرات البيئة فقط — لا يُكتب في الكود أبدًا
api_key = os.environ.get("OPENAI_API_KEY")
client  = OpenAI(api_key=api_key)


# =============================================================================
# 📐 SCORING & ROI HELPERS
# أدوات حساب العائد والسكور
# =============================================================================

def get_roi_assumption(prop_type: str) -> float:
    """
    Return baseline annual ROI % for a property type.
    إرجاع العائد السنوي الأساسي حسب نوع العقار.
    """
    mapping = {
        'apartment':  7.0,
        'villa':      4.5,
        'townhouse':  6.0,
        'commercial': 8.0,
    }
    return mapping.get((prop_type or '').lower(), 5.0)


def calculate_score(p: dict, avg_price: float = 100000) -> int:
    """
    Composite investment score 0-100 for a property dict.
    سكور استثماري مركّب من 0 إلى 100 بناءً على السعر والموقع والعائد.
    """
    price    = float(p.get('price', avg_price))
    ptype    = p.get('type', 'Unknown')
    location = p.get('location', '')

    # جلب بيانات المنطقة من قاعدة البيانات
    area           = None
    location_score = 60
    demand         = 50
    growth         = 50

    if location:
        area = Area.query.filter(Area.name.ilike(f"%{location}%")).first()
    if area:
        location_score = area.score
        demand         = area.demand
        growth         = area.price_growth

    # نسبة السعر مقارنةً بمتوسط السوق
    price_ratio = (price / avg_price) if avg_price > 0 else 1.0
    if price_ratio < 0.8:  price_score = 90
    elif price_ratio < 1.0: price_score = 80
    elif price_ratio < 1.2: price_score = 60
    else:                   price_score = 40

    roi       = get_roi_assumption(ptype)
    roi_score = min(roi * 10, 100)   # 8% ROI → 80 points

    score = (location_score * 0.3 + price_score * 0.2 +
             roi_score * 0.2 + demand * 0.15 + growth * 0.15)
    return min(max(int(score), 0), 100)


# =============================================================================
# 📊 PORTFOLIO HELPERS
# أدوات ملخص البورتفوليو وتوصيات الاستثمار
# =============================================================================

def portfolio_summary(properties: list) -> dict:
    """
    Aggregate stats for an agent's property portfolio.
    إحصاءات إجمالية لمحفظة الوكيل العقارية.
    """
    if not properties:
        return {"total": 0, "avg_price": 0, "portfolio_score": 0,
                "type_distribution": {}, "avg_roi": 0}

    prices    = [float(p.get('price', 0)) for p in properties if p.get('price')]
    avg_price = statistics.mean(prices) if prices else 0

    type_dist = {}
    rois      = []
    for p in properties:
        t = p.get("type", "Other")
        type_dist[t] = type_dist.get(t, 0) + 1
        rois.append(get_roi_assumption(t))

    scores          = [calculate_score(p, avg_price) for p in properties]
    portfolio_score = int(statistics.mean(scores)) if scores else 0
    avg_roi         = statistics.mean(rois) if rois else 0

    return {
        "total":             len(properties),
        "avg_price":         int(avg_price),
        "portfolio_score":   portfolio_score,
        "type_distribution": type_dist,
        "avg_roi":           round(avg_roi, 1),
    }


def recommend_investment(properties: list) -> dict | None:
    """
    Pick the best investment property from a list and explain why.
    اختيار أفضل عقار استثماري وتفسير السبب.
    """
    if not properties:
        return None

    prices    = [float(p.get('price', 0)) for p in properties if p.get('price')]
    avg_price = statistics.mean(prices) if prices else 100000

    scored = []
    for p in properties:
        s = calculate_score(p, avg_price)
        scored.append({**p, "score": s, "roi": get_roi_assumption(p.get('type', 'Unknown'))})
    scored.sort(key=lambda x: x["score"], reverse=True)

    best    = scored[0]
    worst_2 = scored[-2:] if len(scored) >= 2 else []

    reason = "Chosen because: "
    if float(best.get('price', avg_price)) < avg_price:
        reason += f"price is below market avg (< OMR {int(avg_price)}). "
    if best['roi'] >= 6.0:
        reason += f"high rental demand ({best['roi']}% ROI). "
    if best['score'] > 80:
        reason += "extremely strong future growth potential. "
    if reason == "Chosen because: ":
        reason = "Balanced mix of location and demand factors."

    risk_level = "low" if best['score'] > 75 else "medium" if best['score'] > 50 else "high"

    return {
        "best_project":     best.get("location", "Unknown"),
        "type":             best.get("type", "Unknown"),
        "score":            best["score"],
        "roi":              best["roi"],
        "predicted_growth": "5-8%",
        "reason":           reason,
        "risk_level":       risk_level,
        "avg_price":        int(avg_price),
        "top_3":            scored[:3],
        "worst_2":          worst_2,
    }


# =============================================================================
# 🌱 DYNAMIC GROWTH RATES FROM AREA TABLE
# جلب معدلات النمو من جدول المناطق بدلاً من القيم الثابتة
# =============================================================================

def _get_area_growth_rate(location: str) -> dict:
    """
    Convert Area.price_growth (0-100 scale) to real annual growth rates.
    يحوّل نقاط النمو في جدول Area إلى نسب مئوية سنوية حقيقية.

    Scale mapping:
      price_growth 0  → 3% annual growth  (floor)
      price_growth 100 → 12% annual growth (ceiling)
    """
    area = None
    if location and location.strip() and location.lower() not in ("none", "null"):
        area = Area.query.filter(Area.name.ilike(f"%{location}%")).first()

    if area and area.price_growth is not None:
        # خطي: 0→0.03, 100→0.12
        base_growth = 0.03 + (area.price_growth / 100.0) * 0.09
    else:
        # احتياطي: القيم القديمة المشفّرة يدويًا
        loc_lower = (location or '').lower()
        if   "muscat"  in loc_lower or "مسقط"  in loc_lower: base_growth = 0.06
        elif "salalah" in loc_lower or "صلالة" in loc_lower: base_growth = 0.05
        elif "barka"   in loc_lower or "بركاء" in loc_lower: base_growth = 0.07
        elif "sohar"   in loc_lower or "صحار"  in loc_lower: base_growth = 0.06
        else:                                                  base_growth = 0.055

    return {
        "1y": round(base_growth * random.uniform(0.90, 1.10), 4),   # ±10% randomness
        "2y": round(base_growth * 2.0 * random.uniform(0.90, 1.10), 4),
        "5y": round(base_growth * 4.5 * random.uniform(0.90, 1.10), 4),
    }


# =============================================================================
# 🤖 MAIN CHAT FUNCTION
# دالة المحادثة الرئيسية مع إدارة الذاكرة والتتبع الكامل
# =============================================================================

def get_ai_response(prompt: str,
                    user_id: int | None = None,
                    conversation_id: int | None = None) -> dict:
    """
    Core Ahmed 2.0 pipeline:
      1. Quick-intercept shortcuts (favorite / contact)
      2. Load or create Conversation session
      3. Build history from conversation logs
      4. Call GPT-4o-mini to extract intent + reply text
      5. Filter properties from DB
      6. Sort + score + annotate properties
      7. Build follow-up questions
      8. Fetch investment hotspots
      9. Log everything (conversation_id, intent, language, tokens, time)
     10. Return enriched response including conversation_id

    المحادثة مع Ahmed 2.0:
      - تدير سياق المحادثة عبر conversation_id
      - تُسجّل كل رسالة مع النية والوقت والتوكنز
      - تُرجع conversation_id لكل استجابة
    """
    start_time = time.time()   # بداية قياس وقت الاستجابة
    msg_lower  = prompt.lower()

    # ── 1. Quick intercepts (no GPT call needed) ─────────────────────────────
    # اختصارات سريعة لا تحتاج استدعاء GPT

    if any(w in msg_lower for w in ["احفظ", "favorite", "like", "save"]):
        recent  = db.session.query(Property).order_by(Property.id.desc()).first()
        prop_id = recent.id if recent else 1
        return {"action": "add_favorite", "property_id": prop_id,
                "conversation_id": conversation_id}

    if any(w in msg_lower for w in ["contact", "تواصل", "رسالة", "message"]):
        recent = db.session.query(Property).order_by(Property.id.desc()).first()
        a_id   = recent.agent_id if recent else 1
        return {"action": "send_message", "agent_id": a_id, "message": prompt,
                "conversation_id": conversation_id}

    # ── 2. Load or create Conversation ────────────────────────────────────────
    # إنشاء محادثة جديدة إذا لم تكن موجودة، أو تحميل القديمة

    is_arabic = bool(re.search(r"[؀-ۿ]", prompt))
    language  = 'ar' if is_arabic else 'en'

    if conversation_id:
        conversation = Conversation.query.get(conversation_id)
        # إذا لم توجد (محذوفة / رقم خاطئ) أنشئ واحدة جديدة
        if not conversation:
            conversation = Conversation(user_id=user_id, language=language)
            db.session.add(conversation)
            db.session.flush()   # نحصل على ID بدون commit
    else:
        conversation = Conversation(user_id=user_id, language=language)
        db.session.add(conversation)
        db.session.flush()

    conversation_id = conversation.id   # نضمن أن المتغير محدَّث

    # ── 3. Build conversation history from ChatLog ────────────────────────────
    # بناء سياق المحادثة من الرسائل السابقة في نفس الجلسة

    history = []
    if conversation_id:
        past_logs = (ChatLog.query
                     .filter_by(conversation_id=conversation_id)
                     .order_by(ChatLog.timestamp.desc())
                     .limit(8)
                     .all())
        for log in reversed(past_logs):
            history.append({"role": "user",      "content": log.user_message})
            history.append({"role": "assistant",  "content": log.bot_response})

    # ── 4. GPT intent extraction ───────────────────────────────────────────────
    # استخراج النية والموقع والنوع والميزانية من الرسالة

    system_msg = {
        "role": "system",
        "content": (
            "You are Ahmed, a top-tier real estate AI agent in Oman. "
            "Automatically detect the language (Arabic or English) and reply ONLY in valid JSON. "
            "Extract from the user message:\n"
            "- location (e.g. Muscat, Salalah, Barka, Sohar, Al Mouj — empty string if none)\n"
            "- property_type (Villa, Apartment, Land, Townhouse, Commercial — empty if none)\n"
            "- budget (numeric max price in OMR; 0 if not mentioned)\n"
            "- intent (search | investment | compare | contact)\n"
            "- text (your conversational reply in the user's language)\n\n"
            "Respond ONLY with this JSON schema:\n"
            "{\n"
            "  \"location\": \"\",\n"
            "  \"property_type\": \"\",\n"
            "  \"budget\": 0,\n"
            "  \"intent\": \"search\",\n"
            "  \"text\": \"\"\n"
            "}"
        )
    }

    messages = [system_msg] + history + [{"role": "user", "content": prompt}]

    # قيم احتياطية إذا فشل GPT
    fallback_text   = ("جاري البحث عن أفضل الخيارات لك... 🏘️" if is_arabic
                       else "Searching for the best options for you... 🏘️")
    extracted_data  = {
        "location": "", "property_type": "", "budget": 0,
        "intent": "search", "text": fallback_text
    }
    tokens_used = None

    try:
        response      = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={"type": "json_object"}
        )
        extracted_data = json.loads(response.choices[0].message.content.strip())
        tokens_used    = response.usage.total_tokens   # تتبع التوكنز المستخدمة
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[Ahmed] GPT error: {e}")

    ai_text = extracted_data.get("text", fallback_text)
    intent  = extracted_data.get("intent", "search")

    # ── 5. Property DB query ───────────────────────────────────────────────────
    # البحث في قاعدة البيانات بناءً على الفلاتر المستخرجة

    query = Property.query

    loc = extracted_data.get("location", "")
    if loc and loc.strip() and loc.lower() not in ("none", "null"):
        query = query.filter(Property.location.ilike(f"%{loc}%"))

    ptype = extracted_data.get("property_type", "")
    if ptype and ptype.lower() not in ("none", "null", "any"):
        t = ptype.lower()
        if   "villa"      in t: query = query.filter_by(type="Villa")
        elif "apartment"  in t: query = query.filter_by(type="Apartment")
        elif "land"       in t: query = query.filter_by(type="Land")
        elif "townhouse"  in t: query = query.filter_by(type="Townhouse")
        elif "commercial" in t: query = query.filter_by(type="Commercial")

    budget = extracted_data.get("budget", 0)
    try:
        if float(budget) > 0:
            query = query.filter(Property.price <= float(budget))
    except (TypeError, ValueError):
        pass

    results = query.all()

    # ── 6. Fallback message when no results ───────────────────────────────────
    # رسالة احتياطية عند عدم وجود نتائج

    if not results and loc:
        if is_arabic:
            ai_text = (f"عذراً، لا نملك عقارات تطابق بحثك حالياً في {loc}. "
                       f"هل يمكنك توسيع نطاق البحث أو تجربة مناطق قريبة؟ 🏡")
        else:
            ai_text = (f"Sorry, we don't currently have exact matches in {loc}. "
                       f"Consider expanding your criteria or nearby areas. 🏡")

    # ── 7. Sort results ────────────────────────────────────────────────────────
    # ترتيب النتائج حسب النية

    if intent == "investment" or "best investment" in msg_lower or "استثم" in msg_lower:
        results.sort(key=lambda x: get_roi_assumption(x.type or 'Unknown'), reverse=True)
    elif "cheapest" in msg_lower or "ارخص" in msg_lower:
        results.sort(key=lambda x: (x.price or float('inf')))
    else:
        prices = [float(p.price) for p in results if p.price]
        avg    = sum(prices) / len(prices) if prices else 100000
        results.sort(
            key=lambda x: calculate_score(
                {'price': x.price, 'type': x.type, 'location': x.location}, avg
            ), reverse=True
        )

    top_results = results[:4]

    # ── 8. Dynamic reason templates ───────────────────────────────────────────
    # قوالب أسباب متنوعة لكل نوع عقار

    _reason_templates = {
        "Villa": [
            "High demand for luxury villas in {loc} driven by expat families and tourism growth",
            "Villa market in {loc} shows 8-12% annual appreciation due to limited supply",
            "Premium residential area in {loc} with upcoming infrastructure boosting value",
            "{loc} villas benefit from strong rental demand during tourism season",
        ],
        "Apartment": [
            "Apartments in {loc} attract steady rental income from working professionals",
            "Growing urban development in {loc} makes apartments a high-yield investment",
            "Strong occupancy rates in {loc} due to proximity to business districts",
            "{loc} apartment market benefits from government housing initiatives",
        ],
        "Land": [
            "Land prices in {loc} are appreciating rapidly due to upcoming developments",
            "Strategic land in {loc} with zoning approvals for commercial use",
            "Early-stage land investment in {loc} offers 15-25% growth over 5 years",
            "{loc} land benefits from new road connections planned for 2025-2027",
        ],
    }
    _default_reasons = [
        "Strong market fundamentals in {loc} with growing population",
        "Government investment in {loc} driving property value appreciation",
        "{loc} is an emerging investment hub with excellent growth prospects",
    ]
    _used_reasons: set = set()

    def _get_unique_reason(prop_type: str, location: str) -> str:
        templates = _reason_templates.get(prop_type, _default_reasons)
        available = [t for t in templates if t not in _used_reasons] or _default_reasons
        chosen    = random.choice(available)
        _used_reasons.add(chosen)
        return chosen.format(loc=location)

    # ── 9. Format top properties with dynamic ROI + growth from Area table ────
    # تنسيق العقارات مع العائد والنمو الديناميكي من جدول المناطق

    properties_to_return = []
    for best_p in top_results:
        t_low = (best_p.type or '').lower()

        # العائد الديناميكي حسب نوع العقار
        if   'villa'     in t_low: roi_val = round(random.uniform(6.0, 7.0), 1)
        elif 'apartment' in t_low: roi_val = round(random.uniform(7.0, 8.0), 1)
        elif 'land'      in t_low: roi_val = round(random.uniform(8.0, 10.0), 1)
        else:                      roi_val = round(random.uniform(5.0, 7.0), 1)

        # بونص عقارات تحت الإنشاء
        prop_status = getattr(best_p, 'status', 'available') or 'available'
        if prop_status == 'under_construction':
            roi_val = round(roi_val + 1.5, 1)

        price      = float(best_p.price or 0)
        yearly_inc = round(price * (roi_val / 100.0), 0)

        # جلب معدلات النمو من جدول Area (ديناميكي بدلاً من ثابت)
        growth = _get_area_growth_rate(best_p.location)
        p1 = round(price * (1 + growth["1y"]), 0)
        p2 = round(price * (1 + growth["2y"]), 0)
        p5 = round(price * (1 + growth["5y"]), 0)

        agent_name = best_p.agent.username if best_p.agent else "Unknown"

        properties_to_return.append({
            "id":           best_p.id,
            "title":        best_p.title,
            "location":     best_p.location,
            "price":        best_p.price,
            "roi":          roi_val,
            "yearly_income": yearly_inc,
            "price_1y":     p1,
            "price_2y":     p2,
            "price_5y":     p5,
            "reason":       _get_unique_reason(best_p.type or 'Unknown', best_p.location),
            "lat":          getattr(best_p, "latitude",  23.5880),
            "lng":          getattr(best_p, "longitude", 58.3829),
            "agent":        agent_name,
            "agent_id":     best_p.agent_id,
            "is_new":       getattr(best_p, 'is_new', False),
            "status":       prop_status,
        })

    # ── 10. Follow-up questions ────────────────────────────────────────────────
    # أسئلة المتابعة (عربي + إنجليزي)

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
    if properties_to_return:
        ai_text += "\n\n" + random.choice(followups_ar if is_arabic else followups_en)

    # ── 11. Investment hotspots from Area table ────────────────────────────────
    # نقاط الاستثمار الساخنة من جدول المناطق

    hotspot_query = Area.query
    if loc and loc.strip() and loc.lower() not in ("none", "null"):
        hotspot_query = hotspot_query.filter(Area.name.ilike(f"%{loc}%"))
    hotspot_areas = hotspot_query.order_by(Area.demand.desc()).limit(5).all()
    if not hotspot_areas:
        hotspot_areas = Area.query.order_by(Area.demand.desc()).limit(5).all()

    investment_hotspots = []
    for area in hotspot_areas:
        parts = []
        if area.demand      > 70: parts.append("high demand")
        if area.price_growth > 60: parts.append("strong price growth")
        if area.services    > 60: parts.append("excellent infrastructure")
        if not parts:             parts.append("emerging market potential")
        investment_hotspots.append({
            "name":   area.name,
            "lat":    area.latitude,
            "lng":    area.longitude,
            "reason": ", ".join(parts).capitalize(),
        })

    # ── 12. Log to ChatLog with full tracking ─────────────────────────────────
    # تسجيل الرسالة الكاملة في ChatLog مع جميع البيانات

    response_time = round(time.time() - start_time, 3)   # بالثواني

    try:
        log = ChatLog(
            conversation_id=conversation_id,
            user_id=user_id,
            user_message=prompt,
            bot_response=ai_text,
            intent=intent,
            language=language,
            tokens_used=tokens_used,
            response_time=response_time,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[Ahmed] DB log error: {e}")
        db.session.rollback()

    # ── 13. Return response ────────────────────────────────────────────────────
    # الاستجابة النهائية — conversation_id دائمًا موجود

    return {
        "text":                ai_text,
        "properties":          properties_to_return,
        "investment_hotspots": investment_hotspots,
        "conversation_id":     conversation_id,   # يُرسَل للفرونت ويُعاد مع كل طلب
    }
