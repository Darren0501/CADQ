from kubernetes import client, config
from kubernetes.client.rest import ApiException
import time

def run_simulated_ids():
    config.load_kube_config()
    networking_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi()
    
    namespace = "default"
    ids_policy_name = "ids-standard-protection"
    
    ids_policy = client.V1NetworkPolicy(
        metadata=client.V1ObjectMeta(name=ids_policy_name),
        spec=client.V1NetworkPolicySpec(
            pod_selector=client.V1LabelSelector(match_labels={"app": "frontend"}), 
            policy_types=["Egress"],
            egress=[] # Block the hacker
        )
    )

    print("🛡️ [IDS MONITOR] Standard Deep Packet Inspection is ONLINE.\n")

    while True:
        chaos_active = False

        # 1. Check if the network is healthy
        try:
            chaos_objects = custom_api.list_namespaced_custom_object(
                group="chaos-mesh.org", version="v1alpha1", namespace=namespace, plural="networkchaos"
            )
            if len(chaos_objects.get('items', [])) > 0:
                chaos_active = True
        except ApiException:
            pass

        # 2. IDS Logic (The Vulnerability)
        if not chaos_active:
            try:
                networking_api.read_namespaced_network_policy(name=ids_policy_name, namespace=namespace)
            except ApiException as e:
                if e.status == 404:
                    print(f"[{time.strftime('%X')}] 🟢 [IDS] Network latency is low (< 5ms). Applying signature blocks.")
                    networking_api.create_namespaced_network_policy(namespace=namespace, body=ids_policy)
        
        elif chaos_active:
            try:
                # CHAOS BLINDS THE IDS! IT TIMES OUT AND DROPS THE SHIELD!
                networking_api.read_namespaced_network_policy(name=ids_policy_name, namespace=namespace)
                print(f"[{time.strftime('%X')}] ❌ [IDS ERROR] Latency spike! Deep Packet Inspection TIMED OUT.")
                print(f"[{time.strftime('%X')}] ⚠️ [IDS ERROR] Dropping packets. Protection shield is OFFLINE.")
                networking_api.delete_namespaced_network_policy(name=ids_policy_name, namespace=namespace)
            except ApiException:
                pass # Already offline

        time.sleep(3)

if __name__ == '__main__':
    try:
        run_simulated_ids()
    except KeyboardInterrupt:
        print("\n🛑 IDS Shut down.")