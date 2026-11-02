"""Import a downloaded App key into ignored .env without displaying credentials."""

import argparse
import getpass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from dotenv import set_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--pem", required=True, type=Path)
    parser.add_argument(
        "--openai", action="store_true", help="Prompt privately for the OpenAI API key"
    )
    args = parser.parse_args()
    if not args.app_id.isdigit():
        raise SystemExit("App ID must be numeric")
    target = Path(".env")
    if not target.exists():
        raise SystemExit("Run python -m scripts.init_env first")
    try:
        pem = args.pem.read_text()
        key = load_pem_private_key(pem.encode(), password=None)
    except (OSError, ValueError, TypeError):
        raise SystemExit("Cannot read a valid unencrypted App private key from that file") from None
    if not isinstance(key, RSAPrivateKey):
        raise SystemExit("GitHub App authentication requires an RSA key")
    target.chmod(0o600)
    set_key(target, "GITHUB_APP_ID", args.app_id)
    # Store literal backslash-n, which Settings.private_key restores. This keeps
    # .env portable between dotenv and Compose without host file UID problems.
    set_key(target, "GITHUB_APP_PRIVATE_KEY", pem.replace("\n", "\\n"))
    set_key(target, "GITHUB_APP_PRIVATE_KEY_PATH", "")
    if args.openai:
        value = getpass.getpass("OpenAI API key (hidden): ").strip()
        if not value:
            raise SystemExit("No OpenAI key entered; App configuration was saved")
        set_key(target, "OPENAI_API_KEY", value)
    target.chmod(0o600)
    print("App ID and validated RSA key saved in ignored .env. No secrets printed.")
    print("Install the App on diffsentry-test, configure OpenAI, then set REVIEW_MODE=live.")


if __name__ == "__main__":
    main()
