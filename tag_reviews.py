
# tag_reviews.py

from transformers import pipeline
from tqdm import tqdm
import time

# Load once globally
classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli",
    device=-1  # ✅ CPU now, switch to device=0 when moving to GPU
)

LABELS = [
    "romantic", "adventurous", "family-friendly", "spiritual", "sunset",
    "nature", "photogenic", "historical", "cultural", "peaceful", "crowded",
    "quiet", "trek", "local food", "viewpoint"
]

def tag_place_with_reviews(place_name, reviews, min_confidence=0.6, min_occurrences=2):
    """
    Assigns tags to a POI using BERT zero-shot classification.
    Aggregates across reviews with a confidence and occurrence threshold.
    """
    if not reviews:
        print(f"⚠️ No reviews available for {place_name}, skipping tagging.")
        return []

    tag_scores = {}
    tag_count = {}

    for review in tqdm(reviews, desc=f"Tagging {place_name}", leave=False):
        review = review.strip()
        if not review:
            continue

        # Run classification
        result = classifier(review, LABELS, multi_label=True)

        # Aggregate scores
        for label, score in zip(result["labels"], result["scores"]):
            if score >= min_confidence:
                tag_scores[label] = tag_scores.get(label, 0) + score
                tag_count[label] = tag_count.get(label, 0) + 1

        time.sleep(0.05)  # Small delay for rate-limiting safety in large batches

    # Apply minimum occurrence filter
    filtered_tags = {
        tag: score for tag, score in tag_scores.items()
        if tag_count.get(tag, 0) >= min_occurrences
    }

    sorted_tags = sorted(filtered_tags.items(), key=lambda x: x[1], reverse=True)
    final_tags = [tag for tag, _ in sorted_tags]

    return final_tags


#Cache tags in Firestore.

#Only re-run tagging if reviews changed.