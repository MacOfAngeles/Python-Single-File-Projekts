######################################################################################################
# This Python file creates a Netplan file with a static IP address and sets the new hostname.
# Author: MuM
# Date: 15.05.2026
######################################################################################################
# RUN ONLY WITH SUDO !!
######################################################################################################

import netifaces
import ipaddress
import yaml
import subprocess
import time


def get_gateway(ip: str, prefix: str) -> str:
    """Return the first usable IP in the network as the gateway."""
    network = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    return str(network.network_address + 1)


def get_dns_server(ip: str) -> str:
    """Return DNS IP based on network range."""
    return "200.22.22.3" if ip.startswith("200.22.22") else "10.222.22.3"


def write_netplan(config: dict) -> None:
    """Write the netplan YAML configuration and remove apostrophes."""
    filepath = "/etc/netplan/50-cloud-init.yaml"

    with open(filepath, "w") as outfile:
        yaml.dump(config, outfile, default_style=None, default_flow_style=False, sort_keys=False)

    # Remove single quotes added by PyYAML
    with open(filepath, "rt") as f:
        content = f.read().replace("'", "")

    with open(filepath, "w") as f:
        f.write(content)


if __name__ == "__main__":

    # Getting inputs
    print("hostname?")
    hostname = input().strip()

    print("ip?")
    ip = input().strip()

    print("prefix?")
    prefix = input().strip()

    # Netplan dictionary
    netplan = {
        "network": {
            "version": 2,
            "renderer": "networkd",
            "ethernets": {}
        }
    }

    # Gateway & DNS
    ip_gateway = get_gateway(ip, prefix)
    ip_dns = get_dns_server(ip)

    # Detecting interfaces
    interfaces = netifaces.interfaces()
    if "lo" in interfaces:
        interfaces.remove("lo")

    link_not_detected = True

    while link_not_detected:
        print("Checking interfaces for link...")
        for iface in interfaces:

            ps = subprocess.Popen(
                f"ethtool {iface} | sed -n -e 's/^.*Link detected: //p'",
                stdout=subprocess.PIPE, text=True, shell=True
            )
            result = ps.communicate()[0].strip()

            print(f"{iface}: {result}")

            # Link detected → set static IP
            if result == "yes":
                netplan["network"]["ethernets"][iface] = {
                    "addresses": [f"{ip}/{prefix}"],
                    "routes": [{"to": "default", "via": ip_gateway}],
                    "nameservers": {
                        "search": ["RSSLAB.local"],
                        "addresses": [ip_dns]
                    }
                }
                link_not_detected = False

            else:
                netplan["network"]["ethernets"][iface] = {
                    "dhcp4": True
                }

        if link_not_detected:
            print("No plugged cable detected. Waiting 5 seconds...")
            time.sleep(5)

    # Write netplan file
    write_netplan(netplan)

    # Apply settings
    subprocess.run(["netplan", "apply"])

    # Set hostname
    subprocess.run(["hostnamectl", "set-hostname", hostname])

    # Reboot
    subprocess.run(["reboot", "now"])