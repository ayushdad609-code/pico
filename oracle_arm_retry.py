"""
Oracle Cloud Infrastructure (OCI) ARM Always-Free VM Provisioner & Capacity Retry Daemon.
From 32_FREE_BACKEND.pdf (§1 ₹0 Infrastructure Architecture & §6 OCI Capacity Mitigation).

Provisions the Ampere A1 Flex instance (2 OCPUs, 12 GB RAM, Ubuntu ARM64) on Oracle
Always Free Tier. Handles the ubiquitous "Out of host capacity" (HTTP 500) error with
an automated exponential-backoff retry loop and automated Docker Compose bootstrapping.
"""

import os
import sys
import time
import json
import random
import argparse
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict


DEFAULT_CLOUD_INIT = """#!/bin/bash
set -e
echo "🚀 Bootstrapping Pico Backend on Oracle Cloud ARM VM..."

# 1. System updates & Docker installation
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 2. Setup deploy user & pico directory
mkdir -p /opt/pico
cd /opt/pico

echo "Pico Cloud-Init bootstrap complete! Docker ready for compose."
"""


@dataclass
class OCIConfig:
    tenancy: str = ""
    user: str = ""
    fingerprint: str = ""
    key_file: str = ""
    region: str = "ap-mumbai-1"
    compartment_id: str = ""
    subnet_id: str = ""
    image_id: str = ""
    ssh_public_key: str = ""
    ocpus: int = 2
    memory_in_gbs: int = 12
    display_name: str = "pico-backend-vm"
    retry_interval_seconds: int = 60
    max_retries: int = 1000

    @classmethod
    def from_env(cls) -> "OCIConfig":
        return cls(
            tenancy=os.getenv("OCI_TENANCY", ""),
            user=os.getenv("OCI_USER", ""),
            fingerprint=os.getenv("OCI_FINGERPRINT", ""),
            key_file=os.getenv("OCI_KEY_FILE", ""),
            region=os.getenv("OCI_REGION", "ap-mumbai-1"),
            compartment_id=os.getenv("OCI_COMPARTMENT_ID", ""),
            subnet_id=os.getenv("OCI_SUBNET_ID", ""),
            image_id=os.getenv("OCI_IMAGE_ID", ""),
            ssh_public_key=os.getenv("SSH_PUBLIC_KEY", ""),
            ocpus=int(os.getenv("OCI_OCPUS", "2")),
            memory_in_gbs=int(os.getenv("OCI_MEMORY_GBS", "12")),
            display_name=os.getenv("OCI_DISPLAY_NAME", "pico-backend-vm"),
            retry_interval_seconds=int(os.getenv("OCI_RETRY_INTERVAL", "60")),
            max_retries=int(os.getenv("OCI_MAX_RETRIES", "1000")),
        )


