from kubernetes import client, config
from kubernetes.client.rest import ApiException
import time

def monitor_and_react():
    # Connect to your local Minikube cluster
    config.load_kube_config()
    networking_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi() # Needed to detect Chaos Mesh CRDs
    
    namespace = "default"
    policy_name = "cadq-frontend-quarantine"
    
    # Define the Quarantine Network Policy using the bulletproof Dictionary format
    quarantine_policy = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": policy_name,
            "namespace": namespace
        },
        "spec": {
            "podSelector": {
                "matchLabels": {"app": "frontend"}
            },
            "policyTypes": ["Egress"]
            # Omitting the egress array strictly enforces a "Deny All" ruleset
        }
    }

    print("🛡️ CADQ Radar Online. Monitoring network states continuously...\n")

    while True:
        chaos_active = False
        quarantine_active = False

        # 1. CHECK FOR CHAOS
        try:
            chaos_objects = custom_api.list_namespaced_custom_object(
                group="chaos-mesh.org",
                version="v1alpha1",
                namespace=namespace,
                plural="networkchaos"
            )
            if len(chaos_objects.get('items', [])) > 0:
                chaos_active = True
        except ApiException:
            pass # Ignore if chaos mesh isn't active

        # 2. CHECK FOR QUARANTINE
        try:
            networking_api.read_namespaced_network_policy(name=policy_name, namespace=namespace)
            quarantine_active = True
        except ApiException as e:
            if e.status == 404: # 404 means the policy does not exist
                quarantine_active = False

        # 3. THE DECISION ENGINE (Reconciliation)
        if chaos_active and not quarantine_active:
            start_time = time.perf_counter() # ⏱️ START THE TIMER
            
            print(f"[{time.strftime('%X')}] 🚨 ALERT: Chaos Detected! Triggering Dynamic Quarantine...")
            
            try:
                # Create the cage
                networking_api.create_namespaced_network_policy(namespace=namespace, body=quarantine_policy)
                
                end_time = time.perf_counter() # ⏱️ STOP THE TIMER
                ttq_ms = (end_time - start_time) * 1000 # Convert to milliseconds
                
                print(f"[{time.strftime('%X')}] ✅ SUCCESS: Frontend is locked down.")
                print(f"📊 KPI 1 (TTQ): Quarantine applied in {ttq_ms:.2f} ms\n")
                
                quarantine_active = True # Memory update
                
            except ApiException as e:
                if e.status == 409:
                    quarantine_active = True # Ignore if already exists
                else:
                    print(f"❌ API Error: {e}")
            
        elif not chaos_active and quarantine_active:
            print(f"[{time.strftime('%X')}] 🌤️  INFO: Chaos has passed. Lifting Quarantine...")
            try:
                networking_api.delete_namespaced_network_policy(name=policy_name, namespace=namespace)
                print(f"[{time.strftime('%X')}] 🟢 SUCCESS: Frontend restored to normal operations.\n")
                quarantine_active = False # Memory update
            except ApiException:
                pass

        # 4. REST AND REPEAT
        time.sleep(5)

if __name__ == '__main__':
    try:
        monitor_and_react()
    except KeyboardInterrupt:
        print("\n🛑 CADQ Radar gracefully shut down by user.")