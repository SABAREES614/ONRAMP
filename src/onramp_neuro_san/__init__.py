"""ONRAMP - local-first, human-governed client onboarding workbench.

Built on neuro-san-studio. Post-sale onboarding agent network: an Onboarding
Concierge frontman coordinating eight specialist agents via AAOSA, with
deterministic Python evidence checks, named human gates and a SQLite audit trail.
"""

__version__ = "0.2.0"


def main() -> None:
    """Console-script entrypoint: launch the ONRAMP FastAPI server."""
    import uvicorn

    uvicorn.run(
        "onramp_neuro_san.server.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
