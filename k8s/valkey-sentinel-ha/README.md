# Valkey Sentinel HA on Kubernetes

This folder contains raw manifests for a Valkey primary-replica deployment with Sentinel-based high availability.

What this gives you:
- 3 Valkey Pods with one primary and two replicas
- 3 Sentinel Pods for automatic failover
- Persistent volumes for Valkey data
- Persistent volumes for Sentinel state
- A headless service for node-to-node communication
- A Sentinel service for clients that discover the current primary

Important behavior:
- Write traffic should go through a Sentinel-aware client.
- Read-only traffic should use Sentinel to discover replicas.
- A plain Kubernetes Service cannot automatically follow primary role changes without an extra controller or proxy.
- This manifest assumes clients run inside the cluster and can resolve Kubernetes service and pod DNS names.

Before applying:
- Change the password in `secret.yaml`
- Adjust `storageClassName` and PVC size in `statefulset-valkey.yaml`
- Make sure your client supports Sentinel

Apply:

```powershell
kubectl apply -k .\k8s\valkey-sentinel-ha
```

Useful endpoints:
- Sentinel discovery: `valkey-sentinel.valkey-sentinel-ha.svc.cluster.local:26379`
- Valkey nodes: `valkey-nodes.valkey-sentinel-ha.svc.cluster.local`
- Master name: `mymaster`
