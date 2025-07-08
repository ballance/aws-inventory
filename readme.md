# AWS Inventory Visualizer

This repository provides tools to:
1. **Collect AWS infrastructure data** using the AWS CLI (`inventory.sh`)
2. **Generate network topology diagrams** from the collected data (`diagram.py`)

---

## 🔧 Requirements

### AWS CLI
Ensure you're authenticated and have the necessary IAM permissions:
- `ec2:Describe*`
- `rds:DescribeDBInstances`
- `ecs:List*`, `ecs:Describe*`
- `elbv2:Describe*`
- `iam:List*`
- `lambda:ListFunctions`
- `apigateway:GetRestApis`
- `cloudfront:ListDistributions`
- `s3:ListAllMyBuckets`

Install AWS CLI:  
```sh
brew install awscli   # macOS
sudo apt install awscli  # Ubuntu/Debian
```

Install necessary Python modules:
```
python3 -m pip install matplotlib networkx

