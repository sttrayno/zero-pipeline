import os
import yaml
import requests
import json
from rich.console import Console
from rich.progress import track
from rich.markdown import Markdown
from time import sleep
import sys


rc = Console()

def main(auth, org, ipamauth, dirName):
    # create a list of file and sub directories 
    # names in the given directory 
    listOfFile = os.listdir(dirName)
    allFiles = list()

    # Iterate over all the entries
    for entry in listOfFile:
        # Create full path
        fullPath = os.path.join(dirName, entry)
        if os.path.isdir(fullPath):      
            md= Markdown("# Moving to directory: " + fullPath)
            rc.print(md)
        # If entry is a directory then get the list of files in this directory 
        if os.path.isdir(fullPath) and os.path.isfile(fullPath + "/network.yaml") and os.path.isfile(fullPath + "/devices.yaml"):
            rc.print("Artifacts all found... Going on to create/verify the network...", style = "green ")
          
            devices = parseDevices(fullPath)
            network = parseNetwork(fullPath)

            md= Markdown("# Attemping to create network: " + network['network_name'])
            
            rc.print(md)

            networkID = createNetwork(network, auth)

            rc.print("Adding devices to the network...", style = "green")
            addDevicesbySerial(networkID, devices, auth)
            rc.print("Added devices to the network...", style = "green bold")

            rc.print("Updating devices with details...", style = "green")
            updateDevices(devices, network, auth)
            rc.print("Updated devices with details...", style = "green bold")

            rc.print("Binding a template to the network...", style = "green")
            bindTemplate(networkID, network, auth, org)
            rc.print("Bound a template to the network...", style = "green bold")

            rc.print("Getting list of VLANs for the template...", style = "yellow")
            vlanList = getVLANfromTemplate(network['template_name'])
            rc.print("Template has " + str(len(vlanList)) + " VLANs. Moving on to assign these from the IPAM if required...", style = "yellow")

            rc.print("Updating IP addressing from IPAM...", style = "green")

            for vlan in vlanList:
                updateVLANfromIPAM(network, ipamauth, auth, networkID, vlan)
            rc.print("Updated IP addressing from IPAM for all...", style = "green bold")

            md= Markdown("### Pipeline complete for network: " + network['network_name'])
            rc.print(md)

        elif os.path.isdir(fullPath):
            rc.print("Directory exists but does not have complete definitions... Skipping", style = "orange1 italic")

def createNetwork(network, auth):

    url = "https://api-mp.meraki.com/api/v1/organizations/" + org + "/networks"

    headers = {
    'Accept': '*/*',
    'X-Cisco-Meraki-API-Key': auth
    }

    payload ={}

    response = requests.request("GET", url, headers=headers, data=payload)

    existingnetworks = json.loads(response.text.encode('utf8'))

    for existingnetwork in existingnetworks:
        if existingnetwork['name'] == network['network_name']:
            networkID = existingnetwork['id']
            rc.print("Network:" + existingnetwork['name'] + " already exists... moving on to ensure state...", style = "orange1 italic")
            return networkID

    url = "https://api-mp.meraki.com/api/v1/organizations/" + org + "/networks"

    payload = "{\n    \"name\": \""+ network['network_name'] +"\",\n    \"productTypes\": [\n        \"appliance\",\n        \"switch\",\n        \"wireless\"\n    ],\n    \"timeZone\": \"" + network['timezone'] + "\"\n}"
    headers = {
      'Content-Type': 'application/json',
      'X-Cisco-Meraki-API-Key': auth
    }
        
    response = requests.request("POST", url, headers=headers, data = payload)
    parsed_json = (json.loads(response.text.encode('utf8')))
    networkID = parsed_json['id']
    rc.print("Created network container... now moving onto configure the network...", style = "green bold")

    return networkID

def parseDevices(fullPath):

    with open(fullPath + "/devices.yaml") as file:
        # The FullLoader parameter handles the conversion from YAML
        # scalar values to Python the dictionary format
        devices = yaml.load(file, Loader=yaml.FullLoader)
        for step in track(range(100), description="parsing device.yaml in the " + fullPath + " directory...", style = "yellow"):
            sleep(0.001)

    return devices

def parseNetwork(fullPath):

    with open(fullPath + "/network.yaml") as file:
        # The FullLoader parameter handles the conversion from YAML
        # scalar values to Python the dictionary format
        network = yaml.load(file, Loader=yaml.FullLoader)
        for step in track(range(100), description="parsing network.yaml in the " + fullPath + " directory...", style = "yellow"):
            sleep(0.01)

    return network

##### Need to implement yaml linting on artifacts

def updateDevices(devices, network, auth):

    for item in devices:
        
        serial = devices[item]['serial_no']
        type = devices[item]['device_type']
        address = devices[item]['address']

        deviceName = network['network_name'] + "_" + type
        url = "https://api-mp.meraki.com/api/v1/devices/" + serial

        payload = "{\n    \"name\": \"" + deviceName + "\",\n    \"address\": \"" + address +"\",\n    \"moveMapMarker\": \"True\"\n}"
        headers = {
        'Content-Type': 'application/json',
        'X-Cisco-Meraki-API-Key': auth
        }

        response = requests.request("PUT", url, headers=headers, data = payload)

        return None

