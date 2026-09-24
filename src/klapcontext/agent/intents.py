"""Deterministic Spanish/English intent and area detection for planning."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentMatch:
    intent: str
    confidence: float
    area: str


RULES = (
    ("DEBUG", ("error", "falla", "fallo", "bug", "exception", "500", "debug")),
    ("IMPACT", ("impacto", "qué rompe", "que rompe", "qué usa", "que usa", "afecta", "impact")),
    ("REFACTOR", ("refactor", "limpiar", "separar", "reestructurar")),
    ("TEST", ("test", "prueba", "coverage", "cobertura")),
    ("CHANGE", ("modificar", "cambiar", "agregar", "implementar", "añadir", "fix", "update", "edit")),
    ("UNDERSTAND", ("qué hace", "que hace", "entender", "explicar", "comprender", "how does", "what does")),
)
AREAS = (
    ("authentication", ("auth", "autentic", "login", "logout", "jwt", "oauth", "sanctum", "passport", "password")),
    ("orders", ("order", "pedido", "orden")),
    ("files", ("archivo", "file", "upload", "sftp", "ftp", "storage")),
    ("payments", ("payment", "pago", "checkout", "stripe")),
    ("notifications", ("notification", "notific", "mail", "email", "sms")),
)


def detect(query: str) -> IntentMatch:
    text = query.casefold()
    intent, confidence = "UNDERSTAND", .45
    for candidate, words in RULES:
        if any(word in text for word in words):
            intent, confidence = candidate, .9
            break
    area = next((name for name, words in AREAS if any(word in text for word in words)), "unknown")
    return IntentMatch(intent, confidence, area)
