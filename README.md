How to run the program:
First time:
1. Create Minikube 
    minikube start --cpus=4 --memory=6144 --network-plugin=cni --cni=calico
2. Build the web (From Open source)
    kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/main/release/kubernetes-manifests.yaml
    kubectl get pods -w
3. Install the Chaos Mesh
    helm repo add chaos-mesh https://charts.chaos-mesh.org
    helm repo update
    helm install chaos-mesh chaos-mesh/chaos-mesh -n=chaos-mesh --create-namespace
4. Make the hacker pod 
    kubectl run hacker --image=alpine --labels="app=frontend" -- sleep infinity
    kubectl exec -it hacker -- apk add curl
5. Install kubernetes
    pip install kubernetes

Daily Re-run:
1. Start minikube
    minikube start
2. State 1: Normal Security
    python baseline_ids.py
    kubectl exec hacker -- curl -v -m 5 telnet://checkoutservice:5050
3. State 2: Normal Security + Chaos
    kubectl apply -f chaos.yaml
    kubectl exec hacker -- curl -v -m 10 telnet://checkoutservice:5050
4. State 3: CADQ
    python cadq_controller.py
    kubectl exec hacker -- curl -v -m 2 telnet://checkoutservice:5050
5. Clean up
    kubectl delete -f chaos.yaml
    minikube stop