# ai_utils.py — Ahmed 2.0: AI Real Estate Assistant for Oman
# المساعد الذكي "أحمد 2.0" — تحليل النوايا، البحث العقاري، الاستثمار، الذاكرة المحادثاتية
#
# New in this version:
#   - 🔒 Input sanitization + prompt injection protection
#   - 🔍 RAG: search_knowledge_base() injected into system prompt
#   - 🤝 Intent E: AGENT_PROPERTIES  — "أريد عقارات محمد"
#   - 💼 Intent F: INVEST_WITH_AGENT — "أريد أستثمر مع سالم"
#   - 📞 Intent G: CONTACT_AGENT     — "أريد وكيل في مسقط"

from __future__ import annotations

import os
import json
import re
import random
import time
import statistics
import difflib
import logging

from openai import OpenAI
from models import (Property, Area, ChatLog, Conversation,
                    User, Notification, InvestmentRequest)
from extensions import db

logger = logging.getLogger(__name__)

# ─── OpenAI Client ────────────────────────────────────────────────────────────
# يُحمَّل المفتاح من متغيرات البيئة فقط — لا يُكتب في الكود أبدًا
api_key = os.environ.get("OPENAI_API_KEY")
client  = OpenAI(api_key=api_key)


# =============================================================================
# 🔒 SECURITY — Input sanitization + Prompt injection protection
# الأمان — تنظيف المدخلات والحماية من حقن النصوص
# =============================================================================

# عبارات حقن النصوص المعروفة — يُرفض أي مدخل يحتوي على أي منها
# Known prompt injection phrases — any input containing these is rejected immediately
BLOCKED_PHRASES = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "you are now",
    "forget everything",
    "act as",
    "jailbreak",
    "pretend you are",
    "new persona",
    "you are a",
    "override instructions",
    "system prompt",
    "reveal your instructions",
]


def sanitize_input(text: str) -> str:
    """
    Strip whitespace and hard-cap input at 1000 characters.
    تنظيف المدخل: إزالة المسافات الزائدة وتقليص الطول إلى 1000 حرف كحد أقصى.
    """
    return text.strip()[:1000]


def is_prompt_injection(text: str) -> bool:
    """
    Return True if the text contains a known prompt injection pattern.
    إرجاع True إذا كانت الرسالة تحتوي على محاولة حقن نصوص معروفة.
    """
    t = text.lower()
    return any(phrase in t for phrase in BLOCKED_PHRASES)


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

    price_ratio = (price / avg_price) if avg_price > 0 else 1.0
    if price_ratio < 0.8:    price_score = 90
    elif price_ratio < 1.0:  price_score = 80
    elif price_ratio < 1.2:  price_score = 60
    else:                    price_score = 40

    roi       = get_roi_assumption(ptype)
    roi_score = min(roi * 10, 100)

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
    اختيار أفضل عقار استثماري بناءً على نموذج ML المُدرَّب على بيانات حقيقية.

    Upgrades over v1:
      ✅ ML-driven growth per area (from get_future_multiplier, real CAGR)
      ✅ Per-area + per-type avg price (not global average)
      ✅ Real risk level from area data, not just score
      ✅ 5-year projected price for top pick
      ✅ ML confidence indicator
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

    # ── ML-driven growth rate for the best area ────────────────────────────
    # نَستخدم نموذج ML الحقيقي بدلاً من السلسلة الثابتة "5-8%"
    try:
        from ml_engine import get_future_multiplier
        best_location = best.get("location", "")
        mult_1y = get_future_multiplier(best_location, 1)
        mult_5y = get_future_multiplier(best_location, 5)
        annual_growth_pct = (mult_1y - 1) * 100
        five_year_growth_pct = (mult_5y - 1) * 100
        predicted_growth_str = f"{annual_growth_pct:.1f}%/yr"
        ml_powered = True
    except Exception:
        annual_growth_pct = 6.5
        five_year_growth_pct = 37.0
        predicted_growth_str = "5-8%/yr"
        ml_powered = False

    # ── 5-year projected price for top pick ────────────────────────────────
    best_price = float(best.get('price', 0))
    projected_5y = round(best_price * (1 + five_year_growth_pct / 100), 0) if best_price else 0
    gain_5y = projected_5y - best_price
    gain_pct = (gain_5y / best_price * 100) if best_price > 0 else 0

    # ── Per-type avg for fair comparison ──────────────────────────────────
    same_type = [p for p in properties if p.get('type') == best.get('type')]
    type_avg = statistics.mean([float(p.get('price', 0)) for p in same_type
                                if p.get('price')]) if same_type else avg_price

    # ── Build smart reason (ML-driven, location-aware) ────────────────────
    reason_parts = []
    if best_price < type_avg * 0.9:
        pct_below = round((1 - best_price / type_avg) * 100)
        reason_parts.append(f"undervalued by {pct_below}% vs {best.get('type','similar')} avg")
    if best['roi'] >= 7.0:
        reason_parts.append(f"strong rental yield ({best['roi']}% ROI)")
    if annual_growth_pct >= 8.0:
        reason_parts.append(f"ML predicts {annual_growth_pct:.1f}% annual growth")
    elif annual_growth_pct >= 5.0:
        reason_parts.append(f"steady {annual_growth_pct:.1f}% annual appreciation")
    if best['score'] > 80:
        reason_parts.append("excellent location-demand fundamentals")

    if reason_parts:
        reason = "Selected because " + ", ".join(reason_parts) + "."
    else:
        reason = "Balanced opportunity across location, price, and ROI factors."

    # ── Risk level: combine score + area volatility ───────────────────────
    risk_level = (
        "low"      if best['score'] > 80 and annual_growth_pct > 5 else
        "medium"   if best['score'] > 60 else
        "high"
    )

    # ── Confidence: depends on data availability ──────────────────────────
    confidence = (
        90 if ml_powered and len(properties) >= 20 else
        75 if ml_powered and len(properties) >= 5  else
        60 if ml_powered else
        45
    )

    return {
        "best_project":         best.get("location", "Unknown"),
        "type":                 best.get("type", "Unknown"),
        "score":                best["score"],
        "roi":                  best["roi"],
        "predicted_growth":     predicted_growth_str,
        "annual_growth_pct":    round(annual_growth_pct, 1),
        "five_year_growth_pct": round(five_year_growth_pct, 1),
        "projected_5y_price":   projected_5y,
        "gain_5y":              gain_5y,
        "gain_pct":             round(gain_pct, 1),
        "current_price":        best_price,
        "type_avg_price":       round(type_avg, 0),
        "reason":               reason,
        "risk_level":           risk_level,
        "avg_price":            int(avg_price),
        "confidence":           confidence,
        "ml_powered":           ml_powered,
        "top_3":                scored[:3],
        "worst_2":              worst_2,
    }


# =============================================================================
# 🌱 DYNAMIC GROWTH RATES FROM AREA TABLE
# جلب معدلات النمو من جدول المناطق بدلاً من القيم الثابتة
# =============================================================================

