# Running Kuadrant with Rate-limit in AKS

## Pre-requisites

- Kubernetes cluster
- kubectl
- helm
- Model served - check: [vllm-aks-instructions](./vllm-aks-instruction.md)

## Install Kuadrant

https://artifacthub.io/packages/helm/kuadrant/kuadrant-operator

1. Install k8s gateway api

    ```bash
    kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.1.0/standard-install.yaml
    ```

1. Install cert-manager

    ```bash
    helm repo add jetstack https://charts.jetstack.io --force-update
    helm install \
    cert-manager jetstack/cert-manager \
    --namespace cert-manager \
    --create-namespace \
    --version v1.15.3 \
    --set crds.enabled=true
    ```

1. Install Istio (a gateway provider)

    ```bash
    helm install sail-operator \
            --create-namespace \
            --namespace istio-system \
            --wait \
            --timeout=300s \
            https://github.com/istio-ecosystem/sail-operator/releases/download/0.1.0/sail-operator-0.1.0.tgz

    kubectl apply -f -<<<EOF
    apiVersion: sailoperator.io/v1alpha1
    kind: Istio
    metadata:
      name: default
    spec:
      # Supported values for sail-operator v0.1.0 are [v1.22.4,v1.23.0]
      version: v1.23.0
      namespace: istio-system
      # Disable autoscaling to reduce dev resources
      values:
          pilot:
          autoscaleEnabled: false
    EOF
    ```


1. Install Kuadrant

    ```bash
    helm repo add kuadrant https://kuadrant.io/helm-charts/ --force-update
    helm install \
    kuadrant-operator kuadrant/kuadrant-operator \
    --create-namespace \
    --namespace kuadrant-system
    ```

1. Create instance

    ```bash
    kubectl apply -f - <<EOF
    apiVersion: kuadrant.io/v1beta1
    kind: Kuadrant
    metadata:
      name: kuadrant
      namespace: kuadrant-system
    EOF
    ```



## Rate-limiting for LLMs
https://docs.kuadrant.io/latest/kuadrant-operator/doc/user-guides/tokenratelimitpolicy/authenticated-token-ratelimiting-tutorial/

### Create a Gateway

1. Create namespace for gateway:
    ```bash
    export KUADRANT_GATEWAY_NS=gateway-system
    export KUADRANT_GATEWAY_NAME=trlp-tutorial-gateway
    export KUADRANT_SYSTEM_NS=$(kubectl get kuadrant -A -o jsonpath='{.items[0].metadata.namespace}')

    kubectl create ns ${KUADRANT_GATEWAY_NS}
    ```

1. Create a gateway for the LLM:
    ```bash
    kubectl apply -f - <<EOF
    apiVersion: gateway.networking.k8s.io/v1
    kind: Gateway
    metadata:
      name: ${KUADRANT_GATEWAY_NAME}
      namespace: ${KUADRANT_GATEWAY_NS}
    spec:
      gatewayClassName: istio
      listeners:
      - name: http
        protocol: HTTP
        port: 80
        hostname: "trlp-tutorial.example.com"
        allowedRoutes:
          namespaces:
            from: All
    EOF
    ```

1. Expose service via HTTPRoute
    ```bash
    kubectl apply -f - <<EOF
    apiVersion: gateway.networking.k8s.io/v1
    kind: HTTPRoute
    metadata:
      name: trlp-tutorial-llm-sim
    spec:
      hostnames:
        - trlp-tutorial.example.com
      parentRefs:
        - name: ${KUADRANT_GATEWAY_NAME}
        namespace: ${KUADRANT_GATEWAY_NS}
      rules:
        - matches:
            - path:
                type: PathPrefix
                value: "/"
        backendRefs:
            - namespace: vllm
            name: vllm-llama8b
            port: 80
    EOF
    ```

1. Create a ReferenceGrant since the service is in different namespace
    ```bash
    kubectl apply -f - <<EOF
    apiVersion: gateway.networking.k8s.io/v1beta1
    kind: ReferenceGrant
    metadata:
      name: vllm-llama8b
      namespace: vllm
    spec:
      from:
      - group: gateway.networking.k8s.io
        kind: HTTPRoute
        namespace: default
      to:
      - group: ""
        kind: Service
    EOF
    ```

1. Export gateway URL:
    ```bash
    export KUADRANT_INGRESS_HOST=$(kubectl get gtw ${KUADRANT_GATEWAY_NAME} -n ${KUADRANT_GATEWAY_NS} -o jsonpath='{.status.addresses[0].value}')
    export KUADRANT_INGRESS_PORT=$(kubectl get gtw ${KUADRANT_GATEWAY_NAME} -n ${KUADRANT_GATEWAY_NS} -o jsonpath='{.spec.listeners[?(@.name=="http")].port}')
    export KUADRANT_GATEWAY_URL=${KUADRANT_INGRESS_HOST}:${KUADRANT_INGRESS_PORT}
    ```

1. Test connectivity
    ```bash
    curl -H 'Host: trlp-tutorial.example.com' http://$KUADRANT_GATEWAY_URL/v1/models -i
    ```
    > **Note** if command above fails, try with port forward to access the gateway
    ```bash
    kubectl port-forward -n ${KUADRANT_GATEWAY_NS} service/${KUADRANT_GATEWAY_NAME}-istio 9080:80 >/dev/null 2>&1 &
    export KUADRANT_GATEWAY_URL=localhost:9080
    ```

### Configure API Keys and rate-limits

