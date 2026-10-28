output "cluster_name" { value = module.eks.cluster_name }
output "repository_url" { value = aws_ecr_repository.main.repository_url }
output "reports_bucket" { value = aws_s3_bucket.reports.bucket }
output "database_url" {
  value     = "postgresql+psycopg://reviewer:${random_password.database.result}@${aws_db_instance.main.address}:5432/reviewer?sslmode=require"
  sensitive = true
}
output "redis_url" {
  value     = "rediss://:${random_password.redis.result}@${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0?ssl_cert_reqs=required"
  sensitive = true
}
