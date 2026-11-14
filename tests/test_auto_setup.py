"""Unit tests for the Smart Setup engine's pure logic."""

import base64

import pytest

from app.models.auto_setup import SmartSetupRequest
from app.operation.auto_setup import SmartSetupOperation


def test_reality_keypair_is_valid_x25519():
    op = SmartSetupOperation.__new__(SmartSetupOperation)  # statics only; no operator wiring needed

    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    private_b64, public_b64 = op._reality_keypair()
    assert len(private_b64) == 43 and len(public_b64) == 43
    assert "=" not in private_b64 and "=" not in public_b64

    # The public key must really derive from the private key.
    private_raw = base64.urlsafe_b64decode(private_b64 + "=" * (-len(private_b64) % 4))
    key = X25519PrivateKey.from_private_bytes(private_raw)
    derived = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_raw = base64.urlsafe_b64decode(public_b64 + "=" * (-len(public_b64) % 4))
    assert derived == public_raw


@pytest.mark.parametrize(
    "profile, expect_vmess",
    [("turbo", False), ("balanced", False), ("stealth", True)],
)
def test_build_config_profile_changes_stack(profile, expect_vmess):
    op = SmartSetupOperation.__new__(SmartSetupOperation)
    req = SmartSetupRequest(domain="panel.example.com", base_port=443)
    config, descriptors = op._build_config(req, profile)

    tags = [d["tag"] for d in descriptors]
    assert tags == [d["tag"] for d in config["inbounds"]]
    assert "VLESS-REALITY" in tags and "VLESS-WS" in tags and "SS-2022" in tags
    assert ("VMESS-WS" in tags) == expect_vmess

    reality = next(i for i in config["inbounds"] if i["tag"] == "VLESS-REALITY")
    rs = reality["streamSettings"]["realitySettings"]
    assert len(rs["privateKey"]) == 43 and len(rs["shortIds"][0]) == 8
    assert reality["port"] == 443

    ss = next(i for i in config["inbounds"] if i["tag"] == "SS-2022")
    assert len(base64.b64decode(ss["settings"]["password"], validate=True)) == 32

    # ws paths carry a random suffix
    vless_ws = next(i for i in config["inbounds"] if i["tag"] == "VLESS-WS")
    assert vless_ws["streamSettings"]["wsSettings"]["path"].startswith("/vlessws-")

    # ports_to_open is derivable from descriptors
    assert {d["port"] for d in descriptors} == {443, 2052, 8388} | ({2054} if expect_vmess else set())


def test_build_config_custom_base_port():
    op = SmartSetupOperation.__new__(SmartSetupOperation)
    req = SmartSetupRequest(domain="panel.example.com", base_port=8443)
    config, descriptors = op._build_config(req, "balanced")
    reality = next(d for d in descriptors if d["tag"] == "VLESS-REALITY")
    assert reality["port"] == 8443
    assert next(i for i in config["inbounds"] if i["tag"] == "VLESS-REALITY")["port"] == 8443
