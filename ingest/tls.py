"""TLS chain completion for hosts that do not send their intermediate certificate (tesoro.es on 2026-09-10).

Verification is NEVER disabled. When a verified request fails with CERTIFICATE_VERIFY_FAILED, the leaf certificate is fetched, its
Authority Information Access (AIA) "CA Issuers" URL is followed (what browsers do), the intermediate(s) are appended to the certifi bundle
in a per-host PEM under the raw directory, and the request is retried with verify=<that bundle>. If the chain still fails to verify, the error
is raised unchanged (an untrusted host is never silently accepted)."""
from __future__ import annotations
import os
import ssl
import socket
from typing import List, Optional
from urllib.parse import urlparse

_BUNDLES: dict = {}


def _fetch_leaf_der(host: str, port: int = 443, timeout: int = 20) -> bytes:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # only to READ the leaf and its AIA; nothing is trusted from this connection
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as s:
            return s.getpeercert(binary_form=True)


def _aia_issuers(der: bytes) -> List[str]:
    from cryptography import x509  # type: ignore
    from cryptography.x509.oid import ExtensionOID, AuthorityInformationAccessOID  # type: ignore
    cert = x509.load_der_x509_certificate(der)
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
    except x509.ExtensionNotFound:
        return []
    return [d.access_location.value for d in aia if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS]


def _is_self_signed(der: bytes) -> bool:
    from cryptography import x509  # type: ignore
    c = x509.load_der_x509_certificate(der)
    return c.issuer == c.subject


def build_bundle(host: str, raw_dir: Optional[str], timeout: int = 20, port: int = 443) -> str:
    """certifi bundle + the intermediates reachable through AIA from the host's leaf. Returns the PEM path."""
    import certifi  # type: ignore
    import requests  # type: ignore
    from cryptography import x509  # type: ignore
    from cryptography.hazmat.primitives import serialization  # type: ignore
    if host in _BUNDLES:
        return _BUNDLES[host]
    der = _fetch_leaf_der(host, port=port, timeout=timeout)
    pems: List[str] = []
    seen = set()
    for _ in range(4):  # leaf → intermediate(s) → root; stop at a self-signed cert or when no AIA is given
        urls = [u for u in _aia_issuers(der) if u.startswith("http")]
        if not urls:
            break
        nxt = None
        for u in urls:
            if u in seen:
                continue
            seen.add(u)
            r = requests.get(u, timeout=timeout)  # issuer repositories (CA hosts) verify with the normal bundle
            if r.status_code == 200 and r.content:
                nxt = r.content
                break
        if nxt is None:
            break
        try:
            c = x509.load_der_x509_certificate(nxt)
        except ValueError:
            c = x509.load_pem_x509_certificate(nxt)
        pems.append(c.public_bytes(serialization.Encoding.PEM).decode("ascii"))
        der = c.public_bytes(serialization.Encoding.DER)
        if _is_self_signed(der):
            break
    if not pems:
        raise ssl.SSLCertVerificationError("no AIA issuer certificate found for %s" % host)
    out_dir = os.path.join(raw_dir or ".", "certs")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s.pem" % host.replace(".", "_"))
    with open(certifi.where(), encoding="ascii", errors="ignore") as f:
        base = f.read()
    with open(path, "w", encoding="ascii") as f:
        f.write(base)
        if not base.endswith("\n"):
            f.write("\n")
        f.write("".join(pems))
    _BUNDLES[host] = path
    return path


def request(method: str, url: str, raw_dir: Optional[str] = None, notes: Optional[dict] = None, **kw):
    """requests.request with chain completion on CERTIFICATE_VERIFY_FAILED (verify stays on)."""
    import requests  # type: ignore
    host = urlparse(url).hostname or ""
    if host in _BUNDLES:
        kw.setdefault("verify", _BUNDLES[host])
    try:
        return requests.request(method, url, **kw)
    except requests.exceptions.SSLError as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e) or host in _BUNDLES:
            raise
        to = kw.get("timeout")
        bundle = build_bundle(host, raw_dir, timeout=int(to) if isinstance(to, (int, float)) else 20, port=urlparse(url).port or 443)
        if notes is not None:
            notes.setdefault("tls", {})[host] = "server chain incomplete; intermediate completed via AIA, verified against certifi"
        kw["verify"] = bundle
        return requests.request(method, url, **kw)
