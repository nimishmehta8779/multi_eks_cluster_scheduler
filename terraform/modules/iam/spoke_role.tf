# --- Spoke Role (output JSON only — deployed via CloudFormation StackSets) ---

locals {
  spoke_role_trust_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.management_account_id}:role/${var.name_prefix}-hub"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = var.external_id
          }
        }
      }
    ]
  }

  spoke_role_permissions = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EKSReadWrite"
        Effect = "Allow"
        Action = [
          "eks:ListClusters",
          "eks:DescribeCluster",
          "eks:ListNodegroups",
          "eks:DescribeNodegroup",
          "eks:UpdateNodegroupConfig"
        ]
        Resource = "*"
      },
      {
        Sid    = "AutoScalingReadWrite"
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances",
          "autoscaling:DescribeLaunchConfigurations",
          "autoscaling:DescribeTags",
          "autoscaling:UpdateAutoScalingGroup",
          "autoscaling:SetDesiredCapacity",
          "autoscaling:CreateOrUpdateTags"
        ]
        Resource = "*"
      },
      {
        Sid    = "EC2Describe"
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeLaunchTemplateVersions"
        ]
        Resource = "*"
      }
    ]
  }
}
