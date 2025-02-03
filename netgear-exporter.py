import requests
import re
import time
from bs4 import BeautifulSoup
from requests.auth import HTTPBasicAuth
from prometheus_client import start_http_server, Gauge

# Configuration
username = 'admin'
password = 'password'
http_server_port = 8000
scrape_interval = 60  # Interval in seconds to scrape data

login_url = 'http://192.168.100.1/'
modem_info_url = 'http://192.168.100.1/RouterStatus.htm'
modem_data_url = 'http://192.168.100.1/DocsisStatus.htm'

# Prometheus metrics for modem information
modem_info_gauge = Gauge('modem_info', 'Modem Information', ['vendor', 'model', 'hardware_version', 'serial_number', 'mac_address', 'firmware_version', 'cm_ipv4_address'])
downstream_frequency_gauge = Gauge('downstream_frequency', 'Downstream Frequency', ['channel', 'mac_address'])
downstream_power_gauge = Gauge('downstream_power', 'Downstream Power', ['channel', 'mac_address'])
downstream_snr_gauge = Gauge('downstream_snr', 'Downstream SNR', ['channel', 'mac_address'])
upstream_power_gauge = Gauge('upstream_power', 'Upstream Power', ['channel', 'mac_address'])
upstream_frequency_gauge = Gauge('upstream_frequency', 'Upstream Frequency', ['channel', 'mac_address'])
upstream_symbol_rate_gauge = Gauge('upstream_symbol_rate', 'Upstream Symbol Rate', ['channel', 'mac_address'])

def scrape_and_update_metrics():
    # Scrape the data
    session = requests.Session()
    session.get(login_url, auth=HTTPBasicAuth(username, password))
    modem_info = session.get(modem_info_url, auth=HTTPBasicAuth(username, password))
    modem_data = session.get(modem_data_url, auth=HTTPBasicAuth(username, password))

    # Parse the HTML content
    modem_info_soup = BeautifulSoup(modem_info.text, 'html.parser')
    modem_data_soup = BeautifulSoup(modem_data.text, 'html.parser')

    # Extract all JavaScript code blocks containing the variables we need
    modem_info_tags = modem_info_soup.find_all('script', string=re.compile(r'tagValueList'))
    modem_data_tags = modem_data_soup.find_all('script', string=re.compile(r'InitDsTableTagValue'))

    # Initialize an array to store all tagValueList values
    modem_info_tag_value_lists = []
    modem_data_tag_value_lists = []

    # Iterate through all script tags and find all tagValueList occurrences
    for script in modem_info_tags:
        script_text = script.string
        tag_value_list_matches = re.findall(r"var tagValueList\s*=\s*'([^']+)'", script_text)
        for match in tag_value_list_matches:
            modem_info_tag_value_lists.append(match)

    for script in modem_data_tags:
        script_text = script.string
        tag_value_list_matches = re.findall(r"var tagValueList\s*=\s*'([^']+)'", script_text)
        for match in tag_value_list_matches:
            modem_data_tag_value_lists.append(match)

    # Extract modem information
    meta_description = modem_info_soup.find('meta', attrs={'name': 'description'})
    if meta_description:
        model_name = meta_description.get('content')
    else:
        model_name = 'Unknown'
        print("WARNING: CM model name not found")

    modem_info_raw = modem_info_tag_value_lists[0].split('|')
    vendor = "NETGEAR"
    hardware_version = modem_info_raw[0]
    serial_number = modem_info_raw[2]
    mac_address = modem_info_raw[4]
    firmware_version = modem_info_raw[1]
    cm_ipv4_address = modem_info_raw[6]

    # Update Prometheus metrics for modem information
    modem_info_gauge.labels(vendor=vendor, model=model_name, hardware_version=hardware_version, serial_number=serial_number, mac_address=mac_address, firmware_version=firmware_version, cm_ipv4_address=cm_ipv4_address).set(1)

    # Update Prometheus metrics for downstream channels
    downstream_bonded_channels_raw = modem_data_tag_value_lists[2].split('|')
    downstream_bonded_channels_raw = [v for v in downstream_bonded_channels_raw if v]
    num_channels = int(downstream_bonded_channels_raw[0])

    for i in range(num_channels):
        start_index = i * 9 + 1
        end_index = start_index + 8
        if end_index < len(downstream_bonded_channels_raw):
            channel_info = {
                'Channel': downstream_bonded_channels_raw[start_index],
                'Frequency': int(downstream_bonded_channels_raw[start_index + 4].replace(' Hz', '')),
                'Power': float(downstream_bonded_channels_raw[start_index + 5]),
                'SNR': float(downstream_bonded_channels_raw[start_index + 6])
            }
            downstream_frequency_gauge.labels(channel=channel_info['Channel'], mac_address=mac_address).set(channel_info['Frequency'])
            downstream_power_gauge.labels(channel=channel_info['Channel'], mac_address=mac_address).set(channel_info['Power'])
            downstream_snr_gauge.labels(channel=channel_info['Channel'], mac_address=mac_address).set(channel_info['SNR'])

    # Update Prometheus metrics for upstream channels
    upstream_bonded_channels_raw = modem_data_tag_value_lists[1].split('|')
    upstream_bonded_channels_raw = [v for v in upstream_bonded_channels_raw if v]
    num_channels = int(upstream_bonded_channels_raw[0])

    for i in range(num_channels):
        start_index = i * 7 + 1
        end_index = start_index + 6
        if end_index < len(upstream_bonded_channels_raw):
            channel_info = {
                'Channel': upstream_bonded_channels_raw[start_index],
                'Frequency': int(upstream_bonded_channels_raw[start_index + 5].replace(' Hz', '')),
                'Power': float(upstream_bonded_channels_raw[start_index + 6]),
                'SymbolRate': int(upstream_bonded_channels_raw[start_index + 4])
            }
            upstream_frequency_gauge.labels(channel=channel_info['Channel'], mac_address=mac_address).set(channel_info['Frequency'])
            upstream_power_gauge.labels(channel=channel_info['Channel'], mac_address=mac_address).set(channel_info['Power'])
            upstream_symbol_rate_gauge.labels(channel=channel_info['Channel'], mac_address=mac_address).set(channel_info['SymbolRate'])

# Start Prometheus HTTP server
start_http_server(http_server_port)
print("Prometheus metrics server started on port:", http_server_port)

# Main loop to periodically scrape data and update metrics
while True:
    scrape_and_update_metrics()
    time.sleep(scrape_interval)