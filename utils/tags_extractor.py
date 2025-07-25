from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

LABELS = [
    "romantic", "adventurous", "family-friendly", "spiritual", "sunset", "nature",
    "photogenic", "historical", "cultural", "peaceful", "crowded", "quiet",
    "trek", "local food", "viewpoint"
]

model = SentenceTransformer('all-MiniLM-L6-v2')

""" def extract_tags(description):
    tags = []
    desc = description.lower()

    rules = {
        "romantic": ["romantic", "date", "couple"],
        "adventurous": ["adventure", "thrill", "exciting"],
        "family-friendly": ["family", "kids", "child", "safe"],
        "spiritual": ["temple", "spiritual", "ashram", "divine"],
        "sunset": ["sunset", "dusk"],
        "nature": ["forest", "lake", "trees", "nature", "wild"],
        "photogenic": ["photos", "instagram", "photogenic", "picturesque"],
        "historical": ["fort", "ruins", "history", "heritage"],
        "cultural": ["festival", "culture", "tradition"],
        "peaceful": ["peaceful", "calm", "serene"],
        "crowded": ["crowded", "busy", "rush"],
        "quiet": ["quiet", "silent", "isolated"],
        "trek": ["trek", "hike", "climb"],
        "local food": ["food", "cuisine", "eat", "local dish"],
        "viewpoint": ["viewpoint", "top", "hill", "scenic"]
    }

    for label, keywords in rules.items():
        if any(word in desc for word in keywords):
            tags.append(label)

    return tags """

def extract_tags(description, threshold=0.4, top_n=3):
    desc_embedding = model.encode([description])
    label_embeddings = model.encode(LABELS)

    similarities = cosine_similarity(desc_embedding, label_embeddings)[0]
    
    tag_scores = list(zip(LABELS, similarities))
    tag_scores.sort(key=lambda x: x[1], reverse=True)

    selected = [label for label, score in tag_scores if score >= threshold]
    if len(selected) < top_n:
        for label, _ in tag_scores:
            if label not in selected:
                selected.append(label)
            if len(selected) == top_n:
                break

    return selected
