from rapidfuzz import fuzz

def too_similar(a: str, b: str, threshold: int = 92) -> bool:
    return fuzz.token_sort_ratio(a, b) >= threshold

def drop_too_similar_sentences(generated: str, banlist: list[str], threshold: int = 92) -> str:
    out_lines = []
    for sent in generated.split(". "):
        if any(too_similar(sent, x, threshold=threshold) for x in banlist):
            continue
        out_lines.append(sent)
    return ". ".join(out_lines)