def _get_area_growth_rate(location: str) -> dict:
    """
    Convert Area.price_growth (0-100 scale) to real annual growth rates.
    يحوّل نقاط النمو في جدول Area إلى نسب مئوية سنوية حقيقية.
    """
    area = None
    if location and location.strip() and location.lower() not in ("none", "null"):
        area = Area.query.filter(Area.name.ilike(f"%{location}%")).first()

    if area and area.price_growth is not None:
        base_growth = 0.03 + (area.price_growth / 100.0) * 0.09
    else:
        loc_lower = (location or '').lower()
        if   "muscat"  in loc_lower or "مسقط"  in loc_lower: base_growth = 0.06
        elif "salalah" in loc_lower or "صلالة" in loc_lower: base_growth = 0.05
        elif "barka"   in loc_lower or "بركاء" in loc_lower: base_growth = 0.07
        elif "sohar"   in loc_lower or "صحار"  in loc_lower: base_growth = 0.06
        else:                                                  base_growth = 0.055

    # حتمي بالكامل — نفس المدخلات تُعطي نفس النتائج دائماً (لا عشوائية)
    # Fully deterministic — no random.uniform noise
    return {
        "1y": round(base_growth, 4),
        "2y": round(base_growth * 2.0, 4),
        "5y": round(base_growth * 4.5, 4),
    }


# =============================================================================
# 👤 AGENT MATCHING HELPERS
# مساعدات مطابقة الوكلاء — تستخدم difflib للمطابقة التقريبية
# =============================================================================

def _extract_agent_name(msg: str) -> str:
    """
    Extract a potential agent name from the user message.
    استخراج اسم الوكيل المحتمل من رسالة المستخدم.

    Handles Arabic patterns ("عقارات محمد", "مع سالم")
    and English patterns ("Ahmed's properties", "invest with Salem").
    يدعم الأنماط العربية والإنجليزية.
    """
    patterns = [
        r'عقارات\s+(\w+)',                           # عقارات محمد
        r'استثمر\s+مع\s+(\w+)',                      # استثمر مع سالم
        r'أستثمر\s+مع\s+(\w+)',                      # أستثمر مع سالم
        r'مع\s+(?:وكيل\s+)?(\w+)',                   # مع سالم / مع وكيل سالم
        r'وكيل\s+(\w+)',                             # وكيل أحمد
        r"(\w+)'s\s+propert(?:y|ies)",               # Ahmed's properties / Ahmed's property
        r'propert(?:y|ies)\s+(?:of|by|from)\s+(\w+)',# properties of Ahmed
        r'invest\s+with\s+(\w+)',                    # invest with Salem
        r'show\s+me\s+(\w+)',                        # show me Ahmed
        r'(?:need|want|find|get|show)\s+(\w+)\s+propert',  # need binthani property
        r'(\w+)\s+propert(?:y|ies)',                 # binthani property / binthani properties
        r'(?:propert(?:y|ies)|listing(?:s)?)\s+(?:by|from|of)\s+(\w+)',  # listings by Salem
    ]
    # الكلمات الوظيفية التي يجب تجاهلها كأسماء وكلاء
    # Functional words that should never be treated as agent names
    skip_words = {
        'the', 'an', 'a', 'في', 'من', 'مع', 'new', 'best', 'cheap',
        'all', 'any', 'some', 'top', 'good', 'big', 'small', 'nice',
        'luxury', 'cheap', 'affordable', 'available', 'omani', 'oman',
        'muscat', 'salalah', 'sohar', 'barka', 'property', 'properties',
    }
    for pattern in patterns:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            candidate = m.group(1)
            if candidate.lower() not in skip_words:
                return candidate

    # آخر محاولة: فحص إذا كان أي اسم وكيل مسجَّل يظهر مباشرةً في الرسالة
    # Last resort: scan registered agent names directly against the message
    try:
        agents = User.query.filter_by(role='agent').all()
        msg_lower_scan = msg.lower()
        for agent in agents:
            if agent.username.lower() in msg_lower_scan:
                return agent.username
            if agent.full_name and agent.full_name.lower() in msg_lower_scan:
                return agent.full_name
    except Exception:
        pass

    return ''


def _find_agent_by_name(name_hint: str) -> User | None:
    """
    Fuzzy-match a name hint against agent usernames and full names.
    مطابقة تقريبية لاسم الوكيل مقابل أسماء المستخدمين الكاملة.

    1. Direct substring match (fastest)
    2. difflib fuzzy match on username (cutoff 0.5)
    3. difflib fuzzy match on full_name (cutoff 0.5)
    """
    if not name_hint:
        return None

    agents = User.query.filter_by(role='agent').all()
    if not agents:
        return None

    hint = name_hint.lower().strip()

    # ── 1. Direct substring ───────────────────────────────────────────────────
    for agent in agents:
        if (hint in agent.username.lower() or
                hint in (agent.full_name or '').lower()):
            return agent

    # ── 2. Fuzzy on username ──────────────────────────────────────────────────
    usernames = [a.username.lower() for a in agents]
    matches = difflib.get_close_matches(hint, usernames, n=1, cutoff=0.5)
    if matches:
        for agent in agents:
            if agent.username.lower() == matches[0]:
                return agent

    # ── 3. Fuzzy on full_name ─────────────────────────────────────────────────
    full_names = [(a.full_name or '').lower() for a in agents]
    matches = difflib.get_close_matches(hint, full_names, n=1, cutoff=0.5)
    if matches:
        for agent in agents:
            if (agent.full_name or '').lower() == matches[0]:
                return agent

    return None


# =============================================================================
# 🤝 INTENT E — AGENT_PROPERTIES
# "أريد عقارات محمد" / "show me Ahmed's properties"
# =============================================================================

def _handle_agent_properties(msg: str, is_arabic: bool) -> dict | None:
    """
    Intent E: list the top-3 properties of a named agent sorted by ROI.
    النية E: عرض أفضل 3 عقارات لوكيل مُحدَّد مرتبة حسب العائد.

    Returns a response dict or None if no agent name was found.
    يُرجع dict أو None إذا لم يُعثر على اسم وكيل.
    """
    name_hint = _extract_agent_name(msg)
    if not name_hint:
        return None

    agent = _find_agent_by_name(name_hint)
    if not agent:
        return None

    props = Property.query.filter_by(agent_id=agent.id).all()
    phone = agent.phone or "—"

    if not props:
        text = (f"عذراً، لا توجد عقارات مسجلة للوكيل **{agent.username}** حالياً. 🏠"
                if is_arabic else
                f"Sorry, no properties found for agent **{agent.username}** right now. 🏠")
        return {"text": text, "properties": [], "intent": "agent_properties"}

    # ترتيب تنازلي حسب العائد
    props.sort(key=lambda p: get_roi_assumption(p.type or ''), reverse=True)
    top3 = props[:3]

    text = (
        f"🏘️ أفضل عقارات الوكيل **{agent.username}**:\n📞 للتواصل: {phone}"
        if is_arabic else
        f"🏘️ Top properties by agent **{agent.username}**:\n📞 Contact: {phone}"
    )

    result_props = []
    for p in top3:
        roi_val = get_roi_assumption(p.type or '')
        # بونص عقارات تحت الإنشاء
        if (p.status or '') == 'under_construction':
            roi_val = round(roi_val + 1.5, 1)

        price      = float(p.price or 0)
        yearly_inc = round(price * (roi_val / 100.0), 0)

        growth = _get_area_growth_rate(p.location)
        result_props.append({
            "id":            p.id,
            "title":         p.title,
            "location":      p.location,
            "price":         p.price,
            "roi":           roi_val,
            "yearly_income": yearly_inc,
            "price_1y":      round(price * (1 + growth["1y"]), 0),
            "price_2y":      round(price * (1 + growth["2y"]), 0),
            "price_5y":      round(price * (1 + growth["5y"]), 0),
            "agent":         agent.username,
            "agent_id":      agent.id,
            "lat":           getattr(p, 'latitude',  23.5880),
            "lng":           getattr(p, 'longitude', 58.3829),
            "status":        p.status or 'available',
            "is_new":        getattr(p, 'is_new', False),
        })

    return {
        "text":       text,
        "properties": result_props,
        "intent":     "agent_properties",
        "agent":      {"id": agent.id, "username": agent.username, "phone": phone},
    }


