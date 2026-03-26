#!/usr/bin/env python3
"""Generate a 2D embedding visualization (t-SNE with PCA fallback) for Module 5."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from pykeen.models import DistMult, TransE
from pykeen.training import SLCWATrainingLoop
from pykeen.triples import TriplesFactory
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE


def get_entity_embeddings(model):
    if hasattr(model, "entity_embeddings"):
        return model.entity_embeddings.weight.detach().cpu().numpy()
    return model.entity_representations[0](indices=None).detach().cpu().numpy()


def train_model(model_name: str, tf_train: TriplesFactory, epochs: int = 40):
    if model_name == "TransE":
        model = TransE(triples_factory=tf_train, embedding_dim=64, random_seed=42)
    else:
        model = DistMult(triples_factory=tf_train, embedding_dim=64, random_seed=42)

    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    training_loop = SLCWATrainingLoop(
        model=model,
        triples_factory=tf_train,
        optimizer=optimizer,
    )
    training_loop.train(triples_factory=tf_train, num_epochs=epochs)
    return model


def make_projection(embeddings: np.ndarray) -> tuple[np.ndarray, str]:
    n = embeddings.shape[0]
    if n >= 30:
        perplexity = max(5, min(30, n // 10))
        proj = TSNE(n_components=2, random_state=42, perplexity=perplexity).fit_transform(embeddings)
        return proj, f"t-SNE (perplexity={perplexity})"

    proj = PCA(n_components=2, random_state=42).fit_transform(embeddings)
    return proj, "PCA fallback (insufficient samples for stable t-SNE)"


def main():
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data" / "kge"
    out_dir = project_root / "reports" / "kge"
    out_dir.mkdir(parents=True, exist_ok=True)

    tf_train = TriplesFactory.from_path(data_dir / "train.txt")

    transe = train_model("TransE", tf_train, epochs=40)
    distmult = train_model("DistMult", tf_train, epochs=40)

    emb_transe = get_entity_embeddings(transe)
    emb_distmult = get_entity_embeddings(distmult)

    p_transe, method_transe = make_projection(emb_transe)
    p_distmult, method_distmult = make_projection(emb_distmult)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), dpi=140)

    axes[0].scatter(p_transe[:, 0], p_transe[:, 1], s=10, alpha=0.8)
    axes[0].set_title(f"TransE 2D Projection\n{method_transe}")
    axes[0].set_xlabel("Dim 1")
    axes[0].set_ylabel("Dim 2")

    axes[1].scatter(p_distmult[:, 0], p_distmult[:, 1], s=10, alpha=0.8, color="tab:orange")
    axes[1].set_title(f"DistMult 2D Projection\n{method_distmult}")
    axes[1].set_xlabel("Dim 1")
    axes[1].set_ylabel("Dim 2")

    fig.suptitle("Module 5: Entity Embedding Projection", fontsize=12)
    fig.tight_layout()

    image_path = out_dir / "tsne_projection.png"
    fig.savefig(image_path)
    plt.close(fig)

    summary = {
        "entities": int(tf_train.num_entities),
        "triple_count_train": int(tf_train.num_triples),
        "transE_projection": method_transe,
        "distMult_projection": method_distmult,
        "output_figure": str(image_path.relative_to(project_root)).replace("\\", "/"),
    }

    with open(out_dir / "tsne_projection_meta.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("[OK] Wrote", image_path)
    print("[OK] Wrote", out_dir / "tsne_projection_meta.json")


if __name__ == "__main__":
    main()
