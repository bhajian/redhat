# llm-d on Azure Kubernetes Service (AKS)

This document covers configuring AKS cluster for running high performance LLM inference with llm-d.

## Prerequisites

llm-d on AKS is tested with the following configurations:

* GPU types: NVIDIA H100, NVIDIA A10
* Versions: AKS v1.32.7
* Networking:

## Cluster Configuration

The AKS cluster should be configured with the following settings:

* GPU-enabled node pools with at least 2 GPU nodes
* Azure CNI networking
* kubectl configured for cluster access

## Quick Start

### Client Prerequisites

[Setup client tools and HF token](https://github.com/llm-d/llm-d/blob/main/guides/prereq/client-setup/README.md)

### Step 1: Install Prerequisites

Before deploying llm-d workloads, install the required components:

```bash
# Navigate to gateway provider prerequisites
cd guides/prereq/gateway-provider

# Install Gateway API and Inference Extension CRDs
./install-gateway-provider-dependencies.sh

# Install Istio control plane
helmfile apply -f istio.helmfile.yaml
```

### Step 2: Cluster Validation

Verify your cluster setup:

```bash
# Verify cluster access and GPU nodes
kubectl cluster-info
kubectl get nodes -l nvidia.com/gpu.present=true

# Verify components are ready
kubectl get pods -n istio-system
```

### Step 3: Deploy Workloads

Use the `default` environment 

```bash
# For inference scheduling (2 decode pods)
cd guides/inference-scheduling
export NAMESPACE=llm-d-inference-scheduling
helmfile apply -e default -n ${NAMESPACE}
```

**Architecture Overview:**

- **Inference Scheduling**: 2 decode pods with intelligent routing via InferencePool

### Step 4: Testing

Verify deployment success:

```bash
# Check deployment status for inference scheduling
kubectl get pods -n llm-d-inference-scheduling
kubectl get gateway -n llm-d-inference-scheduling

# Test inference endpoint (inference scheduling example)
kubectl port-forward -n llm-d-inference-scheduling svc/infra-inference-scheduling-inference-gateway-istio 8080:80

curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen3-0.6B", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 20}'
```

## Monitoring (Optional)
Deploy Prometheus and Grafana for observability:

```bash
./docs/monitoring/scripts/install-prometheus-grafana.sh

# Access Grafana dashboard
kubectl -n llm-d-monitoring port-forward svc/prometheus-llm-d-monitoring-grafana 3000:80

# Access Prometheus dashboard
kubectl -n llm-d-monitoring port-forward svc/prometheus-llm-d-monitorin-prometheus 9090:9090
```

We recommend enabling the monitoring stack to track:
- GPU utilization per deployment
- Inference request latency and throughput
- Memory usage and KV cache efficiency
- Network performance between inference pods

## AKS-Specific Configuration Details

### GPU Node Configuration

Use these taints on the GPU nodes to prevent non-GPU workloads from scheduling. The decode pods will have relevant toleration to these taints:

```yaml
tolerations:
- key: "nvidia.com/gpu"
  operator: "Exists"
  effect: "NoSchedule"
```

## Troubleshooting

### Common Issues

#### 1. Routing errors in Istio Pod During Testing

**Error**: `404 NR route_not_found`

**Cause**: Required Route CRDs not installed before deployment

**Solution**: Install CRDs before any helmfile deployment:
```bash
kubectl apply -f ./guides/inference-scheduling/httproute.yaml -n llm-d-inference-scheduling
```

#### 2. OOM Errors on Decode pods

**Error**: `Free memory on device on startup is less than desired GPU memory utilization`

**Cause**: Memory utilization of vLLM serve is higher than the GPU can support

**Solution**: Reduce the vLLM serve `--gpu-memory-utilization` that the GPU can support

## Cleanup

```bash
# Remove specific deployment
export NAMESPACE=llm-d-inference-scheduling
helmfile destroy -e default -n ${NAMESPACE}

# Remove prerequisites (affects all deployments)
cd guides/prereq/gateway-provider
helmfile destroy -f istio.helmfile.yaml
./install-gateway-provider-dependencies.sh delete
```
