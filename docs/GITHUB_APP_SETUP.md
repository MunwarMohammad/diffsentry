# Create your DiffSentry GitHub App

Use your personal GitHub account `MunwarMohammad`. The private sandbox [diffsentry-test](https://github.com/MunwarMohammad/diffsentry-test) is ready.

## 1. Open registration

Use [the prefilled registration form](https://github.com/settings/apps/new?name=DiffSentry-Munwar&description=Multi-Agent%20GitHub%20Code%20Reviewer&url=https%3A%2F%2Fgithub.com%2FMunwarMohammad%2Fdiffsentry&public=false&contents=read&pull_requests=write&webhook_active=true&events%5B%5D=pull_request) in your signed-in browser. If that name is taken, add a short suffix.

The link sets the homepage, private App visibility, Contents read permission, Pull requests write permission, and the Pull request event. Metadata read is included automatically. GitHub documents these [registration parameters](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-using-url-parameters).

## 2. Configure webhook delivery

For local testing, a webhook relay forwards GitHub requests to `http://127.0.0.1:8100/webhook/github`. Your local `.env` contains `GITHUB_WEBHOOK_PROXY_URL`, generated during setup. Use that value as the GitHub App's **Webhook URL**. It is intentionally kept out of Git.

Copy the value of `GITHUB_WEBHOOK_SECRET` from your local `.env` into the form's **Webhook secret** field. Keep **Active** enabled and SSL verification on. Leave OAuth callback and setup URLs empty; this App authenticates with installation tokens.

Under **Where can this GitHub App be installed?**, select **Only on this account**. Check the settings and click **Create GitHub App** yourself. Do not paste the webhook secret or generated private key into chat.

## 3. Generate and save the App key

On the App settings page:

1. Copy its numeric **App ID** to `GITHUB_APP_ID` in `.env`.
2. Click **Generate a private key** and save the downloaded `.pem` securely.
3. Import the downloaded key with the command below, replacing the ID and path with your own. `--openai` prompts privately for your OpenAI API key.
4. Set `REVIEW_MODE=live` in `.env`. Keep `PUBLISH_REVIEWS=false` for the first real analysis.

```bash
uv run python -m scripts.configure_app --app-id YOUR_APP_ID --pem /absolute/path/to/downloaded.pem --openai
```

The helper validates the RSA key, stores it in the ignored `.env`, and prints no credential values. No private-key bind mount is needed.

The `secrets/` directory, PEM files and `.env` are ignored by Git and excluded from the Docker image.

## 4. Install only on the sandbox

In App settings, choose **Install App**, select your account, choose **Only select repositories**, and select **diffsentry-test**. Review the requested repository permissions and click **Install** yourself.

This grants the App read access to the sandbox's code and write access to its pull-request reviews. No access to your other repositories is needed for the initial test.

## 5. Start the live stack and relay

```bash
docker compose up -d --build --wait
```

Start the relay in a second terminal, replacing `YOUR_LOCAL_PROXY_URL` with the value in `.env`:

```bash
npx --yes smee-client@5.0.0 --url YOUR_LOCAL_PROXY_URL --target http://127.0.0.1:8100/webhook/github
```

The channel is a relay for webhook payloads; it does not host your application. Use it for the private test repository only. The gateway still verifies GitHub's HMAC signature on every forwarded request. Keep the relay running during tests.

Run the configuration check inside Docker so it checks the same environment as the live services:

```bash
docker compose exec -T webhook python -m scripts.doctor --live
```

A passing doctor check confirms configuration format, not provider authentication. Open a small PR in the sandbox, verify delivery and a `dry_run` review, then enable `PUBLISH_REVIEWS=true`, recreate the stack, and push a new test commit to verify actual comments. The demo and resilience scripts deliberately refuse to run in live mode.