1. Create two tiers: free and gold

    ```bash
    # Create a free tier user
    kubectl apply -f - <<EOF
    apiVersion: v1
    kind: Secret
    metadata:
      name: trlp-tutorial-api-key-free-user-1
      namespace: ${KUADRANT_SYSTEM_NS}
      labels:
        authorino.kuadrant.io/managed-by: authorino
        app: my-llm
      annotations:
        kuadrant.io/groups: free
        secret.kuadrant.io/user-id: user-1
    stringData:
      api_key: iamafreeuser
    type: Opaque
    EOF
    ```

    ```bash
    # Create a gold tier user
    kubectl apply -f - <<EOF
    apiVersion: v1
    kind: Secret
    metadata:
      name: trlp-tutorial-api-key-gold-user-1
      namespace: ${KUADRANT_SYSTEM_NS}
      labels:
        authorino.kuadrant.io/managed-by: authorino
        app: my-llm
      annotations:
        kuadrant.io/groups: gold
        secret.kuadrant.io/user-id: user-2
    stringData:
      api_key: iamagolduser
    type: Opaque
    EOF
    ```
1. Configure auth policy

    ```bash
    kubectl apply -f - <<EOF
    apiVersion: kuadrant.io/v1
    kind: AuthPolicy
    metadata:
      name: trlp-tutorial-llm-api-keys
      namespace: ${KUADRANT_GATEWAY_NS}
    spec:
      targetRef:
        group: gateway.networking.k8s.io
        kind: Gateway
        name: ${KUADRANT_GATEWAY_NAME}
      rules:
        authentication:
        api-key-users:
            apiKey:
            selector:
                matchLabels:
                app: my-llm
            credentials:
            authorizationHeader:
                prefix: APIKEY
        response:
        success:
            filters:
            identity:
                json:
                properties:
                    groups:
                    selector: auth.identity.metadata.annotations.kuadrant\.io/groups
                    userid:
                    selector: auth.identity.metadata.annotations.secret\.kuadrant\.io/user-id
        authorization:
        allow-groups:
            opa:
            rego: |
                groups := split(object.get(input.auth.identity.metadata.annotations, "kuadrant.io/groups", ""), ",")
                allow { groups[_] == "free" }
                allow { groups[_] == "gold" }
    EOF
    ```

1. Apply token rate limiting

    ```bash
    kubectl apply -f - <<EOF
    apiVersion: kuadrant.io/v1alpha1
    kind: TokenRateLimitPolicy
    metadata:
      name: trlp-tutorial-token-limits
      namespace: ${KUADRANT_GATEWAY_NS}
    spec:
      targetRef:
        group: gateway.networking.k8s.io
        kind: Gateway
        name: ${KUADRANT_GATEWAY_NAME}
      limits:
        free:
        rates:

            - limit: 50 # 50 tokens per minute for free users (small for testing)
            window: 1m
        when:
            - predicate: request.path == "/v1/chat/completions"
            - predicate: |
                auth.identity.groups.split(",").exists(g, g == "free")
        counters:
            - expression: auth.identity.userid
        gold:
        rates:
            - limit: 200 # 200 tokens per minute for gold users (small for testing)
            window: 1m
        when:
            - predicate: request.path == "/v1/chat/completions"
            - predicate: |
                auth.identity.groups.split(",").exists(g, g == "gold")
        counters:
            - expression: auth.identity.userid
    EOF
    ```

### Test token count and rate-limits

1. Test with free user (non-streaming)

    Make a chat completion request. Note that stream: false is explicitly set to ensure a non-streaming response:

    ```bash
    curl -H 'Host: trlp-tutorial.example.com' \
        -H 'Authorization: APIKEY iamafreeuser' \
        -H 'Content-Type: application/json' \
        -X POST http://$KUADRANT_GATEWAY_URL/v1/chat/completions \
        -d '{
            "model": "meta-llama/Llama-3.1-8B-Instruct",
            "messages": [
                { "role": "user", "content": "What is Kubernetes?" }
            ],
            "max_tokens": 100,
            "stream": false,
            "usage": true
            }'
    ```

    Notice how the response includes token usage:

    ```console
    {
        "choices": [...],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 95,
            "total_tokens": 100
        }
    }
    ```


1. Test with free user (streaming)

    Make a chat completion request with streaming enabled. Ensure the request includes "stream": true and "stream_options": { "include_usage": true } so that usage is emitted at the end of the stream and can be enforced by the policy:

    ```bash
    curl -H 'Host: trlp-tutorial.example.com' \
     -H 'Authorization: APIKEY iamafreeuser' \
     -H 'Content-Type: application/json' \
     -X POST http://$KUADRANT_GATEWAY_URL/v1/chat/completions \
     -d '{
           "model": "meta-llama/Llama-3.1-8B-Instruct",
           "messages": [
             { "role": "user", "content": "What is Kubernetes?" }
           ],
           "max_tokens": 100,
           "stream": true,
           "stream_options": {
             "include_usage": true
           }
         }'
    ```

    > Note: If *stream_options.include_usage* is omitted when *stream: true*, Kuadrant cannot extract token usage from the stream. Depending on the policy *failureMode*, the request may either be allowed without limiting or rejected.

1. Test with gold user

    ```bash
    curl -H 'Host: trlp-tutorial.example.com' \
     -H 'Authorization: APIKEY iamagolduser' \
     -H 'Content-Type: application/json' \
     -X POST http://$KUADRANT_GATEWAY_URL/v1/chat/completions \
     -d '{
           "model": "meta-llama/Llama-3.1-8B-Instruct",
           "messages": [
             { "role": "user", "content": "Explain cloud native architecture" }
           ],
           "max_tokens": 200,
           "stream": false,
           "usage": true
         }'
    ```