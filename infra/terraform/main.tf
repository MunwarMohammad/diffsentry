data "aws_availability_zones" "available" {
  state = "available"
}
data "aws_caller_identity" "current" {}
module "vpc" {
  source               = "terraform-aws-modules/vpc/aws"
  version              = "6.0.1"
  name                 = var.name
  cidr                 = "10.42.0.0/16"
  azs                  = slice(data.aws_availability_zones.available.names, 0, 2)
  private_subnets      = ["10.42.1.0/24", "10.42.2.0/24"]
  public_subnets       = ["10.42.101.0/24", "10.42.102.0/24"]
  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true
  public_subnet_tags   = { "kubernetes.io/role/elb" = "1" }
  private_subnet_tags  = { "kubernetes.io/role/internal-elb" = "1" }
}
module "eks" {
  source                                   = "terraform-aws-modules/eks/aws"
  version                                  = "21.20.0"
  name                                     = var.name
  kubernetes_version                       = var.kubernetes_version
  vpc_id                                   = module.vpc.vpc_id
  subnet_ids                               = module.vpc.private_subnets
  endpoint_private_access                  = true
  endpoint_public_access                   = true
  endpoint_public_access_cidrs             = var.admin_cidrs
  enable_cluster_creator_admin_permissions = false
  access_entries = {
    administrator = {
      principal_arn = var.admin_role_arn
      policy_associations = {
        admin = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }
  addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni    = { before_compute = true }
  }
  eks_managed_node_groups = {
    application = {
      instance_types = ["t3.medium"]
      min_size       = 2
      max_size       = 4
      desired_size   = 2
    }
  }
}
resource "aws_security_group" "data" {
  name_prefix = "${var.name}-data-"
  vpc_id      = module.vpc.vpc_id
}
resource "aws_vpc_security_group_ingress_rule" "postgres" {
  security_group_id            = aws_security_group.data.id
  referenced_security_group_id = module.eks.node_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}
resource "aws_vpc_security_group_ingress_rule" "redis" {
  security_group_id            = aws_security_group.data.id
  referenced_security_group_id = module.eks.node_security_group_id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
}
resource "random_password" "database" {
  length  = 40
  special = false
}
resource "random_password" "redis" {
  length  = 40
  special = false
}
resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = module.vpc.private_subnets
}
resource "aws_db_instance" "main" {
  identifier                = var.name
  engine                    = "postgres"
  engine_version            = "16"
  instance_class            = "db.t4g.micro"
  allocated_storage         = 20
  max_allocated_storage     = 100
  storage_encrypted         = true
  db_name                   = "reviewer"
  username                  = "reviewer"
  password                  = random_password.database.result
  db_subnet_group_name      = aws_db_subnet_group.main.name
  vpc_security_group_ids    = [aws_security_group.data.id]
  publicly_accessible       = false
  backup_retention_period   = 7
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name}-final"
}
resource "aws_elasticache_subnet_group" "main" {
  name       = var.name
  subnet_ids = module.vpc.private_subnets
}
resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = var.name
  description                = "PR reviewer broker"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.t4g.micro"
  num_cache_clusters         = 1
  port                       = 6379
  parameter_group_name       = "default.redis7"
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.data.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.redis.result
  snapshot_retention_limit   = 3
}
resource "aws_ecr_repository" "main" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}
resource "aws_s3_bucket" "reports" {
  bucket = "${var.name}-reports-${data.aws_caller_identity.current.account_id}-${var.region}"
}
resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration { status = "Enabled" }
}
