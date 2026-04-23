# CADQ: Chaos-Aware Dynamic Quarantine Controller

An automated, self-healing Kubernetes security controller written in Python. CADQ continuously monitors the cluster state and dynamically applies zero-trust network policies to quarantine compromised or chaotic microservices in real-time, preventing lateral movement and cascading network failures.

## Key Features
* **Real-Time CRD Monitoring:** Utilizes the Kubernetes Custom Objects API to detect active Chaos Mesh experiments (`NetworkChaos`) on the fly.
* **Automated Network Isolation:** Dynamically injects a "Deny All Egress" `NetworkPolicy` to instantly lock down targeted pods (e.g., the frontend) when anomalies are detected.
* **Self-Healing Reconciliation:** Acts as a true Kubernetes Operator loop; once the chaos/threat subsides, it automatically lifts the quarantine and restores normal operations.
* **Performance Telemetry:** Calculates and logs the exact Time-To-Quarantine (TTQ) in milliseconds to measure automated security response times.

## Tech Stack & Infrastructure
* **Language:** Python 3
* **Libraries:** Official Kubernetes Python Client (`kubernetes`)
* **Infrastructure:** Minikube (Local K8s)
* **Networking (CNI):** Calico (Required for enforcing `NetworkPolicy`)
* **Chaos Engineering:** Chaos Mesh
* **Target Application:** Google Cloud Microservices Demo

## Technical Highlights
This project demonstrates strong Cloud-Native and DevOps engineering principles:
1. **Kubernetes API Mastery:** Bypasses basic `kubectl` commands by programmatically interacting with the K8s API using `NetworkingV1Api` and `CustomObjectsApi`.
2. **The Reconciliation Loop:** Implements the core architectural pattern of Kubernetes (Observe -> Analyze -> Act). The `while True` loop continuously reconciles the desired state (quarantine or normal) based on the presence of Chaos Mesh CRDs.
3. **Zero-Trust Network Security:** Enforces least-privilege networking by omitting the egress array in the injected `NetworkPolicy`, creating an explicit "Deny All" ruleset that overrides default permissive networking.

## Getting Started (Reproduction Steps)

### First-Time Setup
1. **Spin up a Calico-enabled Cluster:**
   ```bash
   minikube start --cpus=4 --memory=6144 --network-plugin=cni --cni=calico
2. **Deploy the Target Application:**
   ```bash
   kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/main/release/kubernetes-manifests.yaml
    kubectl get pods -w
3. **Install Chaos Mesh via Helm:**
   ```bash
   helm repo add chaos-mesh https://charts.chaos-mesh.org
   helm repo update
   helm install chaos-mesh chaos-mesh/chaos-mesh -n=chaos-mesh --create-namespace
4. **Deploy the "Hacker" Pod (for testing lateral movement):**
   ```bash
   kubectl run hacker --image=alpine --labels="app=frontend" -- sleep infinity
   kubectl exec -it hacker -- apk add curl
5. **Install Python Dependencies:**
   ```bash
   pip install kubernetes

### Execution & Testing
* **Scenario 1: Normal Security State** 
    ```bash
    python baseline_ids.py
    kubectl exec hacker -- curl -v -m 5 telnet://checkoutservice:5050
* **Scenario 2: Chaos Injection (Without CADQ)**
  ```bash
  kubectl apply -f chaos.yaml
  kubectl exec hacker -- curl -v -m 10 telnet://checkoutservice:5050
* **Scenario 3: Active Defense with CADQ**
  ```bash
  # Terminal 1: Run the Controller
  python cadq_controller.py
  
  # Terminal 2: Test the lockdown
  kubectl apply -f chaos.yaml
  kubectl exec hacker -- curl -v -m 2 telnet://checkoutservice:5050
* **Cleanup
  ```bash
  kubectl delete -f chaos.yaml
  minikube stop
