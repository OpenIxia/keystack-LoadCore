"""
This library file is used for reconfiguring LoadCore configurations

"""
def reassignAgents(mainObj, loadCoreObj, testcaseParams=None):
    """
    This function expects all the LoadCore agents and nodes to 
    have a specific value already defined in a ConfigParameters yml file.
  
    Parameters
       mainObj <obj>: The main object 
       loadCoreObj <obj>: The loadcore MW object.
       testcaseParams <dict list>: Params in a list.

    Example
       agentsDict = {'ran':  [{'agent':agent1Ip, 'passthroughDevice':'none', 'n2':agent1IpInterface,
                            'n3':agent1IpInterface, 's1':agent1IpInterface,
                            's1u':agent1IpInterface, 'n26':agent1IpInterface, 's6a':agent1IpInterface,
                            's5c':agent1IpInterface,'s5u':agent1IpInterface, 's11':agent1IpInterface}],
                  'amf':  [{'agent':agent2Ip, 'n2':agent2IpInterface, 'namf':agent2IpInterface,
                            'n26':agent2IpInterface}],
                  'ausf': [{'agent':agent2Ip, 'nausf':agent2IpInterface}],
                  'udm':  [{'agent':agent2Ip, 'nudm':agent2IpInterface, 's6a':agent2IpInterface}],
                  'pcf':  [{'agent':agent2Ip, 'npcf':agent2IpInterface, 'rx':agent2IpInterface}],
                  'udr':  [{'agent':agent2Ip, 'nudr':agent2IpInterface}],
                  'smf':  [{'agent':agent2Ip, 'n4':agent2IpInterface, 'nsmf':agent2IpInterface,
                            's5c':agent2IpInterface, 's11':agent2IpInterface}],
                  'upf':  [{'agent':agent2Ip, 'n3':agent2IpInterface, 'n4':agent2IpInterface, 'n6':'none',
                            'n9':agent2IpInterface}]
    }
    """
    loadCoreObj.logInfo('ReconfigureLoadCore.py function: reassignAgents')
    loadCoreObj.assignAgents(testcaseParams[0]['value']['agentsDict'])

def reassignAgentsFullcore(mainObj, loadCoreObj, testcaseParams=None):
    """
    Parameters
       loadCoreObj <obj>: The loadcore MW object.
       testcaseParams <dict list>: Params in a list. The testcase key 'configs' params
       
    Four methods to assign agent to 5G nodes:
        
        1. agentsDict[node] = self.Agent1 
           it will use the agent's first test interface
        
        2. agentsDict[node] = [{'agent': self.Agent2, 'n3': 'ens160', 'n4': 'ens160', 'n6': 'none' , 'n9': 'ens160'}]
           it will assign 'agent' to the node as described in the dict
        
        3. agentsDict[node] = [(self.Agent1, 'ens192')]
           it will use the exact test interface (ens192)
        
        4. agentsDict[node] = [self.Agent1, self.Agent2]
           agentsDict[node] = [(self.Agent2, 'ens192'),(self.Agent1, 'ens160')]
           this is used to assign multiple agents on every node. It will use the first interface.
           Can be used also as tuple: assign first agent with a specific interface, assign second with specific interface. 
    
    Notes: Calling helper function reassignAgents() to construct this agentsDict using the testcaseDict param. 
           Then the helper function reassignAgents() calls assignAgents() with the agentsDict to remap agents.
           The testcase yml file should have the followings:
             
           configs:
             reassignAgentNodes:
                ran: {nodes: [172.16.1.14]}                          
                dn:  {nodes: [172.16.1.41, lcNodesAndInterfaces: [{n6: ens33}] ]}
                amf: {nodes: [172.16.1.41]}
                nrf: {nodes: [172.16.1.41]}
                udm: {nodes: [172.16.1.41]}
                pcf: {nodes: [172.16.1.41]}
                udr: {nodes: [172.16.1.41]}
                smf: {nodes: [172.16.1.41]}
                upf: {nodes: [172.16.1.41]}
                ausf: {nodes: [172.16.1.41]}
                nssf: {nodes: [172.16.1.41]}
        
        # This is how the assignAgents() function requires the agentsDict. 
        agentsDict = dict()
        agentsDict['ran'] = ['172.16.1.14']
        agentsDict['dn'] =  [{'agent': '172.16.1.41', 'n6': 'ens33'}]
        agentsDict['nrf'] = ['172.16.1.14']
        agentsDict['udm'] = ['172.16.1.14']
        agentsDict['pcf'] = ['172.16.1.14']
        agentsDict['udr'] = ['172.16.1.14']
        agentsDict['smf'] = ['172.16.1.14']
        agentsDict['upf'] = ['172.16.1.14']
        agentsDict['amf'] =  ['172.16.1.14'] 
        agentsDict['ausf'] = ['172.16.1.14']
        agentsDict['nssf'] = ['172.16.1.14']

        # Reassign Agents
        loadCoreObj.assignAgents(agentsDict)
    """
    loadCoreObj.logInfo('ReconfigureLoadCore.py function: reassignAgentsFullCore')

    agent1Ip = mainObj.moduleProperties['envParams']['agents'][0]['agent']['ip']
    agent2Ip = mainObj.moduleProperties['envParams']['agents'][1]['agent']['ip']

    agentsDict = {'ran':  [agent1Ip],
                  'amf':  [agent2Ip],
                  'nrf':  [agent2Ip],
                  'ausf': [agent2Ip],
                  'smsf': [agent2Ip],
                  'udm':  [agent2Ip],
                  'pcf':  [agent2Ip],
                  'udr':  [agent2Ip],
                  'smf':  [agent2Ip],
                  'upf':  [agent2Ip],
                  'dn':   [agent2Ip],
                  'nssf': [agent2Ip],
    }
        
    loadCoreObj.assignAgents(agentsDict)
    
