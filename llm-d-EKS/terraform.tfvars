region          = "us-east-1"
cluster_name    = "eks-gpu-prod"
cluster_version = "1.30"

vpc_id = "vpc-0c5b87e00f328a749"

# Private (workers)
private_subnet_ids = [
  "subnet-019932a6fa140b2e8", # vpc2-subnet-private1-us-east-1f
  "subnet-0b6cc122738ebdaf5", # vpc2-subnet-private2-us-east-1e
  "subnet-0c9644ba720873e29", # vpc2-subnet-private3-us-east-1d
]

# Public (internet-facing LBs)
public_subnet_ids = [
  "subnet-06bcdfa0f633356f5", # vpc2-subnet-public1-us-east-1f
  "subnet-0771055baa3560d70", # vpc2-subnet-public2-us-east-1e
  "subnet-0236bf8e61a22de72", # vpc2-subnet-public3-us-east-1d
]

# Your IAM admin role (replace with your real one)
admin_role_arn = "arn:aws:iam::256274107934:role/YourEKSAdminRole"

# Node groups
cpu_instance_type = "m6i.large"
cpu_desired       = 2
cpu_min           = 2
cpu_max           = 5

# GPU (toggle later by setting enable_gpu_node_group = true)
enable_gpu_node_group = false
gpu_instance_type     = "g5.xlarge"
gpu_desired           = 1
gpu_min               = 0
gpu_max               = 3
