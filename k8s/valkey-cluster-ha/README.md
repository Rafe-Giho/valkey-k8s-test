# Valkey Cluster HA on Kubernetes

This folder contains raw manifests for a Valkey Cluster deployment with high availability.

What this gives you:
- 6 Valkey Pods
- 3 primary nodes and 3 replica nodes after bootstrap
- Persistent volumes for every node
- Cluster bootstrap Job
- Headless service for node-to-node discovery

Important behavior:
- Clients must be cluster-aware.
- Read-write traffic uses the normal cluster client.
- Read-only traffic uses the same cluster but the client must enable replica reads (`READONLY`, `readFromReplicas`, or the library equivalent).
- A plain single Service is only a seed endpoint, not the full routing layer.
- This manifest assumes clients run inside the cluster and can resolve Kubernetes service and pod DNS names.

Before applying:
- Change the password in `secret.yaml`
- Adjust `storageClassName` and PVC size in `statefulset.yaml`
- Make sure your client supports Valkey Cluster

Apply:

```powershell
kubectl apply -k .\k8s\valkey-cluster-ha
```

Useful endpoints:
- Seed service: `valkey-cluster.valkey-cluster-ha.svc.cluster.local:6379`
- Headless node discovery: `valkey-cluster-headless.valkey-cluster-ha.svc.cluster.local`
