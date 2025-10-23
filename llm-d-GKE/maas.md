


```
echo "Waiting for the Gateway IP address..."
IP=""
while [ -z "$IP" ]; do
  IP=$(kubectl get gateway inference-gateway -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)
  if [ -z "$IP" ]; then
    echo "Gateway IP not found, waiting 10 seconds..."
    sleep 10
  fi
done
echo "Gateway IP address is: $IP"
export GATEWAY_IP=$IP

curl http://$KUADRANT_GATEWAY_URL/v1/chat/completions \
-H 'Host: trlp-tutorial.example.com' \
-H "Content-Type: application/json" \
-H 'Authorization: APIKEY iamafreeuser' \
-d '{
    "model": "llama3-8b",
    "prompt": "The capital of Canada is",
    "max_tokens": 50,
    "temperature": 0
}'
```