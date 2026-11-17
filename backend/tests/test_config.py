from backend.app.config import Settings


def test_comma_separated_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv(
        "RESEARCHBRIDGE_CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    )

    settings = Settings()

    assert settings.cors_origins == [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]
