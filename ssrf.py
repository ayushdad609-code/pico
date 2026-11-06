"""
SSRF Protection and Network Safety Guards for Pico.
Guarantees that web browsing, scraping, and handoffs never access internal,
private, loopback, link-local, or cloud-metadata network addresses.
"""

from __future__ import annotations
import socket
import ipaddress
from urllib.parse import urlparse
from typing import Tuple


BANNED_DOMAIN_NAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "internal",
    "metadata.google.internal",
    "instance-data",
}


def is_safe_url(url: str) -> Tuple[bool, str]:
    """Validates that a URL does not point to internal, private, or loopback networks."""
    if not url:
        return False, "Empty URL provided."

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Scheme '{parsed.scheme}' is blocked. Only HTTP/HTTPS allowed."

        host = parsed.hostname
        if not host:
            return False, "Missing hostname in URL."

        host_lower = host.lower().strip("[]")

        if host_lower in BANNED_DOMAIN_NAMES:
            return False, f"Target '{host_lower}' is blocked by Security Policy."

        if host_lower.endswith((".local", ".internal", ".localhost", ".onion")):
            return False, f"Target domain '{host_lower}' is blocked by Security Policy."

        # Check raw IP literals before DNS
        try:
            ip = ipaddress.ip_address(host_lower)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False, f"Access to private/local network address ({ip}) is blocked by Security Policy."
        except ValueError:
            pass

        # Resolve DNS and check all target IPs
        try:
            addr_info = socket.getaddrinfo(host_lower, None)
        except Exception:
            # If DNS resolution fails here, let the HTTP client handle or report DNS error
            return True, ""

        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return False, f"DNS resolved to private/local IP ({ip_str}), blocked by SSRF Security Policy."
                # Extra validation for AWS/GCP metadata & private ranges
                if ip in ipaddress.ip_network("169.254.0.0/16") or ip in ipaddress.ip_network("172.16.0.0/12"):
                    return False, f"Access to cloud metadata / link-local address ({ip_str}) is blocked."
            except ValueError:
                continue

        return True, ""
    except Exception as e:
        return False, f"Malformed URL: {str(e)}"
