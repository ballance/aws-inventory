#!/bin/bash

AWS_REGION="${AWS_REGION:-us-east-1}"
DATE=$(date +%Y%m%d_%H%M%S)
OUT_DIR="aws-inventory-$DATE"
mkdir -p "$OUT_DIR"

echo "Saving AWS inventory to $OUT_DIR"

echo "Getting EC2 instances..."
aws ec2 describe-instances --region "$AWS_REGION" > "$OUT_DIR/ec2-instances.json"

echo "Getting VPCs..."
aws ec2 describe-vpcs --region "$AWS_REGION" > "$OUT_DIR/vpcs.json"

echo "Getting Subnets..."
aws ec2 describe-subnets --region "$AWS_REGION" > "$OUT_DIR/subnets.json"

echo "Getting Security Groups..."
aws ec2 describe-security-groups --region "$AWS_REGION" > "$OUT_DIR/security-groups.json"

echo "Getting Load Balancers..."
aws elbv2 describe-load-balancers --region "$AWS_REGION" > "$OUT_DIR/load-balancers.json"

echo "Getting Target Groups..."
aws elbv2 describe-target-groups --region "$AWS_REGION" > "$OUT_DIR/target-groups.json"

echo "Getting RDS Instances..."
aws rds describe-db-instances --region "$AWS_REGION" > "$OUT_DIR/rds-instances.json"

echo "Getting S3 Buckets..."
aws s3api list-buckets > "$OUT_DIR/s3-buckets.json"

echo "Getting Lambda functions..."
aws lambda list-functions --region "$AWS_REGION" > "$OUT_DIR/lambda-functions.json"

echo "Getting IAM roles..."
aws iam list-roles > "$OUT_DIR/iam-roles.json"

echo "Getting IAM users..."
aws iam list-users > "$OUT_DIR/iam-users.json"

echo "Getting API Gateways..."
aws apigateway get-rest-apis --region "$AWS_REGION" > "$OUT_DIR/api-gateways.json"

echo "Getting CloudFront distributions..."
aws cloudfront list-distributions > "$OUT_DIR/cloudfront-distributions.json"

echo "Getting ECS clusters..."
aws ecs list-clusters --region "$AWS_REGION" > "$OUT_DIR/ecs-clusters.json"

echo "Getting EKS clusters..."
aws eks list-clusters --region "$AWS_REGION" > "$OUT_DIR/eks-clusters.json"

CLUSTERS=$(aws ecs list-clusters --region "$AWS_REGION" --query "clusterArns[]" --output text)
OUT_SVC_FILE="$OUT_DIR/ecs-services.json"
echo '{"services":[]}' > "$OUT_SVC_FILE"

for CLUSTER_ARN in $CLUSTERS; do
  CLUSTER_NAME=$(basename "$CLUSTER_ARN")
  echo "Getting services for cluster: $CLUSTER_NAME"

  SERVICE_ARNS=$(aws ecs list-services \
    --cluster "$CLUSTER_ARN" \
    --region "$AWS_REGION" \
    --query "serviceArns[]" \
    --output text)

  if [ -z "$SERVICE_ARNS" ]; then
    echo "No services in $CLUSTER_NAME"
    continue
  fi

  echo "$SERVICE_ARNS" | xargs -n 10 | while read -r CHUNK; do
    jq -s 'reduce .[] as $item ({"services":[]}; .services += $item.services)' \
      "$OUT_SVC_FILE" \
      <(aws ecs describe-services \
        --cluster "$CLUSTER_ARN" \
        --services $CHUNK \
        --region "$AWS_REGION" \
        --query '{services: services}' \
        --output json) > tmp.json && mv tmp.json "$OUT_SVC_FILE"
  done
done

echo "ECS Services Done. Output written to $OUT_SVC_FILE"
echo "Inventory complete. Output saved to $OUT_DIR"