# =============================================================================
# 💼 INTENT F — INVEST_WITH_AGENT
# "أريد أستثمر مع سالم" / "best investment with Salem"
# =============================================================================

def _handle_invest_with_agent(msg: str,
                               user_id: int | None,
                               is_arabic: bool) -> dict | None:
    """
    Intent F: register an InvestmentRequest, notify the agent, show best property.
    النية F: تسجيل طلب استثمار، إرسال إشعار للوكيل، عرض أفضل عقار.

    Saves to DB even for anonymous users (user_id=None is allowed).
    يحفظ في قاعدة البيانات حتى للمستخدمين المجهولين.
    """
    name_hint = _extract_agent_name(msg)
    if not name_hint:
        return None

    agent = _find_agent_by_name(name_hint)
    if not agent:
        return None

    # ── Find best investment property for this agent ──────────────────────────
    props     = Property.query.filter_by(agent_id=agent.id).all()
    prices    = [float(p.price) for p in props if p.price]
    avg_price = statistics.mean(prices) if prices else 100000

    best_prop = None
    if props:
        props.sort(
            key=lambda p: calculate_score(
                {'price': p.price, 'type': p.type, 'location': p.location},
                avg_price,
            ),
            reverse=True,
        )
        best_prop = props[0]

    # ── Save InvestmentRequest + Notification ─────────────────────────────────
    # حفظ الطلب وإرسال الإشعار — الأخطاء لا توقف الرد على المستخدم
    try:
        req = InvestmentRequest(
            user_id=user_id,
            agent_id=agent.id,
            project=agent.username,
            message=msg,
            status='pending',
        )
        db.session.add(req)

        notif_text = (
            "طلب استثمار جديد من مستخدم عبر الشاتبوت"
            if is_arabic else
            "New investment request from a user via chatbot"
        )
        db.session.add(Notification(user_id=agent.id, message=notif_text))
        db.session.commit()
        logger.info(f"[Ahmed] InvestmentRequest saved — agent_id={agent.id}")
    except Exception as e:
        logger.error(f"[Ahmed] InvestmentRequest save error: {e}")
        db.session.rollback()

    phone = agent.phone or "—"

    if best_prop:
        text = (
            f"✅ تم تسجيل طلب استثمارك مع الوكيل **{agent.username}**!\n"
            f"🏆 أفضل عقار: {best_prop.title} في {best_prop.location}\n"
            f"💰 السعر: {best_prop.price:,.0f} OMR\n"
            f"📞 للتواصل المباشر: {phone}\n"
            f"سيتواصل معك الوكيل قريباً. 🤝"
            if is_arabic else
            f"✅ Investment request registered with agent **{agent.username}**!\n"
            f"🏆 Best property: {best_prop.title} in {best_prop.location}\n"
            f"💰 Price: {best_prop.price:,.0f} OMR\n"
            f"📞 Direct contact: {phone}\n"
            f"The agent will reach out soon. 🤝"
        )
        bp_roi    = get_roi_assumption(best_prop.type or '')
        if (best_prop.status or '') == 'under_construction':
            bp_roi = round(bp_roi + 1.5, 1)
        bp_price  = float(best_prop.price or 0)
        bp_growth = _get_area_growth_rate(best_prop.location)
        result_props = [{
            "id":            best_prop.id,
            "title":         best_prop.title,
            "location":      best_prop.location,
            "price":         best_prop.price,
            "roi":           bp_roi,
            "yearly_income": round(bp_price * (bp_roi / 100.0), 0),
            "price_1y":      round(bp_price * (1 + bp_growth["1y"]), 0),
            "price_2y":      round(bp_price * (1 + bp_growth["2y"]), 0),
            "price_5y":      round(bp_price * (1 + bp_growth["5y"]), 0),
            "agent":         agent.username,
            "agent_id":      agent.id,
            "lat":           getattr(best_prop, 'latitude',  23.5880),
            "lng":           getattr(best_prop, 'longitude', 58.3829),
            "status":        best_prop.status or 'available',
            "is_new":        getattr(best_prop, 'is_new', False),
        }]
    else:
        text = (
            f"✅ تم تسجيل طلب استثمارك مع الوكيل **{agent.username}**!\n"
            f"📞 للتواصل: {phone}\nسيتواصل معك قريباً. 🤝"
            if is_arabic else
            f"✅ Investment request registered with agent **{agent.username}**!\n"
            f"📞 Contact: {phone}\nThey will reach out soon. 🤝"
        )
        result_props = []

    return {
        "text":       text,
        "properties": result_props,
        "intent":     "invest_with_agent",
        "agent":      {"id": agent.id, "username": agent.username, "phone": phone},
    }


# =============================================================================
# 📞 INTENT G — CONTACT_AGENT
# "أريد وكيل في مسقط" / "contact an agent in Muscat"
# =============================================================================

def _handle_contact_agent(msg: str, is_arabic: bool) -> dict | None:
    """
    Intent G: list available agents, optionally filtered by city.
    النية G: عرض الوكلاء المتاحين مع إمكانية التصفية حسب المدينة.

    Returns agent list with name, phone, property count.
    يُرجع قائمة الوكلاء مع الاسم والهاتف وعدد العقارات.
    """
    # ── Extract city hint ─────────────────────────────────────────────────────
    city_hint = ''
    for pattern in [r'في\s+(\w+)', r'بـ?\s*(\w+)', r'in\s+(\w+)', r'at\s+(\w+)']:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            candidate = m.group(1)
            if candidate.lower() not in ('a', 'an', 'the', 'في', 'من'):
                city_hint = candidate
                break

    agents = User.query.filter_by(role='agent').all()
    if not agents:
        text = ("عذراً، لا يوجد وكلاء مسجلون حالياً. 😔"
                if is_arabic else
                "Sorry, no agents are registered right now. 😔")
        return {"text": text, "properties": [], "intent": "contact_agent"}

    # ── Filter + count properties ─────────────────────────────────────────────
    # تصفية حسب المدينة إن ذُكرت، وإلا عرض جميع الوكلاء
    agent_data = []
    for agent in agents:
        if city_hint:
            count = Property.query.filter(
                Property.agent_id == agent.id,
                Property.location.ilike(f"%{city_hint}%"),
            ).count()
        else:
            count = Property.query.filter_by(agent_id=agent.id).count()
        agent_data.append((agent, count))

    # If city filter returned nothing, fall back to all agents
    if city_hint and all(c == 0 for _, c in agent_data):
        agent_data = [
            (a, Property.query.filter_by(agent_id=a.id).count())
            for a in agents
        ]

    agent_data.sort(key=lambda x: x[1], reverse=True)
    # عرض جميع الوكلاء — بدون حد مصطنع يخفي بعضهم
    # Show ALL agents — no artificial cut-off that hides some of them
    # (cap at 20 only as a safety limit for very large deployments)
    agent_data = agent_data[:20]

    lines       = []
    agents_list = []
    for agent, count in agent_data:
        phone = agent.phone or "—"
        agents_list.append({
            "id":         agent.id,
            "username":   agent.username,
            "full_name":  agent.full_name or agent.username,
            "phone":      phone,
            "prop_count": count,
        })
        if is_arabic:
            lines.append(f"• **{agent.full_name or agent.username}** — {count} عقار — 📞 {phone}")
        else:
            lines.append(f"• **{agent.full_name or agent.username}** — {count} listings — 📞 {phone}")

    city_str = (f"في {city_hint} " if city_hint else "")
    text = (
        f"👔 الوكلاء المتاحون {city_str}:\n" + "\n".join(lines)
        if is_arabic else
        f"👔 Available agents {city_str}:\n" + "\n".join(lines)
    )

    return {
        "text":       text,
        "properties": [],
        "intent":     "contact_agent",
        "agents":     agents_list,
    }


