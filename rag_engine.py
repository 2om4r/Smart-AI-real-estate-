# rag_engine.py — RAG (Retrieval-Augmented Generation) Engine
# محرك الاسترجاع المعزز للمعرفة — يفهرس العقارات والمناطق ويبحث فيها
#
# يستخدم ChromaDB كقاعدة بيانات متجهة و OpenAI text-embedding-3-small للتضمين.
# Uses ChromaDB as a vector store and OpenAI text-embedding-3-small for embeddings.
#
# Public API:
#   build_knowledge_base()            — full rebuild (called on app start)
#   search_knowledge_base(query, k=5) — semantic search, returns context string
#   update_property_in_rag(id)        — incremental upsert after add/edit
#   delete_property_from_rag(id)      — remove after delete

from __future__ import annotations

import os
import logging
from typing import List

import chromadb
from chromadb.config import Settings
from openai import OpenAI

logger = logging.getLogger(__name__)

# =============================================================================
# ⚙️ CONSTANTS
# الثوابت — قابلة للتغيير عبر متغيرات البيئة أو مباشرةً
# =============================================================================

CHROMA_PATH     = os.environ.get("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME = "real_estate_oman"       # اسم المجموعة في ChromaDB
EMBED_MODEL     = "text-embedding-3-small" # نموذج OpenAI للتضمين
BATCH_SIZE      = 100                      # عدد الوثائق في كل دفعة تضمين
DISTANCE_FILTER = 0.8                      # حد المسافة الكوسينية (أقل = أكثر تشابهًا)
                                           # cosine distance threshold; lower = more relevant


# =============================================================================
# 🔌 CLIENTS (module-level singletons)
# عملاء الخدمات — يُنشأ مرة واحدة عند تحميل الوحدة
# =============================================================================

# OpenAI client — المفتاح من متغيرات البيئة فقط
_openai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ChromaDB PersistentClient — يحفظ البيانات على القرص بين إعادات التشغيل
_chroma = chromadb.PersistentClient(
    path=CHROMA_PATH,
    settings=Settings(anonymized_telemetry=False),  # لا نرسل بيانات مجهولة لـ Chroma
)


# =============================================================================
# 🔧 INTERNAL HELPERS
# دوال داخلية مساعدة — لا تُستخدم خارج هذه الوحدة
# =============================================================================

def _get_collection() -> chromadb.Collection:
    """
    Return the ChromaDB collection, creating it if it does not exist.
    إرجاع مجموعة ChromaDB — تُنشأ تلقائيًا إن لم تكن موجودة.

    hnsw:space = cosine  →  الأقرب لـ 0 يعني الأكثر تشابهًا دلاليًا.
    """
    return _chroma.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _embed(texts: List[str]) -> List[List[float]]:
    """
    Embed a batch of texts with OpenAI text-embedding-3-small.
    تضمين دفعة من النصوص باستخدام نموذج OpenAI.

    Returns a list of float vectors, one per input text.
    يُرجع قائمة متجهات، واحد لكل نص مُدخَل.
    """
    response = _openai.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _property_to_text(prop) -> str:
    """
    Serialise a Property ORM instance to a bilingual searchable string.
    تحويل كائن عقار إلى نص قابل للبحث (عربي + إنجليزي).

    الحقول: العنوان، النوع، الموقع، المدينة، السعر، المساحة، الغرف، الوكيل،
            مشروع صروح، مشروع عمران، الحالة.
    """
    agent_name = prop.agent.username if prop.agent else "unknown"
    is_surooh  = "نعم" if prop.is_surooh else "لا"
    is_omran   = "نعم" if prop.is_omran  else "لا"
    bedrooms   = prop.bedrooms or 0
    size       = prop.size     or 0
    price      = prop.price    or 0
    status     = prop.status   or "available"
    city       = prop.city     or prop.location or ""

    return (
        f"عقار: {prop.title} | "
        f"نوع: {prop.type} | "
        f"موقع: {prop.location} | "
        f"مدينة: {city} | "
        f"سعر: {price} OMR | "
        f"مساحة: {size} م² | "
        f"غرف: {bedrooms} | "
        f"وكيل: {agent_name} | "
        f"صروح: {is_surooh} | "
        f"عمران: {is_omran} | "
        f"الحالة: {status}"
    )


def _area_to_text(area) -> str:
    """
    Serialise an Area ORM instance to a searchable string.
    تحويل كائن منطقة إلى نص قابل للبحث.

    الحقول: الاسم، متوسط السعر، الطلب، نمو الأسعار، التوصية، السكور.
    """
    return (
        f"منطقة: {area.name} | "
        f"متوسط السعر: {area.avg_price} OMR | "
        f"الطلب: {area.demand}/100 | "
        f"نمو الأسعار: {area.price_growth}/100 | "
        f"التوصية: {area.recommendation} | "
        f"السكور: {round(area.score, 1)}/100"
    )


# =============================================================================
# 📦 BUILD KNOWLEDGE BASE  —  full rebuild
# بناء قاعدة المعرفة من الصفر — يُستدعى عند بدء التطبيق
# =============================================================================

def build_knowledge_base() -> None:
    """
    Full (re)build: delete the old collection and index every Property + Area.
    إعادة بناء كاملة: حذف المجموعة القديمة ثم فهرسة جميع العقارات والمناطق.

    Must be called inside an active Flask app_context (db queries are made here).
    يجب الاستدعاء داخل app_context نشط لأن الدالة تستعلم من قاعدة البيانات.

    Steps:
      1. Delete existing collection (guarantees freshness on every restart)
      2. Re-create the collection
      3. Build text + metadata for every Property and Area row
      4. Embed + upsert in batches of BATCH_SIZE
      5. Log progress

    الخطوات:
      1. حذف المجموعة الحالية (يضمن حداثة البيانات عند كل إعادة تشغيل)
      2. إنشاء مجموعة جديدة
      3. بناء النصوص والبيانات الوصفية لكل عقار ومنطقة
      4. التضمين والإدراج على دفعات
      5. تسجيل التقدم
    """
    # Lazy import to avoid circular import at module level
    # استيراد متأخر لتجنب الاستيراد الدائري
    from models import Property, Area

    logger.info("[RAG] Starting full knowledge-base rebuild...")

    # ── 1. Drop old collection for a clean slate ──────────────────────────────
    # حذف المجموعة القديمة — يُتجاهَل الخطأ إن لم تكن موجودة (أول تشغيل)
    try:
        _chroma.delete_collection(COLLECTION_NAME)
        logger.info("[RAG] Old collection deleted.")
    except Exception:
        pass  # does not exist on first run — that's fine

    # ── 2. Create fresh collection ────────────────────────────────────────────
    collection = _get_collection()

    # ── 3. Collect documents ──────────────────────────────────────────────────
    # جمع النصوص والمعرّفات والبيانات الوصفية
    docs:      List[str]  = []
    doc_ids:   List[str]  = []
    metadatas: List[dict] = []

    # --- Properties -----------------------------------------------------------
    properties = Property.query.all()
    for prop in properties:
        try:
            docs.append(_property_to_text(prop))
            doc_ids.append(f"prop_{prop.id}")
            metadatas.append({"type": "property", "id": prop.id})
        except Exception as e:
            logger.warning(f"[RAG] Skipping property id={prop.id}: {e}")

    # --- Areas ----------------------------------------------------------------
    areas = Area.query.all()
    for area in areas:
        try:
            docs.append(_area_to_text(area))
            doc_ids.append(f"area_{area.id}")
            metadatas.append({"type": "area", "id": area.id})
        except Exception as e:
            logger.warning(f"[RAG] Skipping area id={area.id}: {e}")

    if not docs:
        logger.warning("[RAG] No documents found. Knowledge base is empty.")
        return

    total   = len(docs)
    indexed = 0

    # ── 4. Embed + upsert in batches ──────────────────────────────────────────
    # التضمين والإدراج على دفعات لتجنب تجاوز حدود OpenAI API وضمان الأداء
    for i in range(0, total, BATCH_SIZE):
        batch_docs  = docs[i : i + BATCH_SIZE]
        batch_ids   = doc_ids[i : i + BATCH_SIZE]
        batch_meta  = metadatas[i : i + BATCH_SIZE]

        try:
            embeddings = _embed(batch_docs)
            collection.upsert(
                documents  = batch_docs,
                ids        = batch_ids,
                metadatas  = batch_meta,
                embeddings = embeddings,
            )
            indexed += len(batch_docs)
            logger.info(f"[RAG] Progress: {indexed}/{total} documents indexed.")
        except Exception as e:
            logger.error(
                f"[RAG] Batch {i}–{i + BATCH_SIZE} failed: {e} — skipping batch."
            )

    logger.info(f"[RAG] Knowledge base ready. {indexed}/{total} documents indexed.")


# =============================================================================
# 🔍 SEARCH KNOWLEDGE BASE
# البحث الدلالي — يُستدعى من get_ai_response() في ai_utils.py
# =============================================================================

def search_knowledge_base(query: str, k: int = 5) -> str:
    """
    Semantic search: embed the query, fetch top-k results, filter by distance.
    بحث دلالي: تضمين الاستعلام، جلب أفضل k نتيجة، تصفية حسب المسافة.

    Args:
        query: User's natural-language question (Arabic or English).
               سؤال المستخدم بالعربية أو الإنجليزية.
        k:     Max number of results to fetch before distance filtering (default 5).
               الحد الأقصى للنتائج قبل التصفية.

    Returns:
        A single newline-joined string of relevant documents ready for GPT injection.
        Returns "" on error or when no relevant results pass the distance threshold.

        نص واحد يجمع الوثائق ذات الصلة — جاهز للحقن في رسالة النظام لـ GPT.
        يُرجع "" عند الخطأ أو عدم وجود نتائج ذات صلة كافية.
    """
    if not query or not query.strip():
        return ""

    try:
        collection = _get_collection()

        # تضمين الاستعلام — يستخدم نفس النموذج المُستخدَم عند الفهرسة
        query_embedding = _embed([query])[0]

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=["documents", "distances"],
        )

        documents: List[str]  = results.get("documents", [[]])[0]
        distances: List[float] = results.get("distances",  [[]])[0]

        # تصفية النتائج التي تتجاوز حد المسافة (بعيدة عن الاستعلام = غير ذات صلة)
        # Keep only results whose cosine distance is below DISTANCE_FILTER
        filtered = [
            doc
            for doc, dist in zip(documents, distances)
            if dist < DISTANCE_FILTER
        ]

        if not filtered:
            logger.debug(f"[RAG] No results passed distance filter for query: {query[:60]}")
            return ""

        return "\n".join(filtered)

    except Exception as e:
        logger.error(f"[RAG] search_knowledge_base failed: {e}")
        return ""  # graceful degradation — GPT still runs without RAG context


