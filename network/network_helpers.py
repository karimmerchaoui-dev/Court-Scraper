import os
import random
import subprocess
import time

import psutil
import requests

from config_ import nordvpn_path

IP_SOURCES = [
    {
        "name": "ipinfo.io",
        "url": "https://ipinfo.io/json",
        "ip_field": "ip",
        "country_field": "country"
    },
    {
        "name": "ip-api.com",
        "url": "http://ip-api.com/json",
        "ip_field": "query",
        "country_field": "countryCode"
    },
        {
        "name": "myip.com",
        "url": "https://api.myip.com",
        "ip_field": "ip",
        "country_field": "cc"
    },
    {
        "name": "ipwho.is",
        "url": "https://ipwho.is/",
        "ip_field": "ip",
        "country_field": "country_code"
    },
    {
        "name": "freeipapi.com",
        "url": "https://freeipapi.com/api/json",
        "ip_field": "ipAddress",
        "country_field": "countryCode"
    },
]


def _connect_to_random_city(countries=["United States"]):
    """Just fires the nordvpn connect command. No waiting, no IP checking."""
    country = random.choice(countries)
    target = random.choice(US_CITIES) if country.strip().lower() == "united states" else country

    print(f"🌍 Connecting to {target}...")

    if not is_nordvpn_running():
        restart_nordvpn_gui_only()

    while True:
        reset_nordvpn_network()
        try:
            subprocess.run(
                f'nordvpn -c -g "{target}"',
                shell=True,
                check=True,
                cwd=r"C:\Program Files\NordVPN",
                timeout=15
            )
            break
        except Exception:
            pass
def _fetch_ip_data(vpn_timeout=15, interval=2):
    elapsed = 0

    while elapsed < vpn_timeout:
        for source in IP_SOURCES:
            try:
                response = requests.get(source["url"], timeout=2)
                if response.status_code != 200:
                    break
                data = response.json()
                ip = data.get(source["ip_field"], "")
                country = data.get(source["country_field"], "")
                if ip and country:
                    print(f"✅ Connected — IP: {ip} | Country: {country}")
                    return ip, country.upper()
            except Exception as e:
                break

        time.sleep(interval)
        elapsed += interval

    # Timeout reached — rotate city, no recursion
    print("⚠️ VPN did not connect in time — changing city...")
    _connect_to_random_city()
    time.sleep(5)
    return None, None  # caller retries if needed

def get_ip():
    ip, _ = _fetch_ip_data()
    return ip


def is_us_ip():
    _, country = _fetch_ip_data()
    if not country:
        return False
    print(f"country: {country}")
    return country in ("US", "CA")

def save_ip_to_file(ip, filename="used_ips.txt"):
    """Save IP to file"""
    with open(filename, "a") as f:
        f.write(f"\n{ip}")




def is_nordvpn_running():
    # Check if nordvpn.exe is running
    for process in psutil.process_iter(attrs=['pid', 'name']):
        if process.info['name'] == 'NordVPN.exe':
            return True
    return False


def disconnect():
    try:
        # Set 'cwd' to the NordVPN directory and run the command directly
        subprocess.run('nordvpn -d', shell=True, check=True, cwd=r"C:\Program Files\NordVPN")
        print("NordVPN disconnected successfully.")
    except subprocess.CalledProcessError as e:
        print()

def load_used_ips(filename="used_ips.txt"):
    """Load all previously used IPs"""
    try:
        with open(filename, "r") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()

def restart_nordvpn_gui_only():
    """
    Just restart the NordVPN GUI application without changing connection
    """
    reset_nordvpn_network()
    try:
        print("🔄 Restarting NordVPN GUI...")

        _kill_nordvpn_processes_windows()

        time.sleep(3)

        # Restart GUI
        if os.path.exists(nordvpn_path):
            subprocess.Popen([nordvpn_path], shell=True)
            while not is_nordvpn_running():
                time.sleep(2)
            print("✅ NordVPN GUI restarted")
            time.sleep(2)
            return True
        else:
            print("❌ NordVPN executable not found")
            return False

    except Exception as e:
        print(f"❌ Failed to restart NordVPN GUI: {e}")
        return False

def _kill_nordvpn_processes_windows():
    """
    Kill all NordVPN related processes on Windows
    """
    killed = 0
    nord_process_names = [
        "NordVPN.exe",
        "NordVPN.Service.exe",
        "NordVPN.Update.exe",
        "nordvpn-service.exe",
        "NordUpdateService.exe"
    ]

    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                proc_name = proc.info['name'] or ""
                if proc_name.lower() in [name.lower() for name in nord_process_names]:
                    print(f"   Killing process: {proc_name} (PID: {proc.info['pid']})")
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        print(f"⚠️ Error killing processes: {e}")

    return killed






US_CITIES = [
    "anchorage", "ashburn", "atlanta", "baltimore", "billings", "boise", "boston",
    "buffalo", "burlington", "charlotte", "charleston", "cheyenne", "chicago", "dallas",
    "denver", "honolulu", "houston", "huntington", "kansas city", "las vegas", "lewiston",
    "los angeles", "mcallen", "miami", "nashua", "nashville", "new haven", "new york",
    "omaha", "phoenix", "pittsburgh", "portland", "providence", "salt lake city",
    "san francisco", "seattle", "st. louis", "trenton", "wilmington"
]

def connect(countries=["United States"], wait=True, save_ip=True, timeout=12, max_retries=3):
    used_ips = load_used_ips()
    initial_ip=get_ip()
    attempt = 0

    while attempt < max_retries:
        try:
            country = random.choice(countries)
            target = random.choice(US_CITIES) if country.strip().lower() == "united states" else country

            if not is_nordvpn_running():
                restart_nordvpn_gui_only()

            print(f"🌍 Attempt {attempt + 1}: Connecting to {target}...")

            # Only reset network before first connect, not on every used-IP retry
            reset_nordvpn_network()
            try:
                subprocess.run(
                    f'nordvpn -c -g "{target}"',
                    shell=True, check=True,
                    cwd=r"C:\Program Files\NordVPN",
                    timeout=15
                )
            except Exception as e:
                print(f"⚠️ Connect command failed: {e}")
                attempt += 1
                continue

            if not wait:
                return True

            # Wait for IP to actually change
            time.sleep(2)
            start = time.time()
            current_ip = None

            while time.time() - start < timeout:
                current_ip = get_ip()
                if current_ip and current_ip != initial_ip:
                    break
                time.sleep(1)

            if not current_ip or current_ip == initial_ip:
                print(f"⏱️ Timeout — IP never changed. Retrying...")
                attempt += 1
                continue

            # We have a new IP — check if it was used before
            if not is_us_ip():
                print(f"🚫 IP {current_ip} is not US. Retrying...")
                attempt += 1
                continue

            if current_ip in used_ips:
                print(f"🚫 IP {current_ip} was used before. Trying new city...")
                # Just disconnect cleanly — no network reset
                subprocess.run('nordvpn -d', shell=True, cwd=r"C:\Program Files\NordVPN")
                time.sleep(2)
                # Don't increment attempt, just pick a new city
                continue

            # Fresh, valid US IP
            if save_ip:
                save_ip_to_file(current_ip)
            print(f"✅ Connected with new IP: {current_ip}")
            return True

        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")
            attempt += 1

    print(f"❌ Failed after {max_retries} attempts")
    return False



def reset_vpn(pool=None,wait=True,countries=["United States"],save_ip=True):
    if pool:
        time.sleep(2)
        while pool.is_any_downloading():
            time.sleep(1)
    disconnect()
    while True:
        connected=connect(countries,wait,save_ip=save_ip)
        if connected:
            break


def reset_nordvpn_network(adapter_name="Wi-Fi", skip_firewall=False):
    """
    Reset network settings to fix NordVPN connection issues

    Args:
        adapter_name: Name of your network adapter (default: "Wi-Fi")
                     Common alternatives: "Ethernet", "Wi-Fi 2", etc.
        skip_firewall: Set to True to skip firewall reset (default: False)
    """

    print("Starting NordVPN Network Reset Sequence...")

    commands = [
        # Reset TCP/IP stack
        ("netsh int ip reset", "Reset IP configuration"),
        ("netsh winsock reset", "Reset Winsock catalog"),

        # Reset specific network components
        ("netsh int tcp reset", "Reset TCP settings"),
        ("netsh int ipv4 reset", "Reset IPv4 settings"),
        ("netsh int ipv6 reset", "Reset IPv6 settings"),

        # Clear DNS cache
        ("ipconfig /flushdns", "Flush DNS cache"),
        ("ipconfig /registerdns", "Re-register DNS"),

        # Release and renew IP
        ("ipconfig /release", "Release IP address"),
        ("ipconfig /renew", "Renew IP address"),
    ]

    # Add firewall reset if not skipped
    if not skip_firewall:
        commands.append(("netsh advfirewall reset", "Reset Windows Firewall"))

    # Add adapter info and restart
    commands.extend([
        ("ipconfig /all", "Display network adapter info"),
        (f'netsh interface set interface "{adapter_name}" disabled', f"Disable {adapter_name}"),
        (f'netsh interface set interface "{adapter_name}" enabled', f"Enable {adapter_name}"),


    ])