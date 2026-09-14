from rapidfuzz import fuzz
from models import MissingPerson

NAME_MATCH_THRESHOLD = 78      # 0-100, higher = stricter
LOCATION_MATCH_THRESHOLD = 65
AGE_TOLERANCE = 4              # years


def find_possible_duplicates(full_name, gender, age, district, municipality, ward_no, exclude_id=None):
    """
    Returns a list of MissingPerson records that could be the same person
    as the one being reported, ranked by similarity score.

    Required signal: name + gender must match (both are compulsory fields).
    Optional signals (only applied when data exists on both sides):
    age proximity, district, municipality/ward/landmark similarity.

    District alone is far too broad after a large disaster, so ward/
    municipality is weighted more heavily when available.
    """
    query = MissingPerson.query.filter(
        MissingPerson.status.in_(["missing", "found_safe"]),
    )

    # Gender is compulsory on every record, so always filter on it exactly -
    # it's a hard disambiguator and cheap to apply before fuzzy scoring.
    if gender:
        query = query.filter(MissingPerson.gender == gender)

    candidates = query.all()

    results = []
    for c in candidates:
        if exclude_id and c.id == exclude_id:
            continue

        name_score = fuzz.token_sort_ratio(full_name.lower().strip(), c.full_name.lower().strip())
        if name_score < NAME_MATCH_THRESHOLD:
            continue

        # Age proximity check (only if both ages are known - age is optional)
        if age and c.age:
            if abs(int(age) - int(c.age)) > AGE_TOLERANCE:
                continue

        # District check (only if both provided - district is optional)
        if district and c.district:
            if district.strip().lower() != c.district.strip().lower():
                continue

        # Location similarity: compare municipality + ward + landmark text combined
        loc_a = f"{municipality or ''} {ward_no or ''}".lower().strip()
        loc_b = f"{c.municipality or ''} {c.ward_no or ''}".lower().strip()
        loc_score = fuzz.partial_ratio(loc_a, loc_b) if loc_a and loc_b else 50

        if loc_a and loc_b and loc_score < LOCATION_MATCH_THRESHOLD:
            continue

        combined_score = (name_score * 0.6) + (loc_score * 0.4)
        results.append((combined_score, c))

    results.sort(key=lambda x: x[0], reverse=True)
    return [c for score, c in results[:5]]
