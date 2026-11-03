"""
Pytest unit tests for Oracle ARM Provisioner & Capacity Retry Daemon.
"""

from pico.oracle_arm_retry import OCIConfig, OCIArmProvisioner


def test_oci_arm_provisioner_mock_success():
    config = OCIConfig(
        region="ap-mumbai-1",
        ocpus=2,
        memory_in_gbs=12,
        retry_interval_seconds=10,
        max_retries=5
    )
    provisioner = OCIArmProvisioner(config, mock_mode=True)
    payload = provisioner.generate_launch_payload()

    assert payload["shape"] == "VM.Standard.A1.Flex"
    assert payload["shapeConfig"]["ocpus"] == 2
    assert payload["shapeConfig"]["memoryInGBs"] == 12
    assert "user_data" in payload["metadata"]

    # Run the loop
    success = provisioner.run_until_provisioned(max_attempts=4)
    assert success is True
    assert provisioner.attempt_count == 3
