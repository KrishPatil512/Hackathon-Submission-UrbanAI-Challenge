from functools import lru_cache


LABEL_WATER_SEEK = "water_seek"
LABEL_WATER_AVOID = "water_avoid"
LABEL_SCENIC_SEEK = "scenic_seek"
LABEL_SCENIC_AVOID = "scenic_avoid"
LABEL_CROWDS_AVOID = "crowds_avoid"
LABEL_CROWDS_SEEK = "crowds_seek"
LABEL_SAFETY = "safety"

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import MultiLabelBinarizer

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


TRAINING_EXAMPLES: list[tuple[str, tuple[str, ...]]] = [
    ("I want a safe walk at night with well lit streets", (LABEL_SAFETY,)),
    ("Please avoid dangerous blocks and crime hotspots", (LABEL_SAFETY,)),
    ("Find the safest route with fewer incidents", (LABEL_SAFETY,)),
    ("I care most about safety and secure sidewalks", (LABEL_SAFETY,)),
    ("Give me a scenic route by parks and trees", (LABEL_SCENIC_SEEK,)),
    ("I want a pretty walk through trails and green space", (LABEL_SCENIC_SEEK,)),
    ("Take me somewhere beautiful with nature views", (LABEL_SCENIC_SEEK,)),
    ("Avoid scenic detours and keep me on normal streets", (LABEL_SCENIC_AVOID,)),
    ("I do not want parks or trails on this route", (LABEL_SCENIC_AVOID,)),
    ("Route me near water and the lake", (LABEL_WATER_SEEK,)),
    ("I would like to walk by the river or waterfront", (LABEL_WATER_SEEK,)),
    ("Prefer bridges, creeks, and water views", (LABEL_WATER_SEEK,)),
    ("Do not take me near water or lakes", (LABEL_WATER_AVOID,)),
    ("Avoid the river and stay away from waterfront paths", (LABEL_WATER_AVOID,)),
    ("Keep me away from bridges and creeks", (LABEL_WATER_AVOID,)),
    ("I want quiet streets without crowds", (LABEL_CROWDS_AVOID,)),
    ("Find a peaceful low traffic route", (LABEL_CROWDS_AVOID,)),
    ("Avoid busy bars, nightlife, and crowded areas", (LABEL_CROWDS_AVOID,)),
    ("I prefer lively areas with people around", (LABEL_CROWDS_SEEK,)),
    ("Take me through busy social streets", (LABEL_CROWDS_SEEK,)),
    ("I want active areas with restaurants and people", (LABEL_CROWDS_SEEK,)),
    (
        "I am walking at night and want a quiet scenic route near parks",
        (LABEL_SAFETY, LABEL_CROWDS_AVOID, LABEL_SCENIC_SEEK),
    ),
    (
        "I want water views but avoid crowded nightlife",
        (LABEL_WATER_SEEK, LABEL_CROWDS_AVOID),
    ),
    (
        "Safe route near the lake with parks",
        (LABEL_SAFETY, LABEL_WATER_SEEK, LABEL_SCENIC_SEEK),
    ),
    (
        "Avoid water but give me scenic green streets",
        (LABEL_WATER_AVOID, LABEL_SCENIC_SEEK),
    ),
    (
        "No crowds and no water, just the safest path",
        (LABEL_CROWDS_AVOID, LABEL_WATER_AVOID, LABEL_SAFETY),
    ),
    (
        "Busy route with people around, not isolated",
        (LABEL_CROWDS_SEEK, LABEL_SAFETY),
    ),
]


def _weight_from_probability(probability: float) -> int:
    if probability >= 0.70:
        return 5
    if probability >= 0.55:
        return 4
    if probability >= 0.40:
        return 3
    if probability >= 0.28:
        return 2
    return 0


@lru_cache(maxsize=1)
def _trained_preference_model():
    if not SKLEARN_AVAILABLE:
        return None

    texts = [text for text, _labels in TRAINING_EXAMPLES]
    label_sets = [labels for _text, labels in TRAINING_EXAMPLES]

    binarizer = MultiLabelBinarizer()
    targets = binarizer.fit_transform(label_sets)
    model = Pipeline(
        steps=[
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True)),
            (
                "classifier",
                OneVsRestClassifier(LogisticRegression(max_iter=1000)),
            ),
        ]
    )
    model.fit(texts, targets)
    return model, binarizer


def classify_preference_text(text: str) -> dict[str, int | str] | None:
    """Classify free-text route preferences into ranking weights.

    The model is intentionally lightweight for the hackathon prototype: a local
    TF-IDF + logistic regression classifier trained from seed examples at app
    startup. If scikit-learn is not installed, callers can fall back to rules.
    """

    cleaned_text = text.strip()
    if not cleaned_text:
        return None

    trained = _trained_preference_model()
    if trained is None:
        return None

    model, binarizer = trained
    probabilities = model.predict_proba([cleaned_text])[0]
    scores = dict(zip(binarizer.classes_, probabilities))

    water_seek = _weight_from_probability(scores.get(LABEL_WATER_SEEK, 0.0))
    water_avoid = _weight_from_probability(scores.get(LABEL_WATER_AVOID, 0.0))
    scenic_seek = _weight_from_probability(scores.get(LABEL_SCENIC_SEEK, 0.0))
    scenic_avoid = _weight_from_probability(scores.get(LABEL_SCENIC_AVOID, 0.0))
    crowds_avoid = _weight_from_probability(scores.get(LABEL_CROWDS_AVOID, 0.0))
    crowds_seek = _weight_from_probability(scores.get(LABEL_CROWDS_SEEK, 0.0))
    safety = _weight_from_probability(scores.get(LABEL_SAFETY, 0.0))

    water_mode = "avoid" if water_avoid > water_seek else "seek"
    scenic_mode = "avoid" if scenic_avoid > scenic_seek else "seek"
    crowd_mode = "seek" if crowds_seek > crowds_avoid else "avoid"

    return {
        "water": max(water_seek, water_avoid),
        "scenic": max(scenic_seek, scenic_avoid),
        "crowds": max(crowds_avoid, crowds_seek),
        "safety": safety,
        "water_mode": water_mode,
        "scenic_mode": scenic_mode,
        "crowd_mode": crowd_mode,
    }
