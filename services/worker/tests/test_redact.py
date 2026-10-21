from legacylift_worker.redact import redact_secrets


def test_redact_replaces_key_assignment_and_pem() -> None:
    text = (
        "api_key='abcdEFGHijklMNOP'\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA\n"
        "-----END RSA PRIVATE KEY-----\n"
        "print('hello')\n"
    )
    out = redact_secrets(text)
    assert "abcdEFGHijklMNOP" not in out
    assert "BEGIN RSA PRIVATE KEY" not in out
    assert "[REDACTED]" in out
    assert "print('hello')" in out
