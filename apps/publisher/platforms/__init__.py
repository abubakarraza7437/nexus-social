import logging

from apps.publisher.platforms.mock import MockPublisher

logger = logging.getLogger(__name__)

# Platform string → publisher class (instantiated per task call, not a singleton).
REGISTRY: dict[str, type] = {
    "mock": MockPublisher,
    # Real adapters are added here as they are implemented:
    # "facebook":  FacebookPublisher,
    # "twitter":   TwitterPublisher,
    # "instagram": InstagramPublisher,
    # "linkedin":  LinkedInPublisher,
    # "tiktok":    TikTokPublisher,
    # "youtube":   YouTubePublisher,
    # "pinterest": PinterestPublisher,
    # "reddit":    RedditPublisher,
}


def get_publisher(platform: str):
    """Return an initialised publisher for *platform*."""
    publisher_cls = REGISTRY.get(platform)
    if publisher_cls is None:
        logger.warning(
            "No publisher registered for platform '%s'. Falling back to MockPublisher.",
            platform,
        )
        publisher_cls = MockPublisher
    return publisher_cls()
