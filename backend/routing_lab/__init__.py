"""Offline routing lab: train and honestly evaluate learned routers on public data.

Nothing here is imported by the gateway. Run the stages in order (from backend/):

    python -m routing_lab.download    # SPROUT -> data/lab/sprout_compact.parquet
    python -m routing_lab.embed       # prompt embeddings -> data/lab/embeddings_*.npy
    python -m routing_lab.evaluate    # cost-vs-quality curves, baselines, CIs -> data/lab/report.*
"""
