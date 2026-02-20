# --- EKS Test Cluster Secondary (For Multi-Region Testing) ---
# WARNING: EKS Control Plane costs $0.10/hour (~$2.40/day), 
# which exceeds the $2.00/day budget. Delete this cluster when not testing.

resource "aws_iam_role" "test_cluster_secondary" {
  name = "${local.name_prefix}-test-cluster-role-us-east-1"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "eks.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "test_cluster_policy_secondary" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.test_cluster_secondary.name
}

resource "aws_eks_cluster" "test_secondary" {
  provider = aws.secondary

  name     = "${local.name_prefix}-test-cluster-us-east-1"
  role_arn = aws_iam_role.test_cluster_secondary.arn
  version  = "1.34"

  vpc_config {
    subnet_ids              = var.secondary_public_subnet_ids
    endpoint_public_access  = true
    endpoint_private_access = false
  }

  depends_on = [aws_iam_role_policy_attachment.test_cluster_policy_secondary]

  tags = merge(local.common_tags, {
    auto_stop = "true"
  })
}

# --- Node Role ---

resource "aws_iam_role" "test_nodes_secondary" {
  name = "${local.name_prefix}-test-node-role-us-east-1"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "test_nodes_worker_secondary" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.test_nodes_secondary.name
}

resource "aws_iam_role_policy_attachment" "test_nodes_cni_secondary" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.test_nodes_secondary.name
}

resource "aws_iam_role_policy_attachment" "test_nodes_ecr_secondary" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.test_nodes_secondary.name
}

# --- Managed Node Group ---

resource "aws_eks_node_group" "test_secondary" {
  provider = aws.secondary

  cluster_name    = aws_eks_cluster.test_secondary.name
  node_group_name = "${local.name_prefix}-test-node-group-us-east-1"
  node_role_arn   = aws_iam_role.test_nodes_secondary.arn
  subnet_ids      = var.secondary_public_subnet_ids

  scaling_config {
    desired_size = 1
    max_size     = 1
    min_size     = 1
  }

  instance_types = ["t3.small"]

  # Ensure that IAM Role permissions are created before and deleted after EKS Node Group handling.
  # Otherwise, EKS will not be able to properly delete EC2 Instances and Elastic Network Interfaces.
  depends_on = [
    aws_iam_role_policy_attachment.test_nodes_worker_secondary,
    aws_iam_role_policy_attachment.test_nodes_cni_secondary,
    aws_iam_role_policy_attachment.test_nodes_ecr_secondary,
  ]

  tags = local.common_tags
}
