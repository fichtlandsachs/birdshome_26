#!/usr/bin/env python3
"""Network connectivity checker and WiFi fallback service.

Checks if Ethernet connection is active. If not, connects to configured WiFi.
"""

import subprocess
import sys
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from app.models import Setting

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {' '.join(cmd)}")
        return 1, "", "timeout"
    except Exception as e:
        logger.error(f"Command failed: {e}")
        return 1, "", str(e)


def is_ethernet_connected() -> bool:
    """Check if any Ethernet interface is connected and has an IP address."""
    # Get list of network interfaces with ip addr
    rc, out, err = run_cmd(["ip", "addr", "show"])

    if rc != 0:
        logger.error(f"Failed to get network interfaces: {err}")
        return False

    # Look for ethernet interfaces (eth0, eth1, enp*, etc.)
    # Check if they have an inet address and are UP
    lines = out.split('\n')
    current_interface = None
    is_up = False
    has_ip = False

    for line in lines:
        # Interface line starts with number
        if line and line[0].isdigit():
            # Save previous interface state
            if current_interface and current_interface.startswith(('eth', 'enp')) and is_up and has_ip:
                logger.info(f"Ethernet connection found on {current_interface}")
                return True

            # Parse new interface
            parts = line.split(':')
            if len(parts) >= 2:
                current_interface = parts[1].strip()
                is_up = 'UP' in line and 'LOWER_UP' in line
                has_ip = False

        # Check for inet address
        elif 'inet ' in line and 'scope global' in line:
            has_ip = True

    # Check last interface
    if current_interface and current_interface.startswith(('eth', 'enp')) and is_up and has_ip:
        logger.info(f"Ethernet connection found on {current_interface}")
        return True

    logger.info("No active Ethernet connection found")
    return False


def is_wifi_connected() -> bool:
    """Check if WiFi is already connected."""
    rc, out, err = run_cmd(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"])

    if rc != 0:
        logger.error(f"Failed to check WiFi status: {err}")
        return False

    for line in out.split('\n'):
        parts = line.split(':')
        if len(parts) >= 3:
            device_type = parts[1]
            state = parts[2]
            if device_type == 'wifi' and state == 'connected':
                logger.info("WiFi already connected")
                return True

    return False


def connect_wifi(ssid: str, password: str) -> bool:
    """Connect to WiFi network using NetworkManager."""
    if not ssid or not password:
        logger.warning("WiFi SSID or password not configured")
        return False

    logger.info(f"Attempting to connect to WiFi: {ssid}")

    # Check if connection profile already exists
    rc, out, err = run_cmd(["nmcli", "connection", "show", ssid])

    if rc == 0:
        # Connection exists, try to activate it
        logger.info(f"Connection profile '{ssid}' exists, activating...")
        rc, out, err = run_cmd(["nmcli", "connection", "up", ssid])

        if rc == 0:
            logger.info(f"Successfully connected to {ssid}")
            return True
        else:
            logger.error(f"Failed to activate connection: {err}")
            # Try to delete and recreate
            logger.info("Deleting old connection profile...")
            run_cmd(["nmcli", "connection", "delete", ssid])

    # Create new connection
    logger.info(f"Creating new connection profile for {ssid}")
    rc, out, err = run_cmd([
        "nmcli", "device", "wifi", "connect", ssid,
        "password", password
    ])

    if rc == 0:
        logger.info(f"Successfully connected to {ssid}")
        return True
    else:
        logger.error(f"Failed to connect to {ssid}: {err}")
        return False


def get_wifi_config() -> tuple[str, str]:
    """Load WiFi configuration from database."""
    try:
        app = create_app()
        with app.app_context():
            settings = {s.key: s.value for s in Setting.query.all()}
            ssid = settings.get("WIFI_SSID", "")
            password = settings.get("WIFI_PASSWORD", "")
            return ssid, password
    except Exception as e:
        logger.error(f"Failed to load WiFi config from database: {e}")
        return "", ""


def main():
    """Main network check logic."""
    logger.info("Starting network connectivity check...")

    # Check if Ethernet is connected
    if is_ethernet_connected():
        logger.info("Ethernet connection active, no action needed")
        return 0

    logger.info("No Ethernet connection, checking WiFi...")

    # Check if WiFi is already connected
    if is_wifi_connected():
        logger.info("WiFi connection active, no action needed")
        return 0

    logger.info("No active network connection, attempting WiFi fallback...")

    # Load WiFi configuration
    ssid, password = get_wifi_config()

    if not ssid:
        logger.warning("WiFi SSID not configured in settings, skipping WiFi connection")
        return 1

    # Try to connect to WiFi
    if connect_wifi(ssid, password):
        logger.info("WiFi connection established successfully")

        # Wait a bit and verify connection
        time.sleep(5)
        rc, out, err = run_cmd(["ping", "-c", "1", "-W", "3", "8.8.8.8"])
        if rc == 0:
            logger.info("Internet connectivity verified")
            return 0
        else:
            logger.warning("WiFi connected but no internet connectivity")
            return 1
    else:
        logger.error("Failed to establish WiFi connection")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logger.exception(f"Network check failed with exception: {e}")
        sys.exit(1)
