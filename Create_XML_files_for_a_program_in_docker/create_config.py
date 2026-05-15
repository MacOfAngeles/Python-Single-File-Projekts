#!/usr/bin/env python3
"""
This script generates configuration files for an internal application.
The files are XML-based and deployed inside a container environment.
@author Mac Mueller (MuM)
Date: 23.03.2026
"""

import re
import glob
import stat
import socket
from pathlib import Path
from subprocess import check_output
from string import Template
import sys


# =====================================================================
# CONSTANTS (DO NOT USE ENUM for template compatibility)
# =====================================================================

# Generic keys
KEY_SIM = "sim"
KEY_IP = "ip"
KEY_SITE = "site"
KEY_ENV = "environment"
KEY_PASS = "default_pass"
KEY_ID = "id"
KEY_NAME = "name"
KEY_ENV_NR = "env_nr"
KEY_HOSTNAME = "hostname"

KEY_PATH_SITE = "path_site"
KEY_PATH_CONFIG = "path_config"

KEY_PATCH_A = "patch_a"
KEY_PATCH_B = "patch_b"

KEY_BACKEND_IP = "backend_ip"
KEY_SERVICE_IP = "service_ip"
KEY_SERVICE_PORT = "service_port"

# Generic services
SERVICE_A = "service_a"
SERVICE_B = "service_b"
SERVICE_C = "service_c"

# States
STATE_ON = "ON"
STATE_OFF = "OFF"

ENCODING = "utf-8"
DEFAULT_PASS = "default-password"

BASE_DIR = Path(__file__).resolve().parent
PATH_DATA = BASE_DIR / "data"
PATH_TEMPLATES = BASE_DIR / "templates"

FILE_SERVICE_PORTS = PATH_DATA / "services_ips_ports"
FILE_HOST_SETTINGS = PATH_DATA / "host_settings"

CONFIG_FILES = [
    "BaseConfig.xml",
    "InstallConfig.xml",
    "LabConfig.xml",
    "SystemConfig.xml",
]

# Generic paths
PATCH_A_GLOB = "/internal/tools/PATCHA/**/"
PATCH_B_GLOB = "/internal/tools/PATCHB/**/"

ENABLED_SERVICES = ["SRV1", "SRV2", "SRV3", "SRV4", "SRV5", "SRV6"]

# =====================================================================
# DATA MODEL (DO NOT USE for template compatibility)
# =====================================================================

class Station:
    def __init__(self):
        self.values = {}
        self.services = {
            SERVICE_A: STATE_OFF,
            SERVICE_B: STATE_OFF,
            SERVICE_C: STATE_OFF,
        }

    def set(self, key, value):
        self.values[key] = value

    def get(self, key, default=None):
        return self.values.get(key, default)

    def has(self, key):
        return key in self.values

    def as_template_dict(self):
        return self.values.copy()

# =====================================================================
# HELPERS
# =====================================================================

def get_first_ip():
    output = check_output(["hostname", "-i"]).decode()
    return re.findall(r"[0-9]+(?:\.[0-9]+){3}", output)[0]

def read_file(path: Path):
    with path.open("r", encoding=ENCODING) as f:
        return f.read()

# =====================================================================
# MAIN LOGIC
# =====================================================================

