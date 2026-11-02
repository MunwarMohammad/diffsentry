"""Create a private local configuration without overwriting existing credentials."""

import os
import secrets
from pathlib import Path


def main():
    target = Path(".env")
    if target.exists():
        print(".env already exists; left unchanged.")
        return
    content = Path(".env.example").read_text()
    content = content.replace("local-demo-webhook-secret", secrets.token_hex(32))
    content = content.replace("local-demo-internal-token", secrets.token_hex(32))
    content = content.replace(
        "ALLOWED_REPOSITORIES=demo/example",
        "ALLOWED_REPOSITORIES=demo/example,MunwarMohammad/diffsentry-test",
    )
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(content)
    print(
        "Created .env with unique secrets and owner-only permissions. No credential values printed."
    )


if __name__ == "__main__":
    main()
