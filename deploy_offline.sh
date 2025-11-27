#!/bin/bash

set -e
set -o pipefail

APP_DIR="/Users/pierrepoignant/Coding/offline"
KUBE_DIR="/Users/pierrepoignant/Coding/kubernetes"
IMAGE="8ie06lx5.c1.gra9.container-registry.ovh.net/offline/offline-app:latest"
KUBECONFIG_PATH="$KUBE_DIR/kubeconfig.yml"
NAMESPACE="essorcloud"
K8S_FILES="$APP_DIR/k8s"

# Function to wait for a deployment to be ready
wait_for_deployment() {
    local deployment_name=$1
    local app_label=$2
    
    echo "⏳ Waiting for $deployment_name to be ready..."
    
    timeout=120  # seconds
    interval=5
    elapsed=0
    
    while true; do
        pod_status=$(kubectl get pods -n "$NAMESPACE" -l app="$app_label" -o jsonpath="{.items[0].status.containerStatuses[0].ready}" 2>/dev/null || echo "false")
        
        if [ "$pod_status" == "true" ]; then
            echo "✅ $deployment_name is up and running!"
            break
        fi
        
        if [ "$elapsed" -ge "$timeout" ]; then
            echo "❌ Timed out waiting for $deployment_name to be ready"
            kubectl get pods -n "$NAMESPACE" -l app="$app_label"
            exit 1
        fi
        
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
}

echo "➡️  Building Docker image..."
cd "$APP_DIR"
docker buildx build --platform linux/amd64 -t "$IMAGE" .

echo "➡️  Pushing Docker image..."
docker push "$IMAGE"

echo "➡️  Setting kubeconfig..."
export KUBECONFIG="$KUBECONFIG_PATH"

echo "➡️  Deleting old deployment (if any)..."
kubectl delete deployment offline-app -n "$NAMESPACE" --ignore-not-found

echo "➡️  Applying new deployment..."
kubectl apply -f "$K8S_FILES/configmap.yaml" -n "$NAMESPACE"
kubectl apply -f "$K8S_FILES/secret.yaml" -n "$NAMESPACE"
kubectl apply -f "$K8S_FILES/deployment.yaml" -n "$NAMESPACE"
kubectl apply -f "$K8S_FILES/service.yaml" -n "$NAMESPACE"
kubectl apply -f "$K8S_FILES/ingress.yaml" -n "$NAMESPACE" 2>/dev/null || echo "⚠️  Ingress skipped (optional)"

# Wait for deployment to be ready
wait_for_deployment "offline-app" "offline-app"

echo ""
echo "✅ Deployment completed!"
echo ""
echo "📊 Services:"
kubectl get services -n "$NAMESPACE"
echo ""
echo "🚀 Pods:"
kubectl get pods -n "$NAMESPACE" -l app=offline-app
echo ""
echo "💡 Access your app:"
echo "   - Flask App: Port 5000"

