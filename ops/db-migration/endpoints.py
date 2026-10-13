"""Validate Neon runtime URLs and derive direct replication URLs."""
from urllib.parse import parse_qs, urlsplit


def neon_urls(url):
    if not isinstance(url, str) or len(url) > 1800 or any(c.isspace() for c in url):
        raise ValueError("Invalid Neon URL")
    parts = urlsplit(url)
    if (parts.scheme not in ("postgres", "postgresql") or not parts.hostname or
            not parts.hostname.endswith(".neon.tech") or not parts.username or not parts.password or
            parts.port not in (None, 5432) or not parts.path.strip("/") or parts.fragment):
        raise ValueError("Use a complete Neon PostgreSQL URL on port 5432")
    options = parse_qs(parts.query, keep_blank_values=True)
    if set(options) - {"sslmode", "channel_binding"} or len(options.get("sslmode", [])) != 1:
        raise ValueError("Unsupported Neon URL options")
    if options["sslmode"][0] not in ("require", "verify-full", "verify-ca"):
        raise ValueError("Neon URLs must require TLS")
    if "channel_binding" in options and options["channel_binding"] != ["require"]:
        raise ValueError("Unsupported channel binding")
    direct_host = parts.hostname.replace("-pooler.", ".", 1)
    direct_netloc = parts.netloc.replace("@" + parts.hostname, "@" + direct_host, 1)
    return {"runtime_url": url, "direct_url": parts._replace(netloc=direct_netloc).geturl()}
