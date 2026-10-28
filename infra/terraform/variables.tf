variable "region" {
  type    = string
  default = "us-east-1"
}
variable "name" {
  type    = string
  default = "pr-reviewer"
}
variable "kubernetes_version" {
  description = "Choose an EKS version in standard support in your selected region."
  type        = string
}
variable "admin_cidrs" {
  description = "Public IP CIDRs allowed to reach the Kubernetes API, e.g. your current public IP /32."
  type        = list(string)
  validation {
    condition     = length(var.admin_cidrs) > 0 && !contains(var.admin_cidrs, "0.0.0.0/0")
    error_message = "Supply restricted admin CIDRs; do not expose the Kubernetes API globally."
  }
}
variable "admin_role_arn" {
  description = "Existing IAM role that will administer this cluster."
  type        = string
}
