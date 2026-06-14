
from __future__ import annotations

import os
import logging
from typing import List

import chromadb
from chromadb.config import Settings
from openai import OpenAI

logger = logging.getLogger(__name__)

CHROMA_PATH     = os.environ.get("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME = "real_estate_oman"       
EMBED_MODEL     = "text-embedding-3-small" 
BATCH_SIZE      = 100                      
DISTANCE_FILTER = 0.8                      
                                           
_openai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

_chroma = chromadb.PersistentClient(
    path=CHROMA_PATH,
    settings=Settings(anonymized_telemetry=False),  
)

def _get_collection() -> chromadb.Collection:
    
    return _chroma.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

def _embed(texts: List[str]) -> List[List[float]]:
    
    response = _openai.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]

def _property_to_text(prop) -> str:
    
    agent_name = prop.agent.username if prop.agent else "unknown"
    is_surooh  = "نعم" if prop.is_surooh else "لا"
    is_omran   = "نعم" if prop.is_omran  else "لا"
    bedrooms   = prop.bedrooms or 0
    size       = prop.size     or 0
    price      = prop.price    or 0
    status     = prop.status   or "available"
    city       = prop.city     or prop.location or ""

    if getattr(prop, 'is_project', False):
        developer       = prop.developer or "غير محدَّد"
        completion      = prop.completion_date or "TBD"
        total_units     = prop.total_units or 0
        try:
            units_now = prop.units.count()
        except Exception:
            units_now = 0

        return (
            f"مشروع عقاري: {prop.title} | "
            f"PROJECT: {prop.title} | "
            f"المطوِّر: {developer} | DEVELOPER: {developer} | "
            f"موقع: {prop.location} | LOCATION: {prop.location} | "
            f"مدينة: {city} | CITY: {city} | "
            f"سعر البداية: {price} OMR | STARTING PRICE: {price} OMR | "
            f"إجمالي الوحدات المخطَّطة: {total_units} | TOTAL UNITS PLANNED: {total_units} | "
            f"الوحدات المتوفِّرة الآن: {units_now} | UNITS AVAILABLE: {units_now} | "
            f"تاريخ التسليم: {completion} | COMPLETION: {completion} | "
            f"الحالة: {status} | STATUS: {status} | "
            f"الوكيل: {agent_name} | AGENT: {agent_name} | "
            f"نوع: مشروع متعدِّد الوحدات | TYPE: multi-unit development | "
            f"الوصف: {(prop.description or '')[:300]}"
        )

    parent_label = ""
    try:
        if prop.parent_project_id and prop.parent_project:
            parent_label = (
                f" | ضمن مشروع: {prop.parent_project.title}"
                f" | PART OF PROJECT: {prop.parent_project.title}"
            )
    except Exception:
        pass

    surooh_tag = "المطور: شركة صروح العقارية Surooh Real Estate | " if prop.is_surooh else ""
    omran_tag  = "المطور: مجموعة عمران OMRAN Group | " if prop.is_omran else ""

    return (
        f"عقار: {prop.title} | "
        f"نوع: {prop.type} | "
        f"موقع: {prop.location} | "
        f"مدينة: {city} | "
        f"سعر: {price} OMR | "
        f"مساحة: {size} م² | "
        f"غرف: {bedrooms} | "
        f"وكيل: {agent_name} | "
        f"{surooh_tag}"
        f"{omran_tag}"
        f"الحالة: {status}"
        f"{parent_label}"
    )

def _area_to_text(area) -> str:
    
    return (
        f"منطقة: {area.name} | "
        f"متوسط السعر: {area.avg_price} OMR | "
        f"الطلب: {area.demand}/100 | "
        f"نمو الأسعار: {area.price_growth}/100 | "
        f"التوصية: {area.recommendation} | "
        f"السكور: {round(area.score, 1)}/100"
    )

def build_knowledge_base(force: bool = False) -> None:
    
    from models import Property, Area

    collection = _get_collection()
    
    if not force:
        try:
            count = collection.count()
            if count > 0:
                logger.info(f"[RAG] Knowledge base already has {count} documents. Skipping rebuild.")
                return
        except Exception:
            pass

    logger.info("[RAG] Starting full knowledge-base rebuild...")

    try:
        _chroma.delete_collection(COLLECTION_NAME)
        logger.info("[RAG] Old collection deleted.")
        collection = _get_collection()
    except Exception:
        pass

    docs:      List[str]  = []
    doc_ids:   List[str]  = []
    metadatas: List[dict] = []

    properties = Property.query.all()
    for prop in properties:
        try:
            docs.append(_property_to_text(prop))
            doc_ids.append(f"prop_{prop.id}")
            metadatas.append({"type": "property", "id": prop.id})
        except Exception as e:
            logger.warning(f"[RAG] Skipping property id={prop.id}: {e}")

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

def search_knowledge_base(query: str, k: int = 15) -> str:
    
    if not query or not query.strip():
        return ""

    if "صروح" in query:
        query += " Surooh Real Estate"
    if "عمران" in query:
        query += " OMRAN Group"

    try:
        collection = _get_collection()

        query_embedding = _embed([query])[0]

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=["documents", "distances"],
        )

        documents: List[str]  = results.get("documents", [[]])[0]
        distances: List[float] = results.get("distances",  [[]])[0]

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
        return ""  

def update_property_in_rag(property_id: int) -> None:
    
    from models import Property  

    doc_id = f"prop_{property_id}"

    try:
        prop = Property.query.get(property_id)
        if not prop:
            logger.warning(f"[RAG] update_property_in_rag: property {property_id} not found.")
            return

        text      = _property_to_text(prop)
        embedding = _embed([text])[0]

        _get_collection().upsert(
            documents  = [text],
            ids        = [doc_id],
            metadatas  = [{"type": "property", "id": property_id}],
            embeddings = [embedding],
        )
        logger.info(f"[RAG] Property {property_id} updated in knowledge base.")

    except Exception as e:
        logger.error(f"[RAG] update_property_in_rag({property_id}) failed: {e}")

def delete_property_from_rag(property_id: int) -> None:
    
    doc_id = f"prop_{property_id}"

    try:
        _get_collection().delete(ids=[doc_id])
        logger.info(f"[RAG] Property {property_id} removed from knowledge base.")
    except Exception as e:
        logger.error(f"[RAG] delete_property_from_rag({property_id}) failed: {e}")
