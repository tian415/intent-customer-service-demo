import re
import unicodedata
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.repository import faq_data
from app.models import FAQ


def normalize(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).lower().split())


def keyword_match(word: str, text: str) -> bool:
    if re.fullmatch(r'[a-z0-9 ]+', word):
        return re.search(r'(?<![a-z0-9])' + re.escape(word) + r'(?![a-z0-9])', text) is not None
    return word in text


def search_faq(db: Session, query: str) -> dict:
    text = normalize(query)
    candidates = []
    for item in db.scalars(select(FAQ).where(FAQ.active.is_(True)).order_by(FAQ.id)):
        keywords = [normalize(k) for k in re.split(r'[,，\n]', item.keywords) if k.strip()]
        hits = sum(keyword_match(k, text) for k in set(keywords))
        score = 1.0 if text == normalize(item.question) else min(0.9, 0.6 + 0.1 * hits) if hits else 0.0
        if score:
            candidates.append({**faq_data(item), 'score': round(score, 3)})
    candidates.sort(key=lambda item: (-item['score'], item['id']))
    reliable = bool(candidates) and (len(candidates) == 1 or candidates[0]['score'] - candidates[1]['score'] >= 0.15)
    return {'items': candidates[:5], 'reliable': reliable, 'source': 'faq', 'fallback': None if reliable else 'manual_ticket'}
