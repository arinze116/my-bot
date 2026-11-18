from __future__ import annotations

from sources import enabled_sources


def test_enabled_sources_declare_empty_result_contract(settings_factory) -> None:
    settings = settings_factory(twitter_bearer_token=str(1))

    policies = {
        source.name: source.empty_result_is_valid for source in enabled_sources(settings)
    }

    assert policies == {
        "devpost": False,
        "devfolio": False,
        "dorahacks": False,
        "ethglobal": False,
        "mlh": False,
        "lablab": True,
        "hackerearth": True,
        "gitcoin": True,
        "twitter": True,
    }
