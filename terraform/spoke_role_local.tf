# --- Local Spoke Role (Allows hub to manage this account) ---

resource "aws_iam_role" "local_spoke" {
  name = "eks-operator-spoke"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = [
            module.iam.hub_role_arn,
            module.iam.lambda_worker_role_arn,
            module.iam.lambda_scheduler_role_arn,
            "arn:aws:iam::123456789012:root" # Generic root access for placeholder
          ]
        }
        Condition = {
          StringEquals = {
            "sts:ExternalId" = var.external_id
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "local_spoke_policy" {
  name = "eks-operator-spoke-policy"
  role = aws_iam_role.local_spoke.id

  policy = jsonencode({
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
      },
      {
        Sid    = "LambdaRead"
        Effect = "Allow"
        Action = [
          "lambda:ListFunctions",
          "lambda:ListTags",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration"
        ]
        Resource = "*"
      },
      {
        Sid    = "ECSRead"
        Effect = "Allow"
        Action = [
          "ecs:ListClusters",
          "ecs:DescribeClusters",
          "ecs:ListServices",
          "ecs:DescribeServices"
        ]
        Resource = "*"
      }
    ]
  })
}