# =============================================================================
# 🔄 UPDATE — single property (after add or edit)
# تحديث عقار واحد بعد إضافته أو تعديله
# =============================================================================

def update_property_in_rag(property_id: int) -> None:
    """
    Upsert (insert or overwrite) a single property document in ChromaDB.
    إدراج أو تحديث وثيقة عقار واحد في ChromaDB.

    Call this after:
      - A new property is added   (add_property route)
      - An existing property is edited (edit_property route)

    استدعِها بعد:
      - إضافة عقار جديد
      - تعديل عقار موجود
    """
    from models import Property  # lazy import

    doc_id = f"prop_{property_id}"

    try:
        prop = Property.query.get(property_id)
        if not prop:
            logger.warning(f"[RAG] update_property_in_rag: property {property_id} not found.")
            return

        text      = _property_to_text(prop)
        embedding = _embed([text])[0]

        # upsert — يُحدَّث إن وُجد، يُنشأ إن لم يُوجد
        _get_collection().upsert(
            documents  = [text],
            ids        = [doc_id],
            metadatas  = [{"type": "property", "id": property_id}],
            embeddings = [embedding],
        )
        logger.info(f"[RAG] Property {property_id} updated in knowledge base.")

    except Exception as e:
        logger.error(f"[RAG] update_property_in_rag({property_id}) failed: {e}")


# =============================================================================
# 🗑️ DELETE — single property (after delete)
# حذف عقار واحد من قاعدة المعرفة بعد حذفه من قاعدة البيانات
# =============================================================================

def delete_property_from_rag(property_id: int) -> None:
    """
    Remove a single property document from ChromaDB by its doc_id.
    إزالة وثيقة عقار واحد من ChromaDB باستخدام معرّفه.

    Call this after a property is deleted from the DB.
    استدعِها بعد حذف العقار من قاعدة البيانات.

    Errors are caught and logged — the DB delete should not be blocked
    by a RAG failure.
    الأخطاء تُسجَّل فقط ولا تمنع حذف العقار من قاعدة البيانات.
    """
    doc_id = f"prop_{property_id}"

    try:
        _get_collection().delete(ids=[doc_id])
        logger.info(f"[RAG] Property {property_id} removed from knowledge base.")
    except Exception as e:
        logger.error(f"[RAG] delete_property_from_rag({property_id}) failed: {e}")