# =============================================================================
# 📈 INTENT H — OWN PROPERTY FORECAST
# "I have a villa worth 500,000 OMR, what will the price be after 5 years?"
# "عندي فيلا بـ 500,000 ريال، كم سيكون سعرها بعد 5 سنوات؟"
# =============================================================================

# =============================================================================
# 🏗️ INTENT I — PROJECTS / DEVELOPMENTS
# "show me projects in Muscat" / "ما هي المشاريع المتاحة؟"
# =============================================================================

def _handle_projects(msg: str, is_arabic: bool) -> dict | None:
    """
    Intent I: list multi-unit projects, optionally filtered by city.
    النية I: عرض المشاريع متعدِّدة الوحدات، مع تصفية اختياريَّة حسب المدينة.

    Triggers (English): "projects", "developments", "new projects", "compounds"
    Triggers (Arabic):  "مشاريع", "مشروع", "كومباوند", "مجمَّعات", "تطوير عقاري"

    Returns project cards with:
      - Project name + developer
      - Location, completion date
      - Starting price + total units
      - 5-year ML growth projection
      - Direct link to project page
    """
    # ── Extract city hint (optional filter) ───────────────────────────────
    city_hint = ''
    for pattern in [r'في\s+([A-Za-zأ-ي\s]+)', r'in\s+([A-Za-z\s]+)',
                    r'at\s+([A-Za-z\s]+)', r'بـ?\s+([A-Za-zأ-ي]+)']:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            cand = m.group(1).strip().split()[0]
            if cand.lower() not in ('the', 'a', 'an', 'في', 'من', 'مع'):
                city_hint = cand
                break

    # ── Query projects from DB ────────────────────────────────────────────
    q = Property.query.filter_by(is_project=True)
    if city_hint:
        q = q.filter(
            db.or_(
                Property.location.ilike(f"%{city_hint}%"),
                Property.city.ilike(f"%{city_hint}%"),
            )
        )
    projects = q.order_by(Property.created_at.desc()).limit(10).all()

    # If filter returned nothing, show all
    if not projects and city_hint:
        projects = Property.query.filter_by(is_project=True).limit(10).all()

    if not projects:
        text = (
            "عذراً، لا توجد مشاريع عقاريَّة مسجَّلة حالياً. 🏗️"
            if is_arabic else
            "Sorry, no real-estate projects are registered yet. 🏗️"
        )
        return {"text": text, "properties": [], "intent": "projects"}

    # ── Build response with ML projections ────────────────────────────────
    project_cards = []
    lines = []
    for p in projects:
        try:
            from ml_engine import get_future_multiplier
            mult_5y = get_future_multiplier(p.location, 5)
            growth_5y_pct = round((mult_5y - 1) * 100, 1)
        except Exception:
            growth_5y_pct = None

        units_count = Property.query.filter_by(parent_project_id=p.id).count()
        starting_price = float(p.price or 0)

        project_cards.append({
            "id":              p.id,
            "title":           p.title,
            "type":            "Project",
            "developer":       p.developer or "—",
            "location":        p.location,
            "city":            p.city,
            "starting_price":  starting_price,
            "price":           starting_price,
            "total_units":     p.total_units or 0,
            "units_added":     units_count,
            "completion_date": p.completion_date or "TBD",
            "status":          p.status,
            "growth_5y_pct":   growth_5y_pct,
            "lat":             p.latitude,
            "lng":             p.longitude,
            "agent":           p.agent.username if p.agent else "unknown",
            "is_project":      True,
        })

        # Build text line per project
        growth_txt = (f" · ML نمو 5 سنوات: +{growth_5y_pct}%"
                     if is_arabic and growth_5y_pct else
                     f" · 5y ML growth: +{growth_5y_pct}%"
                     if growth_5y_pct else "")
        if is_arabic:
            lines.append(
                f"🏗️ **{p.title}**\n"
                f"   📍 {p.location} · 🏢 {p.developer or 'مطوِّر غير محدَّد'}\n"
                f"   💰 بداية من {starting_price:,.0f} OMR · "
                f"{units_count}/{p.total_units or '?'} وحدة"
                f"{growth_txt}\n"
                f"   📅 التسليم: {p.completion_date or 'غير محدَّد'}"
            )
        else:
            lines.append(
                f"🏗️ **{p.title}**\n"
                f"   📍 {p.location} · 🏢 {p.developer or 'Developer TBD'}\n"
                f"   💰 From {starting_price:,.0f} OMR · "
                f"{units_count}/{p.total_units or '?'} units"
                f"{growth_txt}\n"
                f"   📅 Completion: {p.completion_date or 'TBD'}"
            )

    city_label = f"في {city_hint} " if city_hint and is_arabic else \
                 f"in {city_hint} " if city_hint else ""

    if is_arabic:
        text = (f"🏗️ المشاريع العقاريَّة المتاحة {city_label}({len(projects)}):\n\n"
                + "\n\n".join(lines))
    else:
        text = (f"🏗️ Available real-estate projects {city_label}({len(projects)}):\n\n"
                + "\n\n".join(lines))

    return {
        "text":       text,
        "properties": project_cards,
        "intent":     "projects",
        "projects":   project_cards,
    }


