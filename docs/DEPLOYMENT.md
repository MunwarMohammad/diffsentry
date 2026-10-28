# AWS and Kubernetes deployment

Local Docker operation is tested separately from cloud deployment. These files have been prepared for your accounts; they have not provisioned AWS resources. Review the Terraform plan before applying it. EKS, NAT gateways, database/cache instances, load balancers, and storage incur charges while running.

## 1. Infrastructure

Install Terraform 1.9+ and AWS CLI, authenticate to your AWS account, and copy the example variables:

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
```

Set your region, existing administrator role ARN, restricted administrator public IP CIDR, and an EKS Kubernetes version currently in standard support in that region. The supplied example deliberately does not guess your account or cluster version.

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan -out=deployment.tfplan
# Review the plan and estimated account-specific costs before applying.
terraform -chdir=infra/terraform apply deployment.tfplan
```

Resources: VPC with two public/private subnet pairs and a NAT gateway; EKS with two managed nodes; private encrypted PostgreSQL and TLS/authenticated Redis; immutable ECR repository; private encrypted/versioned S3 reports bucket. The reports bucket is available for manual/CI exports; application reports currently remain in PostgreSQL and local/CI artifacts.

Use an encrypted, access-controlled remote Terraform backend before team use. Terraform state contains generated database/cache credentials. Local state and variable files are ignored by Git, but still require filesystem protection.

## 2. Container image

Use the returned ECR repository URL and your region. Authenticate Docker to ECR using the AWS CLI, then build for the cluster's architecture (the default `t3.medium` nodes are amd64):

```bash
# Set these shell variables to your own Terraform outputs and a unique version tag.
REVIEWER_REGION=us-east-1
REVIEWER_REGISTRY=YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
REVIEWER_IMAGE="$REVIEWER_REGISTRY/pr-reviewer:YOUR_COMMIT_SHA"
aws ecr get-login-password --region "$REVIEWER_REGION" | docker login --username AWS --password-stdin "$REVIEWER_REGISTRY"
docker buildx build --platform linux/amd64 --tag "$REVIEWER_IMAGE" --push .
```

Alternatively, the manual GitHub Actions **Build release image** workflow publishes to GHCR. Private GHCR images need an appropriate Kubernetes image pull secret. The included workflow does not deploy to AWS; it needs no AWS credentials.

## 3. Kubernetes configuration and migration

Authenticate as the configured EKS administrator role. Use `aws eks update-kubeconfig --name pr-reviewer --region YOUR_REGION --role-arn YOUR_ADMIN_ROLE` if needed.

1. Apply `infra/k8s/namespace.yaml`.
2. Edit the repository allowlist in `infra/k8s/configmap.yaml`; retain `PUBLISH_REVIEWS=false` for initial validation.
3. Copy `secret.example.yaml` to the ignored `secret.yaml`, replace all placeholders locally, then apply it. Use the sensitive Terraform database/Redis outputs, your own App credentials and independently generated secrets. Prefer your organization's secret manager for actual production.
4. Set the actual image name and immutable tag in `infra/k8s/kustomization.yaml`.
5. Apply the ConfigMap before running migrations: `kubectl apply -n pr-reviewer -f infra/k8s/configmap.yaml`.
6. Set the same actual image in a local copy of `infra/k8s/migration.yaml`, apply that Job, and wait for completion. The migration Job is intentionally separate from the application resources so deployment ordering is explicit.

Example migration image substitution without editing the template:

```bash
kubectl set image --local -f infra/k8s/migration.yaml migrate="$REVIEWER_IMAGE" -o yaml | kubectl apply -f -
kubectl wait -n pr-reviewer --for=condition=complete job/reviewer-migrate --timeout=300s
kubectl apply -k infra/k8s
kubectl rollout status -n pr-reviewer deployment/gateway --timeout=300s
kubectl get pods -n pr-reviewer
```

On a subsequent release, delete the completed migration Job before creating it with the new immutable image. Apply compatible migrations before updating the applications. Migrations are never run independently by each replica.

The base has no public ingress and does not include placeholder Secrets. It runs non-root, uses read-only container filesystems with writable `/tmp`, and has resource limits and HTTP probes. Celery Beat uses one replica with a Recreate strategy. Never autoscale Beat. The gateway HPA needs metrics-server. Internal ingress restrictions require a network plugin that enforces NetworkPolicy; enable that support in your cluster.

## 4. HTTPS ingress

Install the [AWS Load Balancer Controller](https://docs.aws.amazon.com/eks/latest/userguide/lbc-helm.html), including its IAM role/service-account integration. This prerequisite is not provisioned by the application Terraform. Obtain an ACM certificate in the cluster region, choose your webhook hostname, and configure DNS to the controller-created ALB.

Copy `infra/k8s/ingress.example.yaml`, replace the ACM ARN and hostname, then apply it. It exposes only `/webhook/github` on HTTPS; internal administration APIs remain private. Set this exact URL in the GitHub App.

If running on another Kubernetes provider, use its supported HTTPS ingress controller and certificates instead. For initial inspection, use `kubectl port-forward -n pr-reviewer svc/webhook 8101:8000`.

## 5. Verify before enabling publication

- Check every service's readiness and container logs.
- Send a real test PR through the installed App; confirm its webhook receives 202 and the review reaches `dry_run`.
- Confirm OpenAI output, changed-line accuracy, database persistence, and worker recovery.
- Enable `PUBLISH_REVIEWS=true` in the ConfigMap and restart deployments to load the new environment. Push a new test commit.
- Verify the actual GitHub review and merge-learning behavior.
- Configure monitoring for your cluster, secure access to it, and verify any enabled Langfuse traces. Local Compose Grafana credentials are not production credentials.

The Prometheus/Grafana files are tested with Compose. In Kubernetes, use your cluster monitoring stack to scrape service port 8000 at `/metrics`; adapt the NetworkPolicy to admit its namespace. Review status and terminal job failures are available from protected intake APIs.

## Release and cleanup

CI runs formatting, tests, a Docker smoke test, fixture evaluation, Terraform validation, and Kubernetes rendering. A weekly workflow runs the offline fixture evaluation only. Live evaluation is a deliberate local command and consumes API usage.

For shutdown, first remove public ingress/load balancers and wait for their cloud resources to disappear. Preserve any needed reports and database backups. RDS deletion protection and final snapshots are intentionally enabled; removing infrastructure requires an explicit decision to disable protection and choose a unique final snapshot name. Do not run `terraform destroy` as routine troubleshooting.

This is a small-project infrastructure baseline, not a highly available deployment. It has not been load-tested or applied to your AWS account.
