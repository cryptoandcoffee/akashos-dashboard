from flask import Flask, render_template, request, jsonify, send_file, url_for, flash, redirect, Markup
from flask_cors import CORS
from io import BytesIO
import subprocess
import os
import socket
import re
import requests
import json
import platform
import cpuinfo
import functools
import time

app = Flask(__name__)
CORS(app) # This will enable CORS for all routes

app.secret_key = 'my_secret_key'
port_check_api = 'http://193.29.62.183:8081/check-port'

os.environ['KUBECONFIG'] = '/var/snap/microk8s/current/credentials/client.config'
# Custom cache dictionary to store the cached results
cache = {}

def get_cached_result(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        key = (func.__name__, args, frozenset(kwargs.items()))

        # Check if the result is already cached and not expired
        if key in cache and time.time() - cache[key][1] <= 3600:
            return cache[key][0]

        # Invoke the function and store the result in the cache
        result = func(*args, **kwargs)
        cache[key] = (result, time.time())
        return result

    return wrapper

@get_cached_result
def get_balance(account_address):
    response = requests.get(f'https://akash-api.global.ssl.fastly.net/cosmos/bank/v1beta1/balances/{account_address}')
    data = response.json()
    # print(data)

    balances = data.get('balances', [])
    if len(balances) > 0:
        for balance in balances:
            amount = balance.get('amount')
            if amount:
                amount = int(amount)  # Convert amount to an integer
                return amount / 1000000  # Divide amount by 1,000,000
    return 0  # Set balance to 0 if no balance is found

@get_cached_result
def get_location(public_ip):
    try:
        response = requests.get(f'http://ip-api.com/json/{public_ip}')
        data = response.json()
        return data['regionName']
    except:
        return "Unknown"

@get_cached_result
def get_public_ip():
    services = [
        'https://checkip.amazonaws.com'
    ]

    for service in services:
        try:
            response = requests.get(service)
            if response.status_code == 200:
                return response.text.strip()
        except requests.RequestException:
            pass
    return None

@get_cached_result
def get_local_ip():
    try:
        # Run the ifconfig command to get the network interfaces information
        output = subprocess.check_output(["ifconfig"]).decode("utf-8")

        # Use regular expressions to find the local IP address
        ip_regex = r"inet (?:addr:)?([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"
        match = re.search(ip_regex, output)
        if match:
            return match.group(1)
        else:
            return None
    except subprocess.CalledProcessError:
        return None


@app.route('/', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        # Save the variables from the form
        variables = request.form.to_dict()
        with open('/home/akash/variables', 'w') as f:
            for key, value in variables.items():
                f.write(f'{key}={value}\n')

        flash('Variables saved successfully. Provider restart is required.', 'success')
        return redirect(url_for('dashboard'))

    else:
        # Read the variables file
        with open('/home/akash/variables', 'r') as f:
            variables = dict(line.strip().split('=') for line in f)

        # If 'ACCOUNT_ADDRESS' is not in variables, return or handle it properly
        if 'ACCOUNT_ADDRESS' not in variables:
            return "Account address not found in variables."

        account_address = variables['ACCOUNT_ADDRESS']
        print(account_address)
        balance = get_balance(account_address)
        print(balance)
        #balance = get_balance(variables)
        # Read the DNS records file
        with open('/home/akash/dns-records.txt', 'r') as f:
            dns_records = f.read()

        # Read the firewall ports file
        with open('/home/akash/firewall-ports.txt', 'r') as f:
            firewall_ports = f.read()

        with open('/home/akash/wallet_qr_code.txt', 'r') as f:
            qr_code = f.read()

        local_ip = get_local_ip()
        public_ip = get_public_ip()
        info = cpuinfo.get_cpu_info()
        location = get_location(public_ip)

#	response = requests.get(f'http://ip-api.com/json/{public_ip}')
#	data = response.json()



        if 'AMD' in info['brand_raw']:
            processor = 'AMD'
        elif 'Intel' in info['brand_raw']:
            processor = 'Intel'
        else:
            processor = 'Unknown'

        # Render the dashboard page with the variables, DNS records, firewall ports, and port status
        return render_template('dashboard.html', variables=variables, dns_records=dns_records, firewall_ports=firewall_ports, local_ip=local_ip, public_ip=public_ip, qr_code=qr_code, processor=info['brand_raw'], region=location, balance=balance)

@app.route('/wallet', methods=['GET', 'POST'])
def wallet():
    if request.method == 'POST':
        # Handle wallet setup or import
        mnemonic = request.form.get('mnemonic')
        # Use the mnemonic to setup the wallet using Akash CLI
        subprocess.run(["akash", "keys", "add", "default", "--recover", mnemonic])
    else:
        # Display wallet information
        # Use Akash CLI to get wallet information
        wallet_info = subprocess.check_output(["akash", "keys", "show", "default"])
        balance = subprocess.check_output(["akash", "query", "bank", "balances", "default"])
        return jsonify(wallet_info=wallet_info, balance=balance)

@app.route('/domain', methods=['GET', 'POST'])
def domain():
    if request.method == 'POST':
        # Handle domain setup
        domain = request.form.get('domain')
        # Use the domain to setup the provider using Akash CLI
        subprocess.run(["akash", "provider", "create", domain])
    else:
        # Display domain information
        # Use Akash CLI to get domain information
        domain_info = subprocess.check_output(["akash", "provider", "show"])
        return jsonify(domain_info=domain_info)

@app.route('/dns', methods=['GET', 'POST'])
def dns():
    if request.method == 'POST':
        # Handle DNS setup
        dns_records = request.form.get('dns_records')
        # Use the DNS records to setup DNS
        subprocess.run(["dns-setup-command", dns_records])
    else:
        # Display DNS information
        # Use a DNS lookup tool to get DNS information
        dns_info = subprocess.check_output(["dns-lookup-command"])
        return jsonify(dns_info=dns_info)

@app.route('/firewall', methods=['GET', 'POST'])
def firewall():
    if request.method == 'POST':
        # Handle firewall setup
        firewall_rules = request.form.get('firewall_rules')
        # Use the firewall rules to setup the firewall
        subprocess.run(["firewall-setup-command", firewall_rules])
    else:
        # Display firewall information
        # Use a firewall inspection tool to get firewall information
        firewall_info = subprocess.check_output(["firewall-inspection-command"])
        return jsonify(firewall_info=firewall_info)

@app.route('/ports', methods=['GET'])
def ports():
    # Check if ports are reachable and display the information
    ports_info = subprocess.check_output(["port-check-command"])
    return jsonify(ports_info=ports_info)

@app.route('/download_key', methods=['GET'])
def download_key():
    # Handle private key download
    # Use Akash CLI to export the private key
    # subprocess.run(["akash", "keys", "export", "default"])
    return send_file('/home/akash/key.pem', as_attachment=True)

@app.route('/download_variables', methods=['GET'])
def download_variables():
    # Handle private key download
    # Use Akash CLI to export the private key
    # subprocess.run(["akash", "keys", "export", "default"])
    return send_file('/home/akash/variables', as_attachment=True)

@app.route('/download_kubeconfig', methods=['GET'])
def download_kubeconfig():
    with open('/var/snap/microk8s/current/credentials/client.config', 'r') as f:
        kubeconfig = f.read()

    local_ip = get_local_ip()
    kubeconfig = kubeconfig.replace('https://127.0.0.1:16443', f'https://{local_ip}:16443')

    kubeconfig_io = BytesIO()
    kubeconfig_io.write(kubeconfig.encode())
    kubeconfig_io.seek(0)

    return send_file(kubeconfig_io, as_attachment=True, attachment_filename='kubeconfig-akashos')

if __name__ == '__main__':
    app.run(debug=True)
