from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

# Cloud metadata endpoints and known dangerous IPs
BLOCKED_IPS = {
    "169.254.169.254",  # AWS/GCP/Azure link-local metadata
    "fd00:ec2::254",    # AWS IPv6 metadata
}


CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def validate_outbound_url(url: str, allow_private: bool | None = None) -> None:
    """
    Validates that a URL is safe for outbound dispatch (webhook / telemetry push).
    Rejects non-HTTP(S) protocols and destinations that resolve to loopback,
    link-local metadata, or private IP addresses unless allow_private is explicitly enabled.
    """
    if not url:
        raise ValueError("URL cannot be empty.")

    if allow_private is None:
        allow_private = os.environ.get("NETMON_ALLOW_PRIVATE_WEBHOOKS", "false").lower() in (
            "true",
            "1",
            "yes",
        )

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(
            f"Invalid protocol '{parsed.scheme}'. Only HTTP and HTTPS URLs are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid URL '{url}': Missing hostname.")

    # Check for direct cloud metadata IP in host string
    if hostname in BLOCKED_IPS:
        raise ValueError(f"SSRF violation: Access to cloud metadata IP {hostname} is blocked.")

    # Check if host is direct IP address or requires DNS resolution
    try:
        resolved_ips = []
        try:
            direct_ip = ipaddress.ip_address(hostname)
            resolved_ips.append(direct_ip)
        except ValueError:
            # Domain name: resolve via DNS
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
            addr_info = socket.getaddrinfo(
                hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM
            )
            for item in addr_info:
                ip_str = item[4][0]
                resolved_ips.append(ipaddress.ip_address(ip_str))

        if not resolved_ips:
            raise ValueError(f"DNS resolution failure for host '{hostname}'.")

        for ip in resolved_ips:
            str_ip = str(ip)
            if str_ip in BLOCKED_IPS:
                raise ValueError(
                    f"SSRF violation: Host '{hostname}' resolves to blocked metadata address {str_ip}."
                )

            if ip.is_loopback:
                raise ValueError(
                    f"SSRF violation: Host '{hostname}' resolves to loopback address {str_ip}."
                )

            if ip.is_link_local:
                raise ValueError(
                    f"SSRF violation: Host '{hostname}' resolves to link-local address {str_ip}."
                )

            if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                raise ValueError(
                    f"SSRF violation: Host '{hostname}' resolves to invalid/reserved address {str_ip}."
                )

            if not allow_private and (not ip.is_global or ip.is_private or (ip.version == 4 and ip in CGNAT_NETWORK)):
                raise ValueError(
                    f"SSRF violation: Host '{hostname}' resolves to non-global or private network address {str_ip}."
                )

    except socket.gaierror as err:
        raise ValueError(f"Failed to resolve host '{hostname}': {err}") from err