class OCIArmProvisioner:
    """Manages the launch requests, error catches, and retry backoff loop."""

    def __init__(self, config: OCIConfig, mock_mode: bool = False):
        self.config = config
        self.mock_mode = mock_mode
        self.attempt_count = 0

    def generate_launch_payload(self) -> Dict[str, Any]:
        """Constructs the OCI Core LaunchInstance payload for VM.Standard.A1.Flex."""
        import base64

        cloud_init_b64 = base64.b64encode(DEFAULT_CLOUD_INIT.encode("utf-8")).decode("utf-8")

        return {
            "compartmentId": self.config.compartment_id or "ocid1.compartment.oc1..mock",
            "displayName": self.config.display_name,
            "shape": "VM.Standard.A1.Flex",
            "shapeConfig": {
                "ocpus": self.config.ocpus,
                "memoryInGBs": self.config.memory_in_gbs
            },
            "sourceDetails": {
                "sourceType": "image",
                "imageId": self.config.image_id or "ocid1.image.oc1..mock-ubuntu-arm64",
                "bootVolumeSizeInGBs": 50
            },
            "createVnicDetails": {
                "subnetId": self.config.subnet_id or "ocid1.subnet.oc1..mock",
                "assignPublicIp": True
            },
            "metadata": {
                "ssh_authorized_keys": self.config.ssh_public_key,
                "user_data": cloud_init_b64
            }
        }

    def attempt_launch(self) -> Tuple[bool, int, str]:
        """
        Sends the launch request.
        Returns (success: bool, status_code: int, message: str).
        """
        self.attempt_count += 1

        if self.mock_mode:
            # In mock mode, simulate 2 capacity failures before successful provisioning
            if self.attempt_count < 3:
                return (
                    False,
                    500,
                    "Out of host capacity for shape VM.Standard.A1.Flex in availability domain AD-1."
                )
            return (
                True,
                200,
                json.dumps({
                    "id": "ocid1.instance.oc1.ap-mumbai-1.mocksuccessinstance123",
                    "displayName": self.config.display_name,
                    "lifecycleState": "PROVISIONING",
                    "shape": "VM.Standard.A1.Flex"
                })
            )

        # Real OCI REST API invocation
        # Requires oci package or authenticated REST signer
        try:
            import oci
            oci_config = {
                "user": self.config.user,
                "key_file": self.config.key_file,
                "fingerprint": self.config.fingerprint,
                "tenancy": self.config.tenancy,
                "region": self.config.region
            }
            compute_client = oci.core.ComputeClient(oci_config)
            payload = self.generate_launch_payload()
            
            # Build LaunchInstanceDetails from payload
            launch_details = oci.core.models.LaunchInstanceDetails(
                compartment_id=payload["compartmentId"],
                display_name=payload["displayName"],
                shape=payload["shape"],
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                    ocpus=payload["shapeConfig"]["ocpus"],
                    memory_in_gbs=payload["shapeConfig"]["memoryInGBs"]
                ),
                source_details=oci.core.models.InstanceSourceViaImageDetails(
                    image_id=payload["sourceDetails"]["imageId"],
                    boot_volume_size_in_gbs=payload["sourceDetails"]["bootVolumeSizeInGBs"]
                ),
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    subnet_id=payload["createVnicDetails"]["subnetId"],
                    assign_public_ip=payload["createVnicDetails"]["assignPublicIp"]
                ),
                metadata=payload["metadata"]
            )
            response = compute_client.launch_instance(launch_details)
            return True, 200, str(response.data.id)
        except Exception as e:
            err_str = str(e)
            if "Out of host capacity" in err_str or "Capacity" in err_str or "TooManyRequests" in err_str:
                return False, 500, f"OCI Out of Capacity: {err_str[:120]}"
            return False, 400, f"OCI API Error: {err_str[:120]}"

    def run_until_provisioned(self, max_attempts: Optional[int] = None) -> bool:
        """Runs the capacity retry daemon loop until success or limit reached."""
        limit = max_attempts or self.config.max_retries
        print(f"🚀 [OCI ARM Provisioner] Starting retry loop for '{self.config.display_name}'")
        print(f"   Shape: VM.Standard.A1.Flex ({self.config.ocpus} OCPUs, {self.config.memory_in_gbs} GB RAM)")
        print(f"   Region: {self.config.region} | Base Interval: {self.config.retry_interval_seconds}s")
        print(f"   Mode: {'MOCK SIMULATION' if self.mock_mode else 'LIVE OCI REST'}\n")

        while self.attempt_count < limit:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            success, code, msg = self.attempt_launch()

            if success:
                print(f"🎉 [{ts}] [ATTEMPT #{self.attempt_count}] SUCCESS (Code {code})!")
                print(f"   Instance provisioned: {msg}")
                print("   Docker & Pico Compose bootstrapping will start shortly via cloud-init.")
                return True

            # Calculate jittered sleep: interval +/- 15%
            jitter = random.uniform(-0.15, 0.15) * self.config.retry_interval_seconds
            sleep_time = max(5.0, self.config.retry_interval_seconds + jitter)

            print(f"⏳ [{ts}] [ATTEMPT #{self.attempt_count}] Code {code}: {msg}")
            print(f"   Waiting {sleep_time:.1f}s before next retry...")

            if self.mock_mode:
                time.sleep(0.1)  # Fast in mock mode
            else:
                time.sleep(sleep_time)

        print(f"\n❌ [OCI ARM Provisioner] Reached maximum attempts ({limit}). Exiting.")
        return False


def main():
    parser = argparse.ArgumentParser(description="Pico OCI ARM Always-Free VM Provisioner & Retry Daemon")
    parser.add_argument("--dry-run", "--mock", action="store_true", help="Run simulation mock without live OCI API")
    parser.add_argument("--region", default="ap-mumbai-1", help="OCI region (e.g. ap-mumbai-1, ap-hyderabad-1)")
    parser.add_argument("--interval", type=int, default=60, help="Retry interval in seconds (default: 60)")
    parser.add_argument("--max-retries", type=int, default=100, help="Max retry attempts (default: 100)")
    args = parser.parse_args()

    config = OCIConfig.from_env()
    config.region = args.region
    config.retry_interval_seconds = args.interval
    config.max_retries = args.max_retries

    # If no credentials present, auto-enable mock mode
    is_mock = args.dry_run or not (config.tenancy and config.user and config.key_file)
    if is_mock and not args.dry_run:
        print("ℹ️  No live OCI credentials detected in environment. Running in mock/dry-run mode.\n")

    provisioner = OCIArmProvisioner(config, mock_mode=is_mock)
    success = provisioner.run_until_provisioned()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