def changeNetworkSettings(mainObj, loadCoreObj, testcaseParams):
    """
    Reconfigure network settings on agents
    
    networkSettings = [{'agentIp': '172.16.1.14', 'interface': 'ens33', 'portCapture': True, 'sriov': False},
                       {'agentIp': '172.16.1.41', 'interface': 'ens33', 'portCapture': True, 'sriov': False}]
                       
    Parameters
       mainObj <obj>: The main keystack object containing all test details.
       loadCoreObj <obj>: The loadcore MW object.
       testcaseParams <dict>: The testcase keyword 'configParams' params

       agentIp <str>
       interface <str>
       portCapture <bool>
       networkStack <str>: options: dpdk, linuxStack, ixStack
       sriov <bool>
    """
    loadCoreObj.logInfo('ReconfigureLoadCore function: changeNetworkSettings')

    for net in testcaseParams[0]['value']['networkSettings']:
        # Example: Change: 172.16.1.14 ens160 True dpdk
        loadCoreObj.changeNetworkSettings(net['agentIp'], net['interface'],
                                          capture=net.get('portCapture', False),
                                          networkStack=net.get('networkStack', 'linuxStack'),
                                          sriov=net.get('sriov', False))

def configSustainTime(mainObj, loadCoreObj, testcaseParams):
    """
    Configure the test sustaining time
    
    Parameters
       loadCoreObj <obj>: The loadcore MW object.
       testcaseParams <dict>: The testcase key 'configs' params
    """
    sustainTestingTime = None
    for param in testcaseParams:
        if param['paramName'] == 'sustainTestingTime':
            sustainTestingTime = param['value']

    if sustainTestingTime:
        loadCoreObj.configSustainTime(sustainTestingTime)
    else:
        loadCoreObj.logError(f'reconfigLoadCore: No sustainTestingTime paramName found in ConfigParameters file')
    
def interfaceConnectivity(mainObj, loadCoreObj, testcaseParams):
    """
    Configure nodes interface connectivity settings
    
    Parameters
       loadCoreObj <obj>: The loadcore MW object.
       testcaseParams <dict>: The testcase key 'configs' params

    Examples:
       In the MW GUI:
          - Click on any of the nodes
          - Open RANGES
          - Select "N2 Interface Settings"
          - Configure the agent's IP address 

          For the eth interface, go back out to the MW main page:
             Note: Use ChangeNetworkSettings() to automate this configuration
               - Click on the node's green icon
               - Select the node and eth interface
 
       ran: [{'agent': '20.0.0.176', 'n2': 'eth1'}, {'agent': '20.0.0.160', 'n3': 'eth1'}],
       amf: [{'agent': '20.0.0.225', 'n2': 'eth1'}],
       upf: [{'agent': '20.0.0.18', 'n3': 'eth1'}]    
    """
    loadCoreObj.interfaceConnectivity()
      
      