def bindTemplate(networkID, network, auth, org):


    url = "https://api.meraki.com/api/v0/organizations/" + org + "/configTemplates"

    payload={}
    headers = {
    'Accept': '*/*',
    'X-Cisco-Meraki-API-Key': '6a572db444bffb6bbf5cd68011e745f217e36121'
    }

    response = requests.request("GET", url, headers=headers, data=payload)

    templates = (json.loads(response.text.encode('utf8')))
   
    for template in templates:
        if template['name'] == network['template_name']:
            templateID = template['id']


    url = "https://api-mp.meraki.com/api/v1/networks/"+ networkID +"/bind"

    payload = "{\n    \"configTemplateId\": \""+ templateID +"\",\n    \"autoBind\": \"False\"\n}"
    headers = {
      'Content-Type': 'application/json',
      'X-Cisco-Meraki-API-Key': auth
    }

    response = requests.request("POST", url, headers=headers, data = payload)
        
    return None

def updateVLANfromIPAM(network,ipamauth,auth,networkID,vlanId):

    parent = ""
    vlanName = ""

    if vlanId == 10:
        parent = "3"
        vlanName = "Branch"
    elif vlanId == 20:
        parent = "54"
        vlanName = "Service"
    else:
        rc.print("No IPAM range exists, skipping this and will let Dashboard assign IP...", style="red bold")
        return None
        
    
    url = "https://3.223.3.203/v1/ipam/address/" + parent + "/children"

    payload={}
    headers = {
    'Content-Type': 'application/json',
    'X-NSONE-Key': ipamauth
    }

    response = requests.request("GET", url, headers=headers, data=payload, verify=False)

    subnets = json.loads(response.text)

    for subnet in subnets:
        if subnet['name'] == network['network_name']:
            rc.print("Addressing already exists for vlan " + str(vlanId) + " moving to ensuring network is in desired state...", style = "orange1")
            url = "https://api.meraki.com/api/v0/networks/" + networkID + "/vlans/" + str(vlanId)
    
            dgw = str(subnet['prefix'])[:-5]
            dgw = str(dgw)  
            dgw = dgw + ".254"

            payload = (
                '{"name":"'
                + vlanName
                + '", "applianceIp":"'
                + dgw
                + '","subnet":"'
                + subnet['prefix']
                + '"}'
            )

            headers = {
            'Content-Type': 'application/json',
            'X-Cisco-Meraki-API-Key': auth
            }

            response = requests.request("PUT", url, headers=headers, data=payload)
            
            rc.print("Network is in desired addressing scheme for vlan " + str(vlanId) +"...", style = "green bold")

            return None
 
    addressID = str(subnets[-1]['id'])

    rc.print("Addressing does not exist for vlan: " + str(vlanId) + " Creating addressing in IPAM now...", style = "green")

    
    url = "https://3.223.3.203/v1/ipam/address/" + addressID + "/adjacent"
    
    response = requests.request("GET", url, headers=headers, data=payload, verify=False)
    
    response = json.loads(response.text)

    nextSubnet = response['prefix']
    

    url = "https://3.223.3.203/v1/ipam/address"
    payload = (
        '{"network_id":1, "parent_id":'
        + parent
        + ',"prefix":"'
        + nextSubnet
        + '","name":"'
        + network['network_name']
        + '","status":"assigned"}'
    )

    response = requests.request("PUT", url, headers=headers, data=payload, verify=False)

    rc.print("Subnet reserved and assigned for: " + str(vlanId) + " moving onto applying this to the network if required...", style = "green")
        

    url = "https://api.meraki.com/api/v0/networks/" + networkID + "/vlans/" + str(vlanId)
    
    dgw = nextSubnet[:-5]
    dgw = str(dgw)  
    dgw = dgw + ".254"

    payload = (
        '{"name":"'
        + vlanName
        + '", "applianceIp":"'
        + dgw
        + '","subnet":"'
        + nextSubnet
        + '"}'
    )

    headers = {
    'Content-Type': 'application/json',
    'X-Cisco-Meraki-API-Key': auth
    }

    response = requests.request("PUT", url, headers=headers, data=payload)

    rc.print("Network addressing configured for vlan: " + str(vlanId), style = "green bold")

    return None

def addDevicesbySerial(networkID, devices, auth):
    
    url = "https://api-mp.meraki.com/api/v1/networks/"+ networkID +"/devices/claim"
    
    for device in devices:
        serial = devices[device]['serial_no']

        rc.print("Ensuring device: " + devices[device]['device_name'] + " at " + devices[device]['address'] + " is on the network...",style = "green")

        payload = "{\n    \"serials\": [\n        \"" + serial + "\"\n    ]\n}"
        headers = {
          'Content-Type': 'application/json',
          'X-Cisco-Meraki-API-Key': auth
        }

        response = requests.request("POST", url, headers=headers, data = payload)

        return None

def getVLANfromTemplate(template_name):

    url = "https://api.meraki.com/api/v0/organizations/" + org + "/configTemplates"

    payload={}
    headers = {
    'Accept': '*/*',
    'X-Cisco-Meraki-API-Key': auth
    }

    response = requests.request("GET", url, headers=headers, data=payload)

    templates = (json.loads(response.text.encode('utf8')))
   
    for template in templates:
        if template_name == template['name']:
            templateID = template['id']

    url = "https://api.meraki.com/api/v0/networks/" + templateID + "/vlans"

    payload={}
    headers = {
    'Accept': '*/*',
    'X-Cisco-Meraki-API-Key': auth
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    vlans = json.loads(response.text.encode('utf8'))
    vlanList =[]
    for vlan in vlans:
        vlanList.append(vlan['id'])    

    return vlanList


if len(sys.argv) !=4:
    rc.print("This script needs 3 arguments to run in the fomat of 'auth' 'org' 'ipamauth'", style = "red")
else:
    auth=sys.argv[1]
    org=sys.argv[2]
    ipamauth=sys.argv[3]
    main(auth, org, ipamauth, './network/branches')