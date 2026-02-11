def normalize_text(s: str) -> str:
    return (s or "").strip().replace("\u3000", " ").replace("\n", " ")
