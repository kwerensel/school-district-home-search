from __future__ import annotations


SUFFIXES = (
    " Central School District",
    " Union Free School District",
    " City School District",
    " School District",
    " SD",
)


def normalize_district_name(name: str) -> str:
    cleaned = " ".join(name.replace("\u2013", "-").split())
    if cleaned == "Union Free School District of the Tarrytowns":
        return "Tarrytowns"
    for phrase in SUFFIXES[:-1]:
        cleaned = cleaned.replace(f"{phrase} (", " (")
    for suffix in SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    return cleaned