def load_station() -> Station:
    if len(sys.argv) < 4:
        raise ValueError("Usage: python3 create_config.py <site> <environment> <SIM> <VERSION(optional)>")

    site = sys.argv[1].lower()
    env = sys.argv[2].lower()
    sim = sys.argv[3].upper()

    st = Station()

    st.set(KEY_PASS, DEFAULT_PASS)
    st.set(KEY_SITE, site)
    st.set(KEY_ENV, env)
    st.set(KEY_SIM, sim)
    st.set(KEY_ENV_NR, env[-1])

    hostname = socket.gethostname().split("-")[0]
    st.set(KEY_HOSTNAME, hostname)

    # Paths
    path_site = Path(f"/internal/application/{site}/")
    st.set(KEY_PATH_SITE, str(path_site))
    st.set(KEY_PATH_CONFIG, str(path_site / "config/"))

    # IP
    st.set(KEY_IP, get_first_ip())

    # Patch detection (generic)
    patch_a = glob.glob(PATCH_A_GLOB)
    patch_b = glob.glob(PATCH_B_GLOB)

    st.set(KEY_PATCH_A, patch_a[0][:-1] if patch_a else "PATCHA")
    st.set(KEY_PATCH_B, patch_b[0][:-1] if patch_b else "/internal/tools/PATCHB")

    # ID & Name (neutralized paths)
    base_path = Path(f"/internal/env/{env}/application/GENERIC/{sim}")

    id_file = base_path / "db/id_data.txt"
    st.set(KEY_ID, read_file(id_file).partition("id:")[2].partition(",")[0].strip())

    name_file = base_path / "info/key_info.txt"
    txt = read_file(name_file)
    st.set(KEY_NAME, txt.partition(f"{sim}(")[2].partition(")")[0])

    # Backend/Service data
    backend_ip = None

    if not FILE_SERVICE_PORTS.exists():
        raise FileNotFoundError(f"Missing file: {FILE_SERVICE_PORTS}")

    for line in FILE_SERVICE_PORTS.read_text().splitlines():
        if "# BACKEND" in line:
            backend_ip = re.findall(r"[0-9]+(?:\.[0-9]+){3}", line)[0]

        if hostname in line and re.split(r"[ \t:]+", line)[0] == hostname:
            st.set(KEY_SERVICE_IP, backend_ip)
            st.set(KEY_SERVICE_PORT, re.findall(r"[0-9]{4}", line)[0])
            st.set(KEY_BACKEND_IP, re.findall(r"[0-9]+(?:\.[0-9]+){3}", line)[0])

            if sim in line:
                break

    if backend_ip is None or not st.has(KEY_SERVICE_PORT):
        raise ValueError("Missing service IP or hostname entry")

    # Host feature settings
    if not FILE_HOST_SETTINGS.exists():
        raise FileNotFoundError(f"Missing file: {FILE_HOST_SETTINGS}")

    for line in FILE_HOST_SETTINGS.read_text().splitlines():

        if hostname in line and line.split()[0] == hostname:
            if "SERVICE_A=ON" in line: st.services[SERVICE_A] = STATE_ON
            if "SERVICE_B=ON" in line: st.services[SERVICE_B] = STATE_ON
            if "SERVICE_C=ON" in line: st.services[SERVICE_C] = STATE_ON
            break

    # Additional enabled services for templates
    enabled_map_on = ["ON", "ON", "OFF", "ON", "ON", "default"]
    enabled_map_off = ["ON", "ON", "OFF", "ON", "OFF", "default"]

    mapped = enabled_map_on if st.services[SERVICE_A] == STATE_ON else enabled_map_off

    for service_name, value in zip(ENABLED_SERVICES, mapped):
        st.values[service_name.lower()] = value.capitalize() if value in [STATE_ON, STATE_OFF] else value

    return st

def generate_configs(st: Station):
    path_config = Path(st.get(KEY_PATH_CONFIG))
    cfg = st.as_template_dict()
    
    for cfg_name in CONFIG_FILES:
        template_path = PATH_TEMPLATES / cfg_name
        text = template_path.read_text(encoding=f"{ENCODING}-sig").lstrip("\ufeff")
        content = Template(text).substitute(cfg)

        target = path_config / cfg_name
        
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as f:
            f.write(content.encode(ENCODING))
            print(f"Config created: {cfg_name}")

def generate_scripts(st: Station):
    path_site = Path(st.get(KEY_PATH_SITE))
    values = st.as_template_dict()

    for service, state in st.services.items():
        if state == STATE_OFF:
            continue

        template_path = PATH_TEMPLATES / f"{service}.sh"
        raw = template_path.read_text().lstrip("\ufeff")
        result = Template(raw).substitute(values)

        target = path_site / f"{service}.sh"
        target.write_text(result, encoding=ENCODING)
        target.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
                     stat.S_IRGRP | stat.S_IXGRP |
                     stat.S_IROTH | stat.S_IXOTH)

        print(f"Script created: {service}.sh")

# =====================================================================
# MAIN
# =====================================================================

def main():
    try:
        st = load_station()

        if st.services[SERVICE_A] == STATE_ON:
            generate_configs(st)

        generate_scripts(st)

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()