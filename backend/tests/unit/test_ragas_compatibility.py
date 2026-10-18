from app.evaluations.ragas_compat import load_ragas


def test_ragas_imports_through_compatibility_boundary() -> None:
    ragas = load_ragas()

    assert ragas.__name__ == "ragas"
    assert callable(ragas.evaluate)
