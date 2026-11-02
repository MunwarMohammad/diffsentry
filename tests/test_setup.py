from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values

from reviewer.config import Settings
from scripts.configure_app import main


def test_key_import_roundtrip_without_disclosure(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text(
        "GITHUB_APP_ID=\nGITHUB_APP_PRIVATE_KEY=\nGITHUB_APP_PRIVATE_KEY_PATH=\n"
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    Path("download.pem").write_text(pem)
    monkeypatch.setattr("sys.argv", ["configure_app", "--app-id", "123", "--pem", "download.pem"])
    main()
    values = dotenv_values(".env")
    assert values["GITHUB_APP_ID"] == "123"
    settings = Settings(github_app_private_key=values["GITHUB_APP_PRIVATE_KEY"])
    assert settings.private_key() == pem
    assert pem not in capsys.readouterr().out
    assert Path(".env").stat().st_mode & 0o777 == 0o600


def test_invalid_key_does_not_replace_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text("GITHUB_APP_ID=existing\n")
    Path("bad.pem").write_text("invalid")
    monkeypatch.setattr("sys.argv", ["configure_app", "--app-id", "123", "--pem", "bad.pem"])
    with pytest.raises(SystemExit):
        main()
    assert Path(".env").read_text() == "GITHUB_APP_ID=existing\n"
