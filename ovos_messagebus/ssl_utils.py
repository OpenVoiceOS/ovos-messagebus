# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Self-signed TLS certificate generation for the messagebus wss:// listener.

Bundled here instead of depending on ``ovos-utils`` because the equivalent
helper that used to live there (``ovos_utils.security.create_self_signed_cert``)
generates a 1024-bit RSA key signed with SHA-1, which OpenSSL 3 (the default
on modern Debian/Ubuntu/Fedora) refuses to load at all
(``[SSL: EE_KEY_TOO_SMALL] ee key too small``). It is also being removed
from ``ovos-utils`` upstream. This module generates RSA-2048/SHA-256 with a
subjectAltName extension instead, which is both loadable and accepted by
modern TLS clients (which require SAN and ignore the certificate CN).

Uses the ``cryptography`` library directly rather than pyOpenSSL's legacy
``crypto.X509``/``crypto.X509Extension`` API: pyOpenSSL >= 26 removed
``X509.add_extensions()`` entirely (it now delegates to ``cryptography``
internally), so building extensions through the old API is not
forward-compatible. ``cryptography`` is pyOpenSSL's own hard dependency and
is always present wherever it is installed, and its ``CertificateBuilder``
is the maintained way to add a ``SubjectAlternativeName``.
"""
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from os import makedirs
from os.path import exists, join
from socket import gethostname
from typing import Tuple


def create_self_signed_cert(cert_dir: str, name: str = "ovos-messagebus") -> Tuple[str, str]:
    """Create (or reuse) a self-signed certificate/key pair.

    Generates an RSA-2048 key signed with SHA-256, with a subjectAltName
    extension covering the local hostname, ``localhost`` and ``127.0.0.1``
    so modern TLS clients (which require SAN and ignore CN) accept it.

    If both the certificate and key already exist in ``cert_dir``, this is
    a no-op and the existing pair is reused - restarts don't regenerate a
    fresh cert/key on every boot.

    Args:
        cert_dir: directory to read/write the cert and key from. Created
            if it does not already exist.
        name: base filename (without extension) for the cert/key pair.

    Returns:
        (cert_path, key_path) tuple of absolute paths to the PEM files.

    Raises:
        ImportError: if 'cryptography' (installed via the 'pyopenssl'/'ssl'
            extra) is not available. Callers should treat this as fatal for
            the ssl:// path rather than falling back to an insecure ws://
            listener.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    cert_path = join(cert_dir, f"{name}.crt")
    key_path = join(cert_dir, f"{name}.key")

    makedirs(cert_dir, exist_ok=True)

    if exists(cert_path) and exists(key_path):
        return cert_path, key_path

    hostname = gethostname()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "PT"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Europe"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Mountains"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OpenVoiceOS"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "ovos-messagebus"),
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])

    san_names = {x509.DNSName("localhost"), x509.DNSName(hostname)}
    now = datetime.now(timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=10 * 365))
        .add_extension(
            x509.SubjectAlternativeName(
                sorted(san_names, key=lambda n: n.value) +
                [x509.IPAddress(ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    return cert_path, key_path