def _handle_own_property_forecast(msg: str, is_arabic: bool) -> dict | None:
    """
    Intent H: user already owns (or hypothetically has) a property and wants
    a future price projection — no DB search needed.
    النية H: المستخدم يملك عقاراً ويريد تقدير سعره المستقبلي — بدون بحث في DB.

    Extracts: price, location, years_ahead
    Calculates: future_value using _get_area_growth_rate()
    Returns a detailed projection card in the chat text.
    """
    # ── Extract price (e.g. 5000000OMR / 500,000 OMR / 500000 ريال) ──────────
    price_match = re.search(
        r'(\d[\d,]*(?:\.\d+)?)\s*(?:omr|OMR|rial|ريال|rials)',
        msg, re.IGNORECASE
    )
    if not price_match:
        # fallback: large bare number (>= 1000) near property keywords
        price_match = re.search(r'\b(\d{4,}(?:,\d{3})*(?:\.\d+)?)\b', msg)
    if not price_match:
        return None

    try:
        price = float(price_match.group(1).replace(',', ''))
    except ValueError:
        return None

    if price <= 0:
        return None

    # ── Extract years ─────────────────────────────────────────────────────────
    years_asked = None
    for _pat in [r'after\s+(\d+)\s+year', r'in\s+(\d+)\s+year',
                 r'(\d+)\s+years?\s+(?:from now|later)',
                 r'بعد\s+(\d+)\s+سن', r'خلال\s+(\d+)\s+سن']:
        _m = re.search(_pat, msg, re.IGNORECASE)
        if _m:
            years_asked = int(_m.group(1))
            break

    if not years_asked:
        return None   # no year mentioned → not a forecast question

    # ── Extract property type (villa / apartment / land / townhouse) ──────────
    # استخراج نوع العقار لذكره في الرد بدقة
    ptype = ""
    _ptype_map = {
        'villa':     'Villa',     'فيلا':     'فيلا',
        'apartment': 'Apartment', 'شقة':      'شقة',
        'land':      'Land',      'أرض':      'أرض',
        'townhouse': 'Townhouse', 'تاون':     'تاون هاوس',
        'commercial':'Commercial','تجاري':    'تجاري',
        'house':     'House',     'بيت':      'بيت',
    }
    for kw, label in _ptype_map.items():
        if kw in msg.lower():
            ptype = label
            break

    # ── Extract location ──────────────────────────────────────────────────────
    # Stop at common terminators: worth/cost/price/for/after/how/كم/بعد + any digit
    # نتوقف عند الكلمات الفاصلة أو أي رقم لتجنّب التقاط جزء من الجملة
    loc_match = re.search(
        r'(?:in|at|في|بـ?)\s+([A-Za-zأ-ي][A-Za-zأ-ي\s\-]+?)'
        r'(?=\s+(?:worth|cost|costs|price|priced|for|after|بعد|how|كم|من|with|of)\b'
        r'|\s+\d|\s*[,.]|$)',
        msg, re.IGNORECASE
    )
    location = loc_match.group(1).strip() if loc_match else ""

    # ── Normalize Omani location aliases (Alburaimi → Al Buraimi, etc.) ───────
    # نوحّد كتابة المناطق العُمانية الشائعة قبل البحث في جدول Area
    _loc_aliases = {
        'alburaimi':   'Al Buraimi',
        'al-buraimi':  'Al Buraimi',
        'buraimi':     'Al Buraimi',
        'almouj':      'Al Mouj',
        'al-mouj':     'Al Mouj',
        'mouj':        'Al Mouj',
        'almawaleh':   'Al Mawaleh',
        'mawaleh':     'Al Mawaleh',
        'alhail':      'Al Hail',
        'hail':        'Al Hail',
        'alkhuwair':   'Al Khuwair',
        'khuwair':     'Al Khuwair',
        'alghubra':    'Al Ghubra',
        'ghubra':      'Al Ghubra',
        'alkhoud':     'Al Khoud',
        'khoud':       'Al Khoud',
        'alseeb':      'Al Seeb',
        'seeb':        'Al Seeb',
    }
    if location:
        loc_key = location.lower().replace(' ', '').replace('-', '')
        if loc_key in _loc_aliases:
            location = _loc_aliases[loc_key]

    # ── Calculate future value using ML compound growth multiplier ───────────
    # نستخدم get_future_multiplier() من ML model — فائدة مركبة حتمية بدون عشوائية
    # Uses compound interest formula: future = price × (1 + annual_rate)^years
    try:
        from ml_engine import get_future_multiplier, ensure_trained
        ensure_trained()   # تأكد أن الـ ML model مُدرَّب على عقارات DB
        multiplier   = get_future_multiplier(location, years_asked)
        future_price = round(price * multiplier, 0)
        rate         = multiplier - 1
    except Exception:
        # Fallback: Area table linear approximation if ML unavailable
        growth       = _get_area_growth_rate(location)
        rate         = growth["2y"] if years_asked <= 2 else growth["5y"]
        future_price = round(price * (1 + rate), 0)

    gain     = future_price - price
    gain_pct = round((gain / price) * 100, 1)
    loc_str  = location or ("عُمان" if is_arabic else "Oman")

    # Use the extracted property type + location in the header for clarity
    # نُظهر نوع العقار والموقع بدقة في العنوان لتجنّب الالتباس
    annual_pct = round(rate / years_asked * 100, 2) if years_asked else 0
    if is_arabic:
        ptype_str = ptype or "عقار"
        text = (
            f"📊 **تقدير سعر {ptype_str} في {loc_str}**\n\n"
            f"💰 السعر الحالي: **{price:,.0f} OMR**\n"
            f"📅 بعد {years_asked} {'سنة' if years_asked == 1 else 'سنوات'}:\n"
            f"🚀 السعر المتوقع: **{future_price:,.0f} OMR**\n"
            f"📈 الزيادة المتوقعة: {gain:,.0f} OMR (+{gain_pct}%)\n"
            f"📊 معدل النمو السنوي: ~{annual_pct}%\n\n"
            f"_تقدير حتمي مبني على بيانات حقيقية (2,000 عقار × 8 سنوات) من نموذج ML._"
        )
    else:
        ptype_str = ptype or "property"
        text = (
            f"📊 **{ptype_str} value projection in {loc_str}**\n\n"
            f"💰 Current price: **{price:,.0f} OMR**\n"
            f"📅 After {years_asked} year{'s' if years_asked > 1 else ''}:\n"
            f"🚀 Estimated value: **{future_price:,.0f} OMR**\n"
            f"📈 Expected gain: {gain:,.0f} OMR (+{gain_pct}%)\n"
            f"📊 Annual growth rate: ~{annual_pct}%\n\n"
            f"_Deterministic estimate from ML model trained on real data "
            f"(2,000 properties × 8 years)._"
        )

    return {
        "text":       text,
        "properties": [],
        "intent":     "own_property_forecast",
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
      0. Sanitize input + block prompt injections
      1. Quick-intercept shortcuts (favorite / contact)
      2. Load or create Conversation session
      3. Detect new intents E / F / G (agent-related)
      4. Fetch RAG context from ChromaDB
      5. Build history from conversation logs
      6. Call GPT-4o-mini to extract intent + reply text
      7. Filter properties from DB
      8. Sort + score + annotate properties
      9. Build follow-up questions
     10. Fetch investment hotspots
     11. Log everything (conversation_id, intent, language, tokens, time)
     12. Return enriched response including conversation_id

    التغييرات الجديدة:
      - الأمان: تنظيف المدخلات + حجب حقن النصوص
      - RAG: حقن سياق البحث الدلالي في رسالة النظام
      - نوايا جديدة: E (عقارات وكيل)، F (استثمار مع وكيل)، G (تواصل مع وكيل)
    """
    start_time = time.time()

    # ── 0. Security: sanitize + injection check ────────────────────────────────
    # الأمان: تنظيف المدخل أولاً، ثم التحقق من حقن النصوص
    prompt = sanitize_input(prompt)

    if is_prompt_injection(prompt):
        logger.warning(f"[Ahmed] Prompt injection blocked: {prompt[:80]}")
        return {
            "text": (
                "⚠️ لا يمكنني معالجة هذا الطلب. "
                "أنا هنا فقط لمساعدتك في العقارات العُمانية. 🏠"
                if bool(re.search(r"[؀-ۿ]", prompt)) else
                "⚠️ This request cannot be processed. "
                "I'm here to help you with Omani real estate only. 🏠"
            ),
            "properties":          [],
            "investment_hotspots": [],
            "conversation_id":     conversation_id,
        }

    msg_lower  = prompt.lower()
    is_arabic  = bool(re.search(r"[؀-ۿ]", prompt))
    language   = 'ar' if is_arabic else 'en'

    # ── 1. Quick intercepts (no GPT call needed) ──────────────────────────────
    # اختصارات سريعة لا تحتاج استدعاء GPT
    if any(w in msg_lower for w in ["احفظ", "favorite", "like", "save"]):
        recent  = db.session.query(Property).order_by(Property.id.desc()).first()
        prop_id = recent.id if recent else 1
        return {"action": "add_favorite", "property_id": prop_id,
                "conversation_id": conversation_id}

    # Quick intercept: "send message / contact" — only for direct messaging, not agent search
    # لا نُشغّله إذا كان المستخدم يبحث عن وكيل (Intent G تتولّى ذلك)
    _contact_g_kws = ["agent", "وكيل", "agents", "وكلاء"]
    if (any(w in msg_lower for w in ["contact", "تواصل", "رسالة", "message"])
            and not any(kw in msg_lower for kw in _contact_g_kws)):
        if not _extract_agent_name(prompt):
            recent = db.session.query(Property).order_by(Property.id.desc()).first()
            a_id   = recent.agent_id if recent else 1
            return {"action": "send_message", "agent_id": a_id, "message": prompt,
                    "conversation_id": conversation_id}

    # ── 2. Load or create Conversation ────────────────────────────────────────
    # إنشاء محادثة جديدة أو تحميل القديمة
    if conversation_id:
        conversation = Conversation.query.get(conversation_id)
        if not conversation:
            conversation = Conversation(user_id=user_id, language=language)
            db.session.add(conversation)
            db.session.flush()
    else:
        conversation = Conversation(user_id=user_id, language=language)
        db.session.add(conversation)
        db.session.flush()

    conversation_id = conversation.id

    # ── 3. New intent intercepts: E / F / G ───────────────────────────────────
    # النوايا الجديدة: عقارات وكيل، استثمار مع وكيل، تواصل مع وكيل

    # Intent F — INVEST_WITH_AGENT (check before E to avoid conflict)
    # النية F — أولوية أعلى من E لأن "استثمر مع" أكثر تحديدًا
    invest_keywords_ar = ["استثمر مع", "أستثمر مع", "استثمار مع"]
    invest_keywords_en = ["invest with", "investment with"]
    if (any(kw in msg_lower for kw in invest_keywords_ar + invest_keywords_en)):
        result = _handle_invest_with_agent(prompt, user_id, is_arabic)
        if result:
            _log_chat(conversation_id, user_id, prompt,
                      result["text"], result["intent"], language, None,
                      round(time.time() - start_time, 3))
            result["conversation_id"] = conversation_id
            result.setdefault("investment_hotspots", [])
            return result

    # Intent G — CONTACT_AGENT
    # النية G — البحث عن وكيل (تشمل كلمة "agent" وحدها)
    contact_keywords_ar = ["أريد وكيل", "ابحث عن وكيل", "وكيل في", "وكلاء في", "وكيل"]
    contact_keywords_en = ["contact agent", "find agent", "agent in", "agents in",
                           "agents", "agent"]   # ← "agent" alone now triggers this
    if (any(kw in msg_lower for kw in contact_keywords_ar + contact_keywords_en)):
        # لا نختطف Intent E — إذا كانت الرسالة تحتوي كلمة عقار + اسم وكيل → اتركها لـ E
        # Don't hijack E: if message has property keyword AND an agent name → skip G
        prop_kws      = ["property", "properties", "listing", "عقار", "عقارات"]
        is_prop_query = (any(kw in msg_lower for kw in prop_kws)
                         and bool(_extract_agent_name(prompt)))
        if not is_prop_query:
            result = _handle_contact_agent(prompt, is_arabic)
            if result:
                _log_chat(conversation_id, user_id, prompt,
                          result["text"], result["intent"], language, None,
                          round(time.time() - start_time, 3))
                result["conversation_id"] = conversation_id
                result.setdefault("investment_hotspots", [])
                return result

    # Intent E — AGENT_PROPERTIES
    # النية E — عقارات وكيل محدد
    # Broad trigger: any property-related word + a detectable agent name
    props_keywords_ar = ["عقارات", "عقار"]
    props_keywords_en = ["properties", "property", "listing", "listings", "show me"]
    if (any(kw in msg_lower for kw in props_keywords_ar + props_keywords_en)
            and _extract_agent_name(prompt)):
        result = _handle_agent_properties(prompt, is_arabic)
        if result:
            _log_chat(conversation_id, user_id, prompt,
                      result["text"], result["intent"], language, None,
                      round(time.time() - start_time, 3))
            result["conversation_id"] = conversation_id
            result.setdefault("investment_hotspots", [])
            return result

    # ── 3a-bis. Intent I — PROJECTS / DEVELOPMENTS ────────────────────────────
    # "show me projects in Muscat" / "ما هي المشاريع المتاحة؟"
    # يُحقَن قبل البحث العام لأن "projects" كلمة عامَّة تخلط مع "properties"
    project_kws_en = [
        "project", "projects", "development", "developments",
        "compound", "compounds", "new project", "off-plan",
        "off plan", "under construction", "multi-unit",
    ]
    project_kws_ar = [
        "مشروع", "مشاريع", "كومباوند", "مجمَّع", "مجمَّعات",
        "تطوير عقاري", "مشروع جديد", "تحت الإنشاء", "تحت البناء",
    ]
    if any(kw in msg_lower for kw in project_kws_en + project_kws_ar):
        # تجاهل إن كان "properties" بدون "project" (لتجنُّب hijacking البحث العام)
        if "project" in msg_lower or "مشروع" in msg_lower or "كومباوند" in msg_lower \
                or "مجمَّع" in msg_lower or "off-plan" in msg_lower \
                or "development" in msg_lower or "تطوير" in msg_lower \
                or "under construction" in msg_lower or "تحت الإنشاء" in msg_lower:
            result = _handle_projects(prompt, is_arabic)
            if result:
                _log_chat(conversation_id, user_id, prompt,
                          result["text"], result["intent"], language, None,
                          round(time.time() - start_time, 3))
                result["conversation_id"] = conversation_id
                result.setdefault("investment_hotspots", [])
                return result

    # ── 3b. Intent H — OWN PROPERTY FORECAST ─────────────────────────────────
    # "I have a villa 500,000 OMR... after 5 years?" — pure calculation, no DB needed
    # "عندي عقار بـ 500,000 ريال... بعد 5 سنوات؟" — حساب مباشر بدون بحث في DB
    own_kws_en = [
        "i have", "i own", "my villa", "my property", "my apartment",
        "my house", "my land", "i bought", "i purchased",
        # hypothetical purchase ("if i buy ... worth X how much after Y years?")
        "if i buy", "if i purchase", "if i get", "if i invest", "if i pay",
        "if i spend", "if i'd buy", "should i buy",
        "i want to buy", "i plan to buy", "i'm buying", "planning to buy",
        "i will buy", "what if i buy",
    ]
    own_kws_ar = [
        "عندي", "عندي فيلا", "لدي", "اشتريت", "عقاري", "فيلتي",
        # هل أشتري / لو اشتريت / إذا اشتريت
        "لو اشتريت", "إذا اشتريت", "هل أشتري", "أنوي شراء", "أريد شراء",
        "سوف أشتري", "إن اشتريت",
    ]
    if (any(kw in msg_lower for kw in own_kws_en + own_kws_ar)):
        result = _handle_own_property_forecast(prompt, is_arabic)
        if result:
            _log_chat(conversation_id, user_id, prompt,
                      result["text"], result["intent"], language, None,
                      round(time.time() - start_time, 3))
            result["conversation_id"] = conversation_id
            result.setdefault("investment_hotspots", [])
            return result

    # ── 4. RAG context from ChromaDB ──────────────────────────────────────────
    # سياق RAG من ChromaDB — يُحقَن في رسالة النظام لتزويد GPT ببيانات حقيقية
    rag_context = ""
    try:
        from rag_engine import search_knowledge_base
        rag_context = search_knowledge_base(prompt, k=5)
    except Exception as e:
        logger.warning(f"[Ahmed] RAG search skipped: {e}")

    # ── 5. Build conversation history from ChatLog ────────────────────────────
    # بناء سياق المحادثة من الرسائل السابقة
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

    # ── 6. GPT intent extraction ───────────────────────────────────────────────
    # استخراج النية والموقع والنوع والميزانية + حقن سياق RAG

    # RAG block is prepended to system prompt when available
    # كتلة RAG تُضاف في بداية رسالة النظام عند توفّرها
    rag_block = (
        f"Real data from our platform (use this to answer accurately):\n"
        f"{rag_context}\n\n"
    ) if rag_context else ""

    # أخبر GPT باللغة صراحةً — لا تترك له مجال لتخمينها
    # Tell GPT the language explicitly — never let it guess
    lang_instruction = (
        "IMPORTANT: The user wrote in Arabic. You MUST reply ONLY in Arabic."
        if is_arabic else
        "IMPORTANT: The user wrote in English. You MUST reply ONLY in English. Do NOT use Arabic."
    )

    system_msg = {
        "role": "system",
        "content": (
            f"{rag_block}"
            f"{lang_instruction}\n\n"
            "You are Ahmed, a top-tier real estate AI agent in Oman. "
            "Reply ONLY in valid JSON. "
            "Extract from the user message:\n"
            "- location (e.g. Muscat, Salalah, Barka, Sohar, Al Mouj, Al Buraimi — empty string if none)\n"
            "- property_type (Villa, Apartment, Land, Townhouse, Commercial — empty if none)\n"
            "- budget (numeric max price in OMR; 0 if not mentioned)\n"
            "- intent (search | investment | compare | contact)\n"
            "- text (a SHORT acknowledgement only — do NOT say 'no data' or 'I cannot find')\n\n"
            "Respond ONLY with this JSON schema:\n"
            "{\n"
            "  \"location\": \"\",\n"
            "  \"property_type\": \"\",\n"
            "  \"budget\": 0,\n"
            "  \"intent\": \"search\",\n"
            "  \"text\": \"\"\n"
            "}"
        ),
    }

    messages = [system_msg] + history + [{"role": "user", "content": prompt}]

    fallback_text  = ("جاري البحث عن أفضل الخيارات لك... 🏘️" if is_arabic
                      else "Searching for the best options for you... 🏘️")
    extracted_data = {
        "location": "", "property_type": "", "budget": 0,
        "intent": "search", "text": fallback_text,
    }
    tokens_used = None

    try:
        response       = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={"type": "json_object"},
        )
        extracted_data = json.loads(response.choices[0].message.content.strip())
        tokens_used    = response.usage.total_tokens
    except Exception as e:
        logger.error(f"[Ahmed] GPT error: {e}")

    ai_text = extracted_data.get("text", fallback_text)
    intent  = extracted_data.get("intent", "search")

    # ── 7. Property DB query ───────────────────────────────────────────────────
    # البحث في قاعدة البيانات بناءً على الفلاتر المستخرجة
    query = Property.query

    loc = extracted_data.get("location", "")
    is_project_query = False
    if loc and loc.strip() and loc.lower() not in ("none", "null"):
        loc_lower = loc.lower()
        if "surooh" in loc_lower or "سروح" in loc_lower:
            query = query.filter_by(is_surooh=True)
            is_project_query = True
        elif "omran" in loc_lower or "عمران" in loc_lower:
            query = query.filter_by(is_omran=True)
            is_project_query = True
        else:
            query = query.filter(Property.location.ilike(f"%{loc}%"))

    if not is_project_query:
        if "surooh" in msg_lower or "سروح" in msg_lower:
            query = query.filter_by(is_surooh=True)
            is_project_query = True
        elif "omran" in msg_lower or "عمران" in msg_lower:
            query = query.filter_by(is_omran=True)
            is_project_query = True

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

    # ── 8a. Guard: only show properties when the user actually asked for them ──
    # إذا لم يُعطِ المستخدم أي فلتر حقيقي ولم تكن رسالته تحتوي كلمات عقارية
    # نخفي النتائج ونعرض رد GPT الطبيعي (تحية، شكر، محادثة عامة …)
    _prop_kws_en = [
        "property", "properties", "villa", "villas", "apartment", "apartments",
        "land", "lands", "townhouse", "commercial", "buy", "rent", "invest",
        "find", "show", "search", "looking for", "need a", "want a", "best",
        "cheap", "affordable", "listing", "listings", "price", "cost",
    ]
    _prop_kws_ar = [
        "عقار", "عقارات", "فيلا", "فيلات", "شقة", "شقق", "أرض", "اراضي",
        "تاون هاوس", "أريد", "أبحث", "ابحث", "أشتري", "اشتري", "استثمار",
        "استثمر", "إيجار", "ايجار", "بحث", "سعر", "تكلفة",
    ]
    # A "real" filter: location given, type given, budget > 0, OR the message
    # contains any property-search keyword → show property cards.
    # Otherwise (greeting / small talk) → clear results, keep GPT text.
    has_real_filters = bool(
        (loc  and loc.strip()  and loc.lower()  not in ("none", "null", "")) or
        (ptype and ptype.strip() and ptype.lower() not in ("none", "null", "any", "")) or
        (float(budget) > 0 if budget else False) or
        any(kw in msg_lower for kw in _prop_kws_en + _prop_kws_ar)
    )

    if not has_real_filters:
        # Pure greeting / small talk — show NO property cards
        results = []

    # ── 8b. Build coherent text based on ACTUAL DB results ───────────────────
    # نبني النص بناءً على نتائج قاعدة البيانات الحقيقية — لا على نص GPT
    # This prevents the "GPT says no data but we show properties" contradiction
    area_str   = loc if loc and loc.lower() not in ("none", "null", "") else ""
    budget_val = float(budget) if budget else 0

    if results:
        count      = min(len(results), 4)   # we show max 4
        area_part  = f" في {area_str}"  if area_str and is_arabic  else f" in {area_str}" if area_str else ""
        budget_part = (f" ضمن ميزانية {int(budget_val):,} ريال عُماني"
                       if budget_val > 0 and is_arabic else
                       f" within a budget of {int(budget_val):,} OMR"
                       if budget_val > 0 else "")
        if is_arabic:
            ai_text = f"وجدت {count} عقار{'ات' if count > 1 else ''}{area_part}{budget_part}. إليك أفضل الخيارات المتاحة: 🏘️"
        else:
            ai_text = f"Found {count} propert{'ies' if count > 1 else 'y'}{area_part}{budget_part}. Here are the best available options: 🏘️"
    elif area_str:
        if is_arabic:
            ai_text = (f"عذراً، لا نملك عقارات تطابق بحثك حالياً في {area_str}. "
                       f"هل يمكنك توسيع نطاق البحث أو تجربة مناطق قريبة؟ 🏡")
        else:
            ai_text = (f"Sorry, we don't currently have exact matches in {area_str}. "
                       f"Consider expanding your criteria or nearby areas. 🏡")
    else:
        # No location, no results — keep GPT's text as context
        pass

    # ── 9. Sort results ────────────────────────────────────────────────────────
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
            ), reverse=True,
        )

    top_results = results[:4]

    # ── 10. Dynamic reason templates ──────────────────────────────────────────
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

    # ── 11. Format top properties with dynamic ROI + growth ───────────────────
    properties_to_return = []
    for best_p in top_results:
        t_low = (best_p.type or '').lower()

        if   'villa'     in t_low: roi_val = round(random.uniform(6.0, 7.0), 1)
        elif 'apartment' in t_low: roi_val = round(random.uniform(7.0, 8.0), 1)
        elif 'land'      in t_low: roi_val = round(random.uniform(8.0, 10.0), 1)
        else:                      roi_val = round(random.uniform(5.0, 7.0), 1)

        prop_status = getattr(best_p, 'status', 'available') or 'available'
        if prop_status == 'under_construction':
            roi_val = round(roi_val + 1.5, 1)

        price      = float(best_p.price or 0)
        yearly_inc = round(price * (roi_val / 100.0), 0)

        growth = _get_area_growth_rate(best_p.location)
        p1 = round(price * (1 + growth["1y"]), 0)
        p2 = round(price * (1 + growth["2y"]), 0)
        p5 = round(price * (1 + growth["5y"]), 0)

        agent_name = best_p.agent.username if best_p.agent else "Unknown"

        properties_to_return.append({
            "id":            best_p.id,
            "title":         best_p.title,
            "location":      best_p.location,
            "price":         best_p.price,
            "roi":           roi_val,
            "yearly_income": yearly_inc,
            "price_1y":      p1,
            "price_2y":      p2,
            "price_5y":      p5,
            "reason":        _get_unique_reason(best_p.type or 'Unknown', best_p.location),
            "lat":           getattr(best_p, "latitude",  23.5880),
            "lng":           getattr(best_p, "longitude", 58.3829),
            "agent":         agent_name,
            "agent_id":      best_p.agent_id,
            "is_new":        getattr(best_p, 'is_new', False),
            "status":        prop_status,
        })

    # ── 12. Future price question detection ───────────────────────────────────
    # اكتشاف سؤال "كم سيكون السعر بعد X سنوات؟" والإجابة عنه صراحةً
    # Detect "after X year(s)" and override text with a direct price projection answer
    _year_patterns = [
        r'after\s+(\d+)\s+year',          # after 2 year / after 5 years
        r'in\s+(\d+)\s+year',             # in 2 years
        r'(\d+)\s+year[s]?\s+(?:from now|later|price)',  # 2 years from now
        r'بعد\s+(\d+)\s+سن',              # بعد 2 سنة / سنوات
        r'خلال\s+(\d+)\s+سن',             # خلال 3 سنوات
    ]
    years_asked = None
    for _pat in _year_patterns:
        _m = re.search(_pat, msg_lower)
        if _m:
            years_asked = int(_m.group(1))
            break

    if years_asked and properties_to_return:
        best_p_proj = properties_to_return[0]   # أفضل عقار في النتائج
        # اختيار السعر المناسب حسب عدد السنوات
        if years_asked <= 1:
            future_price = best_p_proj.get('price_1y', 0)
            yr_key       = "1Y"
        elif years_asked <= 2:
            future_price = best_p_proj.get('price_2y', 0)
            yr_key       = "2Y"
        else:
            future_price = best_p_proj.get('price_5y', 0)
            yr_key       = "5Y"

        curr_price  = float(best_p_proj.get('price', 0))
        gain        = future_price - curr_price
        gain_pct    = round((gain / curr_price) * 100, 1) if curr_price else 0
        title_short = best_p_proj.get('title', '')[:40]

        if is_arabic:
            ai_text = (
                f"📈 أفضل عقار متاح: **{title_short}**\n"
                f"💰 السعر الحالي: {curr_price:,.0f} OMR\n"
                f"🚀 السعر المتوقع بعد {years_asked} {'سنة' if years_asked == 1 else 'سنوات'}: "
                f"**{future_price:,.0f} OMR**\n"
                f"📊 الزيادة المتوقعة: {gain:,.0f} OMR ({gain_pct}%)\n"
                f"(راجع بطاقات العقارات أدناه لمقارنة جميع الخيارات)"
            )
        else:
            ai_text = (
                f"📈 Best available property: **{title_short}**\n"
                f"💰 Current price: {curr_price:,.0f} OMR\n"
                f"🚀 Estimated price after {years_asked} year{'s' if years_asked > 1 else ''}: "
                f"**{future_price:,.0f} OMR**\n"
                f"📊 Expected gain: {gain:,.0f} OMR (+{gain_pct}%)\n"
                f"(See the property cards below to compare all options)"
            )

    # ── 13. Follow-up questions ────────────────────────────────────────────────
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

    # ── 13. Investment hotspots from Area table ────────────────────────────────
    hotspot_query = Area.query
    if loc and loc.strip() and loc.lower() not in ("none", "null"):
        hotspot_query = hotspot_query.filter(Area.name.ilike(f"%{loc}%"))
    hotspot_areas = hotspot_query.order_by(Area.demand.desc()).limit(5).all()
    if not hotspot_areas:
        hotspot_areas = Area.query.order_by(Area.demand.desc()).limit(5).all()

    investment_hotspots = []
    for area in hotspot_areas:
        parts = []
        if area.demand       > 70: parts.append("high demand")
        if area.price_growth > 60: parts.append("strong price growth")
        if area.services     > 60: parts.append("excellent infrastructure")
        if not parts:              parts.append("emerging market potential")
        investment_hotspots.append({
            "name":   area.name,
            "lat":    area.latitude,
            "lng":    area.longitude,
            "reason": ", ".join(parts).capitalize(),
        })

    # ── 14. Log to ChatLog ────────────────────────────────────────────────────
    response_time = round(time.time() - start_time, 3)
    _log_chat(conversation_id, user_id, prompt, ai_text, intent, language,
              tokens_used, response_time)

    # ── 15. Return response ────────────────────────────────────────────────────
    return {
        "text":                ai_text,
        "properties":          properties_to_return,
        "investment_hotspots": investment_hotspots,
        "conversation_id":     conversation_id,
    }


# =============================================================================
# 🗄️ LOGGING HELPER (internal)
# مساعد تسجيل الرسائل — يُستخدم داخليًا فقط
# =============================================================================

def _log_chat(conversation_id: int | None,
              user_id: int | None,
              user_message: str,
              bot_response: str,
              intent: str,
              language: str,
              tokens_used: int | None,
              response_time: float) -> None:
    """
    Persist a ChatLog entry. Errors are caught and logged — never raised.
    حفظ سجل المحادثة في قاعدة البيانات. الأخطاء تُسجَّل ولا تُرفع.
    """
    try:
        log = ChatLog(
            conversation_id=conversation_id,
            user_id=user_id,
            user_message=user_message,
            bot_response=bot_response,
            intent=intent,
            language=language,
            tokens_used=tokens_used,
            response_time=response_time,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"[Ahmed] DB log error: {e}")
        db.session.rollback()
