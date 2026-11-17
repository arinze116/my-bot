from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from config import Settings
from scrapers import (
    devfolio,
    devpost,
    dorahacks,
    ethglobal,
    gitcoin,
    hackerearth,
    lablab,
    mlh,
    twitter,
)

FetchFunction = Callable[[], list[dict]]


@dataclass(frozen=True, slots=True)
class SourceSpec:
    name: str
    display_name: str
    fetch: FetchFunction


def enabled_sources(settings: Settings) -> list[SourceSpec]:
    candidates = (
        (settings.enabled_devpost, SourceSpec("devpost", "Devpost", devpost.fetch)),
        (settings.enabled_devfolio, SourceSpec("devfolio", "Devfolio", devfolio.fetch)),
        (settings.enabled_dorahacks, SourceSpec("dorahacks", "DoraHacks", dorahacks.fetch)),
        (
            settings.enabled_ethglobal,
            SourceSpec("ethglobal", "ETHGlobal", ethglobal.fetch),
        ),
        (settings.enabled_mlh, SourceSpec("mlh", "MLH", mlh.fetch)),
        (settings.enabled_lablab, SourceSpec("lablab", "Lablab.ai / Starfield Labs", lablab.fetch)),
        (
            settings.enabled_hackerearth,
            SourceSpec("hackerearth", "HackerEarth", hackerearth.fetch),
        ),
        (settings.enabled_gitcoin, SourceSpec("gitcoin", "Gitcoin", gitcoin.fetch)),
        (
            settings.enabled_twitter and bool(settings.twitter_bearer_token),
            SourceSpec("twitter", "X/Twitter", twitter.fetch),
        ),
    )
    return [source for is_enabled, source in candidates if is_enabled]
