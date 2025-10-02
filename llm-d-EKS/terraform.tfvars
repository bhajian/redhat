region          = "us-east-1"
cluster_name    = "eks-gpu-prod"
cluster_version = "1.33"

vpc_id = "vpc-0c5b87e00f328a749"

private_subnet_ids = [
  "subnet-019932a6fa140b2e8",
  "subnet-0b6cc122738ebdaf5",
  "subnet-0c9644ba720873e29",
]

public_subnet_ids = [
  "subnet-06bcdfa0f633356f5",
  "subnet-0771055baa3560d70",
  "subnet-0236bf8e61a22de72",
]

admin_role_arn = "arn:aws:iam::256274107934:role/YourEKSAdminRole"

cpu_instance_type = "m6i.large"
cpu_desired = 2
cpu_min     = 2
cpu_max     = 5

enable_gpu_node_group = false
gpu_instance_type     = "g5.xlarge"
gpu_desired           = 1
gpu_min               = 0
gpu_max               = 3
