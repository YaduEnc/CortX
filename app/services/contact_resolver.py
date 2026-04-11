from __future__ import annotations

from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.action import Contact


def _normalized_tokens(value: str) -> list[str]:
    return [token.strip().lower() for token in value.replace(",", " ").split() if token.strip()]


def _candidate_aliases(recipient_name: str) -> list[str]:
    raw = recipient_name.strip().lower()
    if not raw:
        return []
    tokens = _normalized_tokens(raw)
    aliases = {raw, *tokens}
    if len(tokens) > 1:
        aliases.add(tokens[0])
        aliases.add(" ".join(tokens[:2]))
    return [alias for alias in aliases if alias]


async def resolve_contact(
    user_id: str,
    recipient_name: str,
    db: Session,
) -> tuple[Contact | None, bool]:
    raw_name = recipient_name.strip()
    if not raw_name:
        return None, False

    lowered = raw_name.lower()
    exact = db.scalar(
        select(Contact).where(
            Contact.user_id == user_id,
            or_(
                Contact.name.ilike(raw_name),
                Contact.name_aliases.any(lowered),
            ),
        )
    )
    if exact:
        return exact, True

    aliases = _candidate_aliases(raw_name)
    if not aliases:
        return None, False

    for alias in aliases:
        alias_match = db.scalar(
            select(Contact).where(
                Contact.user_id == user_id,
                Contact.name_aliases.any(alias),
            )
        )
        if alias_match:
            return alias_match, True

    contacts = db.scalars(select(Contact).where(Contact.user_id == user_id)).all()
    alias_set = set(aliases)
    best_contact: Contact | None = None
    best_score = 0

    for contact in contacts:
        contact_tokens = set(_normalized_tokens(contact.name))
        contact_tokens.update(token.lower() for token in (contact.name_aliases or []))
        score = len(alias_set.intersection(contact_tokens))
        if score > best_score:
            best_score = score
            best_contact = contact

    if best_contact and best_score > 0:
        return best_contact, True

    return None, False
