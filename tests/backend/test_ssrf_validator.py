import pytest
from app.services.ssrf_validator import validate_outbound_url


def test_ssrf_valid_public_url():
    # Public domains or public mock
    # validate_outbound_url resolves domain via DNS, so we can test with a known public domain or public IP
    validate_outbound_url("https://8.8.8.8/webhook", allow_private=False)
    validate_outbound_url("https://1.1.1.1/api/v1", allow_private=False)


def test_ssrf_invalid_schemes():
    with pytest.raises(ValueError, match="Invalid protocol"):
        validate_outbound_url("ftp://example.com/upload")

    with pytest.raises(ValueError, match="Invalid protocol"):
        validate_outbound_url("file:///etc/shadow")


def test_ssrf_blocks_loopback():
    with pytest.raises(ValueError, match="loopback"):
        validate_outbound_url("http://127.0.0.1:8000/api")

    with pytest.raises(ValueError, match="loopback"):
        validate_outbound_url("http://127.0.0.2:9000")


def test_ssrf_blocks_cloud_metadata():
    with pytest.raises(ValueError, match="cloud metadata|blocked metadata"):
        validate_outbound_url("http://169.254.169.254/latest/meta-data")


def test_ssrf_blocks_private_by_default():
    with pytest.raises(ValueError, match="private network"):
        validate_outbound_url("http://10.0.0.5/webhook", allow_private=False)

    with pytest.raises(ValueError, match="private network"):
        validate_outbound_url("http://192.168.1.100/webhook", allow_private=False)


def test_ssrf_allows_private_when_flag_enabled():
    # Should not raise exception
    validate_outbound_url("http://192.168.1.100/webhook", allow_private=True)
    validate_outbound_url("http://10.10.10.10:8080/hook", allow_private=True)


def test_ssrf_blocks_cgnat_rfc6598():
    with pytest.raises(ValueError, match="private network"):
        validate_outbound_url("http://100.64.0.1/test", allow_private=False)

    with pytest.raises(ValueError, match="private network"):
        validate_outbound_url("http://100.127.255.254/api", allow_private=False)

