import os
import yaml
import requests
import json
import sys



def main(auth, org, ipamauth, dirName):
    # create a list of file and sub directories 
    # names in the given directory 
    listOfFile = os.listdir(dirName)
    allFiles = list()

    # Iterate over all the entries
    for entry in listOfFile:
        # Create full path
        fullPath = os.path.join(dirName, entry)
        # If entry is a directory then get the list of files in this directory 
        if os.path.isdir(fullPath) and os.path.isfile(fullPath + "/network.yaml") and os.path.isfile(fullPath + "/devices.yaml"):
 
            devices = parseDevices(fullPath)
            network = parseNetwork(fullPath)

            networkID = createNetwork(network, auth)

            addDevicesbySerial(networkID, devices, auth)

            updateDevices(devices, network, auth)

            bindTemplate(networkID, network, auth, org)

            vlanList = getVLANfromTemplate(network['template_name'])

            for vlan in vlanList:
                updateVLANfromIPAM(network, ipamauth, auth, networkID, vlan)

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

    return networkID

def parseDevices(fullPath):

    with open(fullPath + "/devices.yaml") as file:
        # The FullLoader parameter handles the conversion from YAML
        # scalar values to Python the dictionary format
        devices = yaml.load(file, Loader=yaml.FullLoader)


    return devices

def parseNetwork(fullPath):

    with open(fullPath + "/network.yaml") as file:
        # The FullLoader parameter handles the conversion from YAML
        # scalar values to Python the dictionary format
        network = yaml.safe_load(file)


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
            

            return None
 
    addressID = str(subnets[-1]['id'])


    
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


    return None

def addDevicesbySerial(networkID, devices, auth):
    
    url = "https://api-mp.meraki.com/api/v1/networks/"+ networkID +"/devices/claim"
    
    for device in devices:
        serial = devices[device]['serial_no']


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


auth=sys.argv[1]
org=sys.argv[2]
ipamauth=sys.argv[3]
main(auth, org, ipamauth, './network/branches')
