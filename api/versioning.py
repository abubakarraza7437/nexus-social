from rest_framework.versioning import URLPathVersioning

V1 = "v1"
V2 = "v2"

SUPPORTED_VERSIONS = (V1, V2)
DEPRECATED_VERSIONS = ()  # Populate as versions age out


class SocialOSVersioning(URLPathVersioning):
    """
    URL-path versioning for SocialOS.

    Reads the version from the first URL segment after /api/:
      /api/v1/auth/login/  →  request.version == "v1"
      /api/v2/auth/login/  →  request.version == "v2"

    DRF raises ``NotAcceptable`` (406) for any version outside
    ``allowed_versions``, keeping unknown-version requests from
    silently hitting v1 behaviour.
    """

    default_version = V1
    allowed_versions = list(SUPPORTED_VERSIONS)
    version_param = "version"
