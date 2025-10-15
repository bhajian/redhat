# Model-as-a-Service on GKE with Argo CD, vLLM, Gateway API Inference Extension, and LiteLLM

This repo lets you deploy any model by dropping a single YAML file in `models/`.
Each file becomes a fully working namespace with:
- vLLM server(s)
- Gateway API InferenceExtension InferencePool + external HTTP Gateway
- LiteLLM sitting in front for token counting, rate limiting, etc.

## Prereqs

- GKE cluster with GPU node pool (NVIDIA drivers + runtime).
- Argo CD installed on the cluster and pointed at this repo.
- Gateway API (standard) enabled on GKE (Regional External Managed).
- Argo CD Helm OCI enabled (see `apps/argocd-cm.yaml`).

## Quick start

1. **Install Kustomize (optional, for local render/checks):**
   - macOS: `brew install kustomize`
   - Linux:
     ```bash
     curl -sSL "https://github.com/kubernetes-sigs/kustomize/releases/latest/download/kustomize_$(uname -s | tr '[:upper:]' '[:lower:]')_amd64.tar.gz" \
     | tar xz && sudo mv kustomize /usr/local/bin/
     ```

2. **Register repo in Argo CD** and apply the “ApplicationSet”:
   ```bash
   # If not already:
   argocd repo add https://github.com/<you>/model-as-a-service.git

   # Create/patch Argo CD config to enable Helm OCI:
   kubectl apply -n argocd -f apps/argocd-cm.yaml

   # Create ApplicationSet so every file under models/ becomes an app:
   kubectl apply -n argocd -f apps/applicationset-models.yaml
