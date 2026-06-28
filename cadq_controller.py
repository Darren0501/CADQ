import os
import re
import json
import time
import signal
import logging
import threading
import subprocess
import socket
from collections import deque
from kubernetes import client, config

# Configure logging to output to standard out
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [CADQ] - %(levelname)s - %(message)s'
)

LOCKFILE_PATH = "/var/run/cadq/quarantine.lock"

class CADQEngine:
    def __init__(self):
        logging.info("Initializing CADQ Deterministic Python Engine (LOCAL ENFORCEMENT MODE)...")
        
        try:
            config.load_incluster_config()
        except config.ConfigException:
            logging.warning("In-cluster config failed. Falling back to local kubeconfig.")
            config.load_kube_config()

        self.core_api = client.CoreV1Api()

        self.active_chaos = False
        self._chaos_lock = threading.Lock()
        
        # --- LOCAL CACHE UNTUK RESOLUSI IP TANPA LAG ---
        self.pod_ip_cache = {}
        self._cache_lock = threading.Lock()

        auth_env = os.getenv("AUTH_SENDERS", "")
        self.auth_senders = [ip.strip() for ip in auth_env.split(",")] if auth_env else []

        self.bypass_active_chaos = os.getenv("BYPASS_ACTIVE_CHAOS", "False").lower() == "true"
        self.bypass_cross_ns = os.getenv("BYPASS_CROSS_NS", "False").lower() == "true"
        self.bypass_auth_senders = os.getenv("BYPASS_AUTH_SENDERS", "False").lower() == "true"
        
        logging.info(
            f"Loaded Config - BypassChaos: {self.bypass_active_chaos}, "
            f"BypassCrossNS: {self.bypass_cross_ns}, "
            f"BypassAuth: {self.bypass_auth_senders}, "
            f"AuthSenders: {self.auth_senders}"
        )

    # -------------------------------------------------------------------------
    # Phase 0: Asynchronous Local Cache 
    # -------------------------------------------------------------------------
    def sync_pod_cache(self):
        logging.info("Starting Background Pod IP Cache Synchronizer...")
        while True:
            try:
                # FIX 1: JANGAN PANGGIL API SAAT CHAOS! (Mencegah GIL Stealing & CPU Drop)
                with self._chaos_lock:
                    in_chaos = self.active_chaos
                
                if in_chaos:
                    time.sleep(5)
                    continue

                # Mengambil seluruh data pod di cluster
                pods = self.core_api.list_pod_for_all_namespaces(_request_timeout=3)
                new_cache = {}
                for pod in pods.items:
                    if pod.status.pod_ip:
                        new_cache[pod.status.pod_ip] = pod.metadata.namespace
                
                # Update kamus lokal secara aman
                with self._cache_lock:
                    self.pod_ip_cache = new_cache
                    
            except Exception as e:
                pass # Tertelan diam-diam agar tidak spam log
            
            # Refresh data setiap 10 detik (agar CPU lebih tenang)
            time.sleep(10)

    # -------------------------------------------------------------------------
    # Phase 1: Control Plane Health Monitor (UPGRADED TO LAYER 4 NETWORK PING)
    # -------------------------------------------------------------------------
    def monitor_control_plane_health(self):
        logging.info("Starting Control Plane RTT Monitor (Pure TCP Socket)...")
        kube_host = os.getenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
        kube_port = int(os.getenv("KUBERNETES_SERVICE_PORT", "443"))

        while True:
            try:
                start_ping = time.time()
                socket.create_connection((kube_host, kube_port), timeout=2.0)
                latency_ms = (time.time() - start_ping) * 1000

                if latency_ms >= 600:
                    with self._chaos_lock:
                        if not self.active_chaos:
                            self.active_chaos = True
                            logging.warning(
                                f"Network Latency HIGH! ({latency_ms:.2f} ms). "
                                f"Degradation detected. Fallback triggered: ActiveChaos = True"
                            )
                else:
                    with self._chaos_lock:
                        if self.active_chaos:
                            self.active_chaos = False
                            logging.info(
                                f"Network connection restored "
                                f"(Latency: {latency_ms:.2f} ms). ActiveChaos = False"
                            )
            except Exception as e:
                with self._chaos_lock:
                    if not self.active_chaos:
                        self.active_chaos = True
            time.sleep(1)

    # -------------------------------------------------------------------------
    # Phase 2: Telemetry Loop — Packet Sniffing & Formula Evaluation
    # -------------------------------------------------------------------------
    def evaluate_telemetry_loop(self):
        logging.info("CADQ Local Engine ON. Monitoring Control Plane latency and local traffic flow...")
        target_port = 5432
        TARGET_NAMESPACE = "backend-ns" # Namespace tempat Database berada

        cmd = ["tcpdump", "-nn", "-l", "-i", "any", f"tcp dst port {target_port} and (tcp[tcpflags] == tcp-syn)"]
        process = None

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1
            )

            syn_timestamps = {}
            THRESHOLD_PACKETS = 25
            TIME_WINDOW_SEC = 0.2 

            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                    
                current_time = time.time()
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)[.:](\d+)\s*>', line)
                source_ip = match.group(1) if match else "unknown"
                
                if source_ip == "unknown":
                    continue

                if source_ip not in syn_timestamps:
                    syn_timestamps[source_ip] = deque(maxlen=THRESHOLD_PACKETS)

                syn_timestamps[source_ip].append(current_time)

                # FIX 2: AUTO-HEALING SLIDING WINDOW (Buang paket basi secara dinamis)
                while syn_timestamps[source_ip] and (current_time - syn_timestamps[source_ip][0] > TIME_WINDOW_SEC):
                    syn_timestamps[source_ip].popleft()

                if len(syn_timestamps[source_ip]) == THRESHOLD_PACKETS:
                    
                    # --- PENGECEKAN DINAMIS (BUKAN HARDCODE) ---
                    with self._cache_lock:
                        source_ns = self.pod_ip_cache.get(source_ip, "external_or_unknown")
                    
                    cross_namespace = (source_ns != TARGET_NAMESPACE)
                    source_pod_in_auth_senders = source_ip in self.auth_senders

                    with self._chaos_lock:
                        real_chaos_state = self.active_chaos

                    eval_chaos = True if self.bypass_active_chaos else real_chaos_state
                    eval_cross_ns = True if self.bypass_cross_ns else cross_namespace
                    eval_not_auth = True if self.bypass_auth_senders else (not source_pod_in_auth_senders)

                    trigger = eval_chaos and eval_cross_ns and eval_not_auth

                    if trigger:
                        logging.error(
                            f"FORMULA MATCHED! Source IP={source_ip} (Namespace: {source_ns}) | "
                            f"ActiveChaos(Eval)={eval_chaos} | "
                            f"CrossNamespace(Eval)={eval_cross_ns} | "
                            f"NotInAuthSenders(Eval)={eval_not_auth}"
                        )

                        exact_detection_start = syn_timestamps[source_ip][0]
                        ttq = self.execute_dynamic_quarantine_local(target_port, source_ip, exact_detection_start)
                        
                        # FIX 3: ZOMBIE CLEANER
                        try:
                            process.terminate()
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        except Exception:
                            pass 
                            
                        self._hold_quarantine(source_ip, target_port, ttq)
                        break

            # Pastikan zombie mati jika loop keluar secara natural
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except:
                    try: process.kill()
                    except: pass

        except Exception as e:
            logging.error(f"Telemetry engine error: {e}")
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except:
                    pass

    # -------------------------------------------------------------------------
    # Phase 3: Dynamic Quarantine — Local iptables Enforcement
    # -------------------------------------------------------------------------
    def execute_dynamic_quarantine_local(self, target_port, source_ip, detection_start_time):
        logging.critical(f"INITIATING LOCAL KERNEL QUARANTINE: Attacker -> {source_ip} | Port -> {target_port}")
        try:
            cmd = (
                f"iptables -I INPUT -p tcp --dport {target_port} -j DROP && "
                f"iptables -I FORWARD -p tcp --dport {target_port} -j DROP"
            )
            subprocess.run(
                cmd, shell=True, check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            ttq_ms = (time.time() - detection_start_time) * 1000
            logging.info("SUCCESS: Local iptables/eBPF rule applied instantly (GRENADE MODE).")
            logging.info(f"METRIC: Time-to-Quarantine (TTQ) = {ttq_ms:.4f} ms")
            return ttq_ms 
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to inject local kernel rule: {e}")
            return 0.0

    # -------------------------------------------------------------------------
    # Indefinite Quarantine Hold
    # -------------------------------------------------------------------------
    def _hold_quarantine(self, source_ip, target_port, ttq_ms):
        os.makedirs(os.path.dirname(LOCKFILE_PATH), exist_ok=True)
        metadata = {
            "quarantine_start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "quarantine_start_epoch": time.time(),
            "ttq_ms": ttq_ms, 
            "attacker_ip": source_ip,
            "blocked_port": target_port,
            "status": "ACTIVE"
        }
        with open(LOCKFILE_PATH, "w") as f:
            json.dump(metadata, f, indent=2)

        while os.path.exists(LOCKFILE_PATH):
            time.sleep(2) 

        subprocess.run(f"iptables -D INPUT -p tcp --dport {target_port} -j DROP", shell=True)
        subprocess.run(f"iptables -D FORWARD -p tcp --dport {target_port} -j DROP", shell=True)

if __name__ == '__main__':
    cadq = CADQEngine()
    
    cache_thread = threading.Thread(target=cadq.sync_pod_cache, daemon=True)
    cache_thread.start()
    
    latency_thread = threading.Thread(target=cadq.monitor_control_plane_health, daemon=True)
    latency_thread.start()

    while True:
        try:
            cadq.evaluate_telemetry_loop()
        except Exception as e:
            logging.error(f"Sensor crash, restarting internally: {e}")
            time.sleep(2)
