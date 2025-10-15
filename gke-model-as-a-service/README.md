# Model-as-a-Service on GKE with Argo CD, Kustomize/Helm, vLLM, Gateway Inference Extension, and LiteLLM

**What you get**  
Drop a file into `models/` (e.g., `llama-3_2-8b.yaml`) and Argo CD will:

1. Create a *new namespace* for that model  
2. **Copy your HF token** from the `default` namespace into the new namespace (automated)  
3. Deploy **vLLM** (GPU-ready) labeled for the InferencePool  
4. Install the **Gateway API – Inference Extension** *InferencePool* OCI chart to balance endpoints  
5. Create an external **HTTP Gateway**  
6. Deploy **LiteLLM** in front of the Gateway for token counting, rate limiting, etc.

---

## Prerequisites

- **GKE cluster** with a **GPU node pool** (NVIDIA drivers/runtime installed)
- **kubectl** access to the cluster
- **Argo CD** installed on the cluster + **argocd** CLI on your laptop
- (Optional) **kustomize** locally for render checks

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
