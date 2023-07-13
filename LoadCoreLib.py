""" 
LoadCoreLib.py

DESCRIPTION:
   A framework that executes LoadCore .json config files, reconfiguration if necessary, 
   start test, get stat, download results and generate a test_summary.yml report.
   
   This framework reads a Yaml file that contains information on which .json file to load and
   which KPIs to analyze at runtime. 
   
   Each Yaml file represents a test case.  You could put all Yaml files in
   a folder and state the folder for the perameter -testcases and this will run all 
   Yaml testcase files inside the folder.
   
   RESULTS FOLDER:
        Each test gets its own top-level results folder with a timestamp:  Ex: KeysightTestResults_<timestamp>.
            - Each test case gets its own result folder
                - Each test has a test_summary.yml file, CSV and JSON KPI results and log file
            - mainDebugLog

PARAMETERS:
   -env:     Details on IP addresses, login credentials, global variables
   -testcases: A folder of yaml files. This script will run all yaml files in a folder.
               You could pass in more than one folder and you could mix folders and individual yaml files.

RECONFIGURATION:
   To modify configurations, create a python file and store all individual reconfigurations
   in its own function.  This main script will pass the main object to the reconfiguration file
   in order to call functions in LoadCoreMWAssistant.py.
   Look at this for sample: ReconfigureLoadCoreFiles/reconfigLoadCore.py
   In the testcase yaml file, all configurations go in the configs field:

    configs:
      reconfigureLoadCoreFiles:
        - /path/ReconfigurationScripts/reconfigLoadCore.py
        
      # Configuration details to support calling reassignAgents()
      agentsDict:
          ran: 172.16.1.14
          nrf: 172.16.1.14
          udm: 172.16.1.14
          pcf: 172.16.1.14
          udr: 172.16.1.14
          smf: 172.16.1.14
          upf: 172.16.1.14
          amf: 172.16.1.14
          ausf: 172.16.1.14
          nssf: 172.16.1.14
          dn:
          - agent: 172.16.1.41
              n6: ens33
                
      # Configuration details to support calling changeNetworkSettings()
      changeNetworkSettings: [{agentIp: 172.16.1.14, interface: ens33, portCapture: True},
                              {agentIp: 172.16.1.41, interface: ens33, portCapture: True}
                              ]
"""
import requests, sys, os, json, time, platform, re, yaml, subprocess, traceback
import datetime, shutil
from pprint import pformat, pprint
from keystackUtilities import readJson, writeToJson, getTimestamp, getDictItemFromList, makeFolder

# Disable SSL warnings
requests.packages.urllib3.disable_warnings()

# Disable non http connections.
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        
class Logger():
    def logMsg(self, msgType, msg, includeTimestamp=True):
        """
        Print message to stdout and append the message to a log file.

        Parameter
           msgType <str>: info|debug|error
           msg <str>: The message for stdout.
        """
        if includeTimestamp:
            timestamp = str(datetime.datetime.now()).split(' ')[1]
            stdout = f'\n{timestamp}: [{msgType}]: {msg}'
        else:
            stdout = msg
            
        print(stdout)
        self.writeToLogFile(msg=f'{stdout}\n', logType='a')
            
    def logInfo(self, msg, includeTimestamp=True):
        self.logMsg('info', msg, includeTimestamp=includeTimestamp)

    def logWarning(self, msg):
        self.logMsg('warning', msg)
        
    def logDebug(self, msg):
        self.logMsg('debug', msg)

    def logError(self, msg):
        self.logMsg('error', msg)                
        raise Exception(f'Aborting test: {msg}')

    # Note: self.debugLogFile is set in class MW()
    def writeToLogFile(self, msg, logType='a'):
        if self.debugLogFile:
            with open(self.debugLogFile, logType) as logFile:
                logFile.write(msg)


class Requests(Logger):
    def get_requests(self):
        if self.httpv2:
            s = requests.Session()
            s.mount(self.baseurl, HTTP20Adapter())
            s.verify = False
            return s
        else:
            return requests

    def get(self, url, params=None, headers=None, stream=False):
        if self.debugMode == False:
            self.logInfo(f'\nGET: {self.baseurl}{url}\nPARAMS: {params}')
        else:
            self.logInfo(f'\nGET: {self.baseurl}{url}\nPARAMS: {params}\nHEADERS: {headers}')
        
        response = self.get_requests().get('%s%s' % (self.baseurl, url), params=params, headers=headers, verify=False,
                                       stream=stream)

        self.logInfo(f'STATUS: {response.status_code}', includeTimestamp=False)
        return response

    def getInfoFromURL(self, url, params=None, headers=None):
        self.logInfo(f'\nGetInforFromUrl: {self.baseurl}{url}\nPARAMS: {params}')
        return self.get_requests().get('%s' % url, params=params, headers=headers, verify=False)

    def put(self, url, data, headers=None):
        if self.debugMode == False:
            self.logInfo(f'\nPUT: {self.baseurl}{url}\nDATA: {data}')
        else:
            self.logInfo(f'\nPUT: {self.baseurl}{url}\nDATA: {data}\nHEADERS: {headers}')
                
        response = self.get_requests().put('%s%s' % (self.baseurl, url), data=(None if data is None else json.dumps(data)),
                                       headers=headers, verify=False)

        self.logInfo(f'STATUS: {response.status_code}', includeTimestamp=False)
        return response

    def putText(self, url, data, headers=None):
        self.logInfo(f'\nPUTTEXT: {self.baseurl}{url}\nDATA: {data}')
        return self.get_requests().put('%s%s' % (self.baseurl, url), data=data, headers=headers, verify=False)

    def post(self, url, data=None, headers=None):
        if self.debugMode == False:
            self.logInfo(f'\nPOST: {self.baseurl}{url}\nDATA: {json.dumps(data)}\nHEADERS: {headers}')
        else:
            self.logInfo(f'\nPOST: {self.baseurl}{url}\nDATA: {json.dumps(data)}')
            
        response = self.get_requests().post('%s%s' % (self.baseurl, url), data=(None if data is None else json.dumps(data)),
                                        headers=headers, verify=False)
        self.logInfo(f'STATUS: {response.status_code}', includeTimestamp=False)
        return response

    def patch(self, url, data, headers=None):
        if self.debugMode == False:
            self.logInfo(f'\nPATCH: {self.baseurl}{url}\nDATA: {data}')
        else:
            self.logInfo(f'\nPATCH: {self.baseurl}{url}\nDATA: {data}\nHEADERS: {headers}')
            
        response = self.get_requests().patch('%s%s' % (self.baseurl, url),
                                         data=(None if data is None else json.dumps(data)), headers=headers,
                                         verify=False)
        
        self.logInfo(f'STATUS: {response.status_code}', includeTimestamp=False)
        return response

    def delete(self, url, headers=None):
        self.logInfo(f'\nDELETE: {self.baseurl}{url}')
        response = self.get_requests().delete('%s%s' % (self.baseurl, url), headers=headers, verify=False)
        self.logInfo(f'STATUS: {response.status_code}', includeTimestamp=False)
        return response

    def post_archive(self, url, data=None, headers=None):
        headers["Content-Type"] = "application/zip"
        return self.get_requests().post('%s%s' % (self.baseurl, url), data=(None if data is None else data),
                                        headers=headers, verify=False)
        
    def getS3(self, url, params=None, headers=None, stream=False):
        if MW.debugMode == False:
            self.logInfo(f'\nGET-AWS-S3: {url}\nPARAMS: {params}')
        else:
            self.logInfo(f'\nGET-AWS-S3: {url}\nPARAMS: {params}\nHEADERS: {headers}')
        
        response = self.get_requests().get(url, params=params, headers=headers, verify=False, stream=stream)
        self.logInfo(f'STATUS: {response.status_code}', includeTimestamp=False)
        return response

    def putS3(self, url, data, headers=None):
        self.logInfo(f'\nPUT-AWS-S3: {url}\nDATA: {data}\nHEADERS: {headers}')
        response = self.get_requests().put(url, data=data, headers=headers, verify=False)
        self.logInfo(f'STATUS: {response.status_code}', includeTimestamp=False)
        return response

    
class Utils(Requests):
    def getTimestamp(self):
       today = datetime.datetime.now()
       return today.strftime("%m-%d-%Y-%H:%M:%S")
    
    def waitForState(self, what, equalToWhat, timeout):
        while timeout > 0:
            try:
                self.logInfo(f'Utils:waitForState:  what={what}  equalToWhat={equalToWhat}')
                if what != equalToWhat:
                    self.logError('Utils:waitForState: %s != %s'.format(what, equalToWhat))
                    
                return True
            except:
                timeout -= 0.2
                time.sleep(0.2)
        else:
            print("Timed out after %s seconds" % (10 - timeout))
            return False

    def createFolder(self, fullPath):
        """
        Create a folder if it doesn't exists

        Parameter
           fullPath <str>: The full path and the folder name
        """
        if not os.path.exists(fullPath):
            #os.makedirs(fullPath)
            makeFolder(fullPath)

    def convertCsvFileToJsonFile(self, csvFilePath, jsonFilePath):
        import csv
        jsonArray = []

        #read csv file
        with open(csvFilePath, encoding='utf-8') as csvf: 
            #load csv file data using csv library's dictionary reader
            #csvReader = csv.DictReader(csvf)
            csvReader = csv.reader(csvf) 

            #convert each csv row into python dict
            for row in csvReader:
                #add this python dict to json array
                jsonArray.append(row)

        #convert python jsonArray to JSON String and write to file
        try:
            with open(jsonFilePath, 'w', encoding='utf-8') as jsonf: 
                jsonString = json.dumps(jsonArray, indent=4)
                jsonf.write(jsonString)

            os.chmod(jsonFilePath, 0o774)
            return True
        except Exception as errMsg:
            self.logWarning(f'convertCsvFileToJson failed: {errMsg}')
            return False
            
    def readCsvFile(self, csvFile):
        import csv
        with open(csvFile, mode='r', encoding='utf-8-sig') as file:
            csvContents = csv.DictReader(file)
            
            csvData = dict()

            for row in csvContents:
                csvData[row['Test No']] = dict()
                for key,value in row.items():
                    if key == '':
                        continue
                    
                    #print(f'key={key} value={value}')
                    valueList = []
                    for eachValue in value.split('\n'):
                        if eachValue == '':
                            continue
                        
                        valueList.append(eachValue)
                    
                    csvData[row['Test No']].update({key: valueList})
                    
        return csvData
 

class LoadCoreLicense(Logger):
    def __init__(self, licenseServerIp, port='7443', user='admin', password='admin', testcaseLogFile=None):
        self.licsenseServerIp = f'{licenseServerIp}:{port}'
        self.user = user
        self.password = password
        self.urlBase = f'https://{licenseServerIp}:{port}'
        self.headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        self.session = requests.session()
        
        # For Logger
        self.debugLogFile = testcaseLogFile
         
        # LoadCore license server doesn't return a token to use for future REST execution.
        # It uses persistant cookie.  The requests.session() will hold the sesssion
        try:
            self.connect()
        except Exception as errMsg:
            raise Exception(errMsg)
            
    def get(self, url, params=None, verify=False):
        self.logInfo(f'\nGET URL: {url}', includeTimestamp=False)
        self.logInfo(f'PARAMS: {params}', includeTimestamp=False)
        self.logInfo(f'HEADERS: {self.headers}', includeTimestamp=False)
        try:
            response = self.session.request('GET', url, params=params, headers=self.headers, verify=verify)
        except Exception as errMsg:
            raise Exception(f'LoadCoreLicense GET: {errMsg}')
        
        if response.status_code != 200:
            raise Exception(f'LoadCoreLicense() GET: Failed.')
        
        return response
        
    def post(self, url, data=None, verify=False):
        self.logInfo(f'\nPOST URL: {url}', includeTimestamp=False)
        self.logInfo(f'DATA: {data}', includeTimestamp=False)
        self.logInfo(f'HEADERS: {self.headers}', includeTimestamp=False)
        
        try:
            response = self.session.request('POST', url, data=data, headers=self.headers, verify=verify)
        except Exception as errMsg:
            raise Exception(f'LoadCoreLicense POST: {errMsg}')
        
        if response.status_code != 200:
            raise Exception(f'LoadCoreLicense() POST: Failed.')
        
        return response
      
    def connect(self):
        url = f'{self.urlBase}/rest/license/login'
        data = {'userid': self.user, 'password': self.password}
        try:
            self.post(url, data)
        except Exception as errMsg:
            return errMsg
 
    def getLicenseDetails(self):
        response = self.get(f'{self.urlBase}/rest/license/floatingStats')
        return response
    
    def showLicenseDetails(self):
        response = self.getLicenseDetails()
        pprint(response.json()['payload']['floatingFeatureStats'])
                             
    def checkForLicenses(self, requiredLicenses):
        """ 
        login to license server to get license avaialability
        
        POST https://<ip>:7443/rest/license/login data={'userid': 'admin', 'password': 'admin'}
        GET https://<ip>:7443/rest/license/floatingStats check the installedCount, availableCount.        
        """
        response = self.getLicenseDetails()
        
        licenseFailures = []
        if response.status_code == 200 and requiredLicenses:
            for eachRequiredLicense in requiredLicenses:
                licenseFeatureName = list(eachRequiredLicense.keys())[0]
                requiredLicenseCount = list(eachRequiredLicense.values())[0]
                for eachLicense in response.json()['payload']['floatingFeatureStats']:
                    if eachLicense['featureName'] == licenseFeatureName:
                        availableCount = int(eachLicense['availableCount'])
                        installedCount = int(eachLicense['installedCount'])
                        self.logInfo(f'\nLoadCore license is available: {eachLicense["featureName"]} available:{availableCount} installedCount={installedCount}')
                        if availableCount == 0:
                            licenseFailures.append({'RequiredLicenseFeatureName':licenseFeatureName,
                                                    'RequiredCount': requiredLicenseCount,
                                                    'availableCount': availableCount,
                                                    'installedCount': installedCount})
        return licenseFailures
        
                        
class MW(Utils):
    # These variables are for Logger and LoadCoreAssistantException
    debugMode = False
    debugLogFile = None
    
    def __init__(self, host='localhost', port=443, username='admin', password='admin',
                 authToken=None, licenseServer=None, protocol='https', login=True,
                 enablehttp2=False, logLevel='debug', debugMode=False, testcaseLogFile=None,
                 testcaseResultsFolder=None, testcaseName=None, keystackObj=None):
        """
        This class works in conjunction with runLoadCore.py
        
        Parameters
           testcasesLogFile <str>: A testcase log file must be created already. Full path to the log file name.
           testcaseResultsFolder <str>: Full path to the folder for all result files to be stored.
           testcaseName <str>: Used for naming the PDF report and CSV file.
           login <bool>: Sometimes a LoadCore private build has no login. In this case, don't abort test if connection failed
        """
        self.keystackObj = keystackObj
        self.host = host
        self.port = port
        self.protocol = protocol
        self.process = None
        self.baseurl = '%s://%s:%d' % (self.protocol, self.host, self.port)
        self.httpv2 = enablehttp2
        self.licenseServer = licenseServer
        self.licenseServerType = keystackObj.moduleProperties['envParams']['licenseServerType']
        self.logLevel = logLevel
        self.sessionId = None
        self.username = username
        self.password = password
        self.connectedSuccessfully = False
        
        if login:
            # Sometimes a LoadCore private build has no login.
            # In this case, don't abort test if connection failed
            apiKey = self.getToken()
        else:
            self.connectedSuccessfully = True
            apiKey = None
          
        self.headers = {'authorization': apiKey}
        self.debugMode = debugMode
        self.debugLogFile = testcaseLogFile
        self.testcaseResultsFolder = testcaseResultsFolder
        self.testcaseName = testcaseName
        self.testId = None

    def getToken(self):
        try:
            apiPath = '/auth/realms/keysight/protocol/openid-connect/token'
            self.headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            payload = { "grant_type" : "password", "username" : self.username, "password": self.password, "client_id": "clt-wap" }
            # use requests.post because payload is not json format as it is used in self.post()
            response = requests.post(self.baseurl + apiPath, data=payload, headers=self.headers, verify=False)
            print('auth_token: {}'.format(response.json()['access_token']))
            self.connectedSuccessfully = True
        except Exception as e:                
            self.logError(f'getToken: Connecting to Loadcore MW failed: {self.baseurl}')
            return None
        
        return response.json()["access_token"]

    def newSession(self, configName=None, configID=None, configJson=None, configArchive=None,
                   statusCode=201, sessionType='fullCore'):
        """
        :param configName:
        :param configID: specify a configID to create a new config and load the config with configID
        :param config: config in json format that will be uploaded and attached to the new session
        :return: new session ID
        """

        if sessionType == "fullCore":
            configType = "wireless-fullcore-config"

        if (configName == None and configJson == None and configID == None and configArchive == None):
            self.config = {"ConfigUrl": configType}
        elif configID != None:
            self.config = {"ConfigUrl": configID}
        elif (configName != None):
            # in this case create a new config by loading a specified config name
            self.config = self.selectConfig(configName)
            uploadedConfig = self.uploadConfig(config=self.config)
            self.config = {"ConfigUrl": uploadedConfig[0]['id']}
        elif (configJson != None):
            uploadedConfig = self.uploadConfig(config=configJson)
            self.config = {"ConfigUrl": uploadedConfig[0]['id']}
        elif configArchive != None:
            uploadedConfig = self.uploadConfig(configArchive=configArchive)
            self.config = {"ConfigUrl": uploadedConfig[0]['id']}
        else:
            self.logError("NewSession: Unhandled case")

        response = self.post('/api/v2/sessions', self.config, headers=self.headers)

        if response.status_code == 201:
            self.logDebug(pformat(response.json()))
            self.sessionId = response.json()[0]['id']
            if 'wireless' not in self.sessionId:
                self.logError('Failed to create new session: {}'.format(self.sessionId))

            return response
        else:
            self.logError(f'newSession failed. Connecting to MW status code={response.status_code}')

    def deleteSession(self,  statusCode=204):
        if self.sessionId is None:
            return
        
        response = self.delete('/api/v2/sessions/{0}'.format(self.sessionId), headers=self.headers)
        # print response
        assert response.status_code == statusCode
        if '200' in str(response.status_code):
            assert (True if self.sessionId not in self.getAllSessions() else False)
            return response
        
        elif '204' in str(response.status_code):
            assert (True if self.sessionId not in self.getAllSessions() else False)
            return response
        
        else:
            self.logDebug(pformat(response))
            return response.status_code

    def getAllSessions(self):
        response = self.get('/api/v2/sessions', headers=self.headers)
        assert response.status_code == 200
        sessions = []
        for item in response.json():
            sessions.append(item['id'])

        return sessions

    def getSessionInfo(self, status_code=200):
        response = self.get('/api/v2/sessions/{0}'.format(self.sessionId), headers=self.headers)
        assert response.status_code == status_code
        return response.json()

    def getSessionStatus(self):
        response = self.get('/api/v2/sessions/{0}/test'.format(self.sessionId), headers=self.headers)
        assert response.status_code == 200
        return response.json()['status']

    def isSessionStarted(self):
        response = self.get('/api/v2/sessions/{0}/test'.format(self.sessionId), headers=self.headers)
        assert response.status_code == 200
        return True if response.json()['status'] == 'Started' else False

    def pickExistingSession(self, wildcard):
        try:
            self.assertGreater(self.newSessionID, 0)
            return self.newSessionID
        except:
            allSessions = self.getAllSessions()
            for session in allSessions:
                if wildcard in session:
                    return session

    def uploadConfig(self, config=None, configArchive=None, statusCode=201):
        """
        :param config: in json format
        :return:
        """
        currentTestcase = self.keystackObj.moduleSummaryData['currentlyRunning']
        
        if config != None:
            response = self.post('/api/v2/configs', data=config, headers=self.headers)
            # self.logger.debug(pformat(response.content))
            #self.logger.debug(pformat(response.reason))
            #self.testcase.assertEquals(response.status_code, statusCode)
            return response.json()
        
        if configArchive != None:
            with open(configArchive, 'rb') as f:
                # Replace f here
                if 'modifyLoadCoreJsonConfigs' in self.keystackObj.testcaseDict[currentTestcase]:
                    # read the loadcore json config in memory and replace
                    # zip: /opt/KeystackTests/Modules/LoadCore/ExportedConfigs/sample_fullCore.zip
                    for eachChange in self.keystackObj.testcaseDict[currentTestcase]['modifyLoadCoreJsonConfigs']:
                        try:
                            f.update(eachChange)
                        except Exception as errMsg:
                            raise Exception(f'uploadConfig(): Modifying json config failed: {errMsg}')
                            
                response = self.post_archive('/api/v2/configs',data=f, headers=self.headers)
                # self.logger.debug(pformat(response.content))
                #self.logger.debug(pformat(response.reason))
                #self.testcase.assertEquals(response.status_code, statusCode)
                self.configId = response.json()[0]['id']
                return response.json()

    def getUploadedConfig(self, configID, statusCode=200):
        response = self.get('/api/v2/configs/{0}'.format(configID), headers=self.headers)
        #assert response.status_code == statusCode
        if response.status_code != statusCode:
            self.logError(f'getUploadedConfig failed: {response.json()["message"]}') 
            
        return response.json()
    
    def getAllAgents(self):
        """
        :return: a list of agents
        """
        response = self.get('/api/v2/agents', headers=self.headers)
        #assert response.status_code == 200
        if response.status_code != 200:
            self.logError(f'getAllAgents failed: {response.json()["message"]}')
        
        return response.json()

    def getAgentInfo(self, agentID):
        response = self.get('/api/v2/agents/{0}'.format(agentID), headers=self.headers)
        if response.status_code != 200:
            self.logError(f'getAgentInfo failed: {response.json()["message"]}') 
           
        if len(response.json()['id']) > 0:
            return response.json()
        else:
            return None

    def getAgentIP(self, agentID):
        response = self.getAgentInfo(agentID)
        return response['IP']
 
    def rebootAgents(self, agentIdList=None):
        """
        Reboot a list of agent IDs.
        
        Parameters
           agentIdList <list>: {"agents":[{"agentId":"<agent-id>"}]}
        """
        if agentIdList is None:
            agentIdList = []
            allAgentInfo = self.getAllAgents()
                
            for agent in allAgentInfo:
                agentId = agent['id']
                agentInfo = self.getAgentInfo(agentId)
                agentIp = agentInfo['IP']
                if 'agents' in self.keystackObj.moduleProperties['envParams'] and \
                    agentIp in self.keystackObj.moduleProperties['envParams']['agents']:
                    agentIdList.append({"agentId": agentId})
                else:
                    continue
                
        self.logInfo(f'rebootAgents: {agentIdList}') 
        response = self.post(url='/api/v2/agents/operations/reboot', data={"agents": agentIdList}, headers=self.headers)
        if response.status_code != 202:
            self.logError(f'Rebooting agents failed on LoadCore MW with status code {response.status_code}: {response.json()["message"]}')        
 
        # After rebooting agents, need to wait for agent operation status == SUCCESS       
        operationStatusUrl = '/api/v2/agents/operations/reboot/{}'.format(response.json()['id'])
        counter = 0
        timeout = 160
        
        while True:
            response = self.get(operationStatusUrl, headers=self.headers)
            status = response.json()['state']
            
            if counter < timeout and status != 'SUCCESS':
                self.logInfo(f'rebootAgents: Waiting for reboot status=SUCCESS. Current status={status}. {counter}/{timeout} seconds')
                counter += 1
                time.sleep(1)
            
            if counter < timeout and status == 'SUCCESS':
                break
            
            if counter == timeout and status != 'SUCCESS':
                self.logDebug(f'rebootAgents: Waited {counter}/{timeout} seconds. Reboot status = {status}.')
                # If using LoadCore on a laptop for development, agents take longer to reboot because of limited resources. 
                # The MW timeout is 5 seconds short.  Agents actually might've booted successfully.
                # Solution: Call verifyAllAgentsStatusUp().  If agents go from OFFLINE state to the STOPPED state, then they're up.
                if self.verifyAllAgentsStatusUp() == True:
                    break

    def verifyAllAgentsStatusUp(self):
        """
        Before starting the test, verify if the agents are in the STOPPED status.
        If not, reboot them and verify for STOPPED status.
        Raise an exception to abort the test if the agents are not in the STOPPED status.
        """
        agentIdRebootList = []
        allAgentInfo = self.getAllAgents()
        allAgents = []

        for agent in allAgentInfo:
            agentId = agent['id']
            agentInfo = self.getAgentInfo(agentId)
            
            if 'agents' in self.keystackObj.moduleProperties['envParams']:
                # The middleware could have many agents attached, but not all agents are 
                # for this test environment. We only care for agents relevant for the test.
                if agentInfo['IP'] not in self.keystackObj.moduleProperties['envParams']['agents']:
                    #self.logInfo(f'Discovered agent {agentInfo["IP"]}, but it is not part of this test environment. Excluding verification')
                    continue
                
            # For the below while loop 
            allAgents.append(agentInfo['IP'])

            self.logInfo(f'verifyAllAgentsStatusUp: Agent {agentInfo["IP"]} current status: {agentInfo["Status"]}')
            
            if agentInfo['Status'] != "STOPPED":
                agentIdRebootList.append({"agentId": agentId})
        
        if len(agentIdRebootList) == 0:
            # rebootAgents() could be calling this function and expecting a return value 
            # of True to indicate that all agents are up.
            return True
          
        if agentIdRebootList:
            timeout = 150
            counter = 0
            self.logInfo(f'verifyAllAgentsStatusUp: Total agents in LoadCore: {allAgents}')

            while True:
                counter += 1
                allAgentInfo = self.getAllAgents()
                
                for agent in allAgentInfo:
                    agentId = agent['id']
                    agentIp = agentInfo['IP']
                    agentInfo = self.getAgentInfo(agentId)

                    if agentIp in allAgents:
                        if agentInfo['Status'] == "STOPPED" and counter < timeout:
                            self.logInfo(f'Agent {agentIp} is up')
                            index = allAgents.index(agentIp)
                            allAgents.pop(index)
                            
                            if len(allAgents) == 0:
                                self.logInfo('verifyAllAgentsStatusUp: All agents are up and ready for testing')
                                return True

                            self.logInfo(f'verifyAllAgentsStatusUp: {counter}/{timeout} secs: status={agentInfo["Status"]} Waiting for remaining agents: {allAgents}')
                            time.sleep(1)
                        
                        if agentInfo['Status'] != "STOPPED" and counter < timeout:
                            self.logInfo(f'verifyAllAgentsStatusUp: {counter}/{timeout} secs: Agent={agentIp}: {agentInfo["Status"]}')
                            time.sleep(1)
                            continue
                        
                        if agentInfo['Status'] != "STOPPED" and len(allAgents) != 0 and counter == timeout:
                            self.logError(f'verifyAllAgentsStatusUp: {counter}/{timeout} secs: Some agents are not ready for testing. Please troubleshoot the following agents: {allAgents}')

    def getSessionConfig(self,  statusCode=200):
        response = self.get('/api/v2/sessions/{0}/config?include=all'.format(self.sessionId), headers=self.headers)
        assert response.status_code == statusCode
        return response.json()
    
    def selectConfig(self, configName):
        # Don't force people to put their config files in this folder structure
        # configFileName = 'configs/{0}.json'.format(configName)

        if '.json' in configName:
            configFileName = configName
        else:
            configFileName = '{0}.json'.format(configName)

        self.logInfo('Selected config file to load: {}'.format(configFileName))
        assert os.path.isfile(configFileName)

        file = open(configFileName)
        config = file.read()
        file.close()

        configJson = json.loads(config)
        return configJson

    def setSessionConfig(self, config, statusCode=200):
        self.headers.update({'Content-Type': 'application/json',
                             'Accept': '*/*',
                             'Cache-Control': 'no-cache',
                             'Host': '{0}'.format(self.host),
                             'Accept-Encoding': 'gzip, deflate',
                             'Referer': 'http://{0}/api/v2/sessions'.format(self.host),
                             'Postman-Token': '009256e4-5703-4564-8526-adfe3567fecd',
                             'User-Agent': 'PostmanRuntime/7.16.3',
                             'Connection': 'keep-alive'})

        if 'configData' in config:
            config = config['configData']['Config']

        response = self.put('/api/v2/sessions/{0}/config/config'.format(self.sessionId), data=config,
                            headers=self.headers)
        
        self.logDebug(pformat(response.content))
        self.logDebug(pformat(response.reason))
        assert response.status_code == statusCode
        
        #self.configId = response.json()['config-id']
        
        try:
            return response.json()
        except:
            return response
        
    def startTest(self,  result='SUCCESS', wait=90, statusCode=202):
        response = self.post('/api/v2/sessions/{0}/test-run/operations/start'.format(self.sessionId), headers=self.headers)
        self.logDebug(pformat(response.content))
        self.logDebug(pformat(response.json()))
        assert response.status_code == statusCode
                    
        waitTime = wait
        rest_url = '/api/v2/sessions/{0}/test-run/operations/start/{1}'.format(self.sessionId, response.json()['id'])
        retry = 0
        
        while wait > 0:
            state = self.get(rest_url, headers=self.headers)
            # self.logDebug(pformat(state))
            # self.logDebug(pformat(state.content))
            
            if state.json()['state'] == result:
                self.testId = self.getTestId()
                return state.json()

            if 'state' not in state.json():
                # The MW did not include the "state" in the JSON data. Show LoadCore team.
                self.logError(testcaseResultFolder=self.testcaseResultsFolder,
                              msg=f'GET for /api/v2/sessions/{self.sessionId}/test-run/operation/start/{response.json()["id"]} was called, but the MW did not include the state in the json response.  The json response: {state.json()}')
                break

            if 'message' in state.json():
                mwMessage = state.json()['message']
            else:
                mwMessage = None
                    
            if state.json()['state'] == 'ERROR':                    
                if retry == 0:
                    # NOTE: This is a workaround in case the agent fails to start traffic due to a race condition.
                    #       Reboot the agents and retest
                    warningMsg = f'Start traffic failed with ERROR state. LoadCore MW message: {mwMessage}'
                    self.logWarning(warningMsg)
                    self.keystackObj.logWarning(msg=warningMsg)
                    if self.verifyLicenseSettings() == False:
                        warningMsg = f'startTest: The license server type somehow got reverted. Resetting it back to {self.licenseServerType}'
                        self.logWarning(warningMsg)
                        self.keystackObj.logWarning(msg=warningMsg)
                        self.setLicenseServer()
                        
                    self.checkSessionState(status="STOPPED")
                    self.rebootAgents()
                    self.verifyAllAgentsStatusUp()
                    
                    # In case rebooting agemts reverted the license type, lets verify it to make sure.
                    if self.verifyLicenseSettings() == False:
                        warningMsg = f'startTest: The license server type somehow got reverted. Resetting it back to {self.licenseServerType}'
                        self.logWarning(warningMsg)
                        self.keystackObj.logWarning(msg=warningMsg)
                        self.setLicenseServer()
                        
                    retry = 1
                    response = self.post('/api/v2/sessions/{0}/test-run/operations/start'.format(self.sessionId), headers=self.headers)
                    self.logDebug(pformat(response.content))
                    self.logDebug(pformat(response.json()))
                    assert response.status_code == statusCode
                    wait = waitTime
                    rest_url = '/api/v2/sessions/{0}/test-run/operations/start/{1}'.format(self.sessionId, response.json()['id'])
        
                else:
                    if 'The test ended and was cleaned up' in state.json()['message']:
                        # The test ended and was cleaned up. Check the session's test details for more information.
                        # Need to hard reboot agents
                        # Ignore this message
                        self.logError(state.json()['message'])
                    else:
                        # break when start goes to ERROR state
                        self.logError(state.json()['message'])

            wait -= 1
            time.sleep(2)
            self.logDebug(pformat(state.json()))

        else:
            # Getting here means that Loadore MW did not state an ERROR in the json response
            # But still need to reboot the agents and retest one more time
            if retry == 0:
                    # NOTE: This is a workaround in case the agent fails to start traffic due to a race condition.
                #       Reboot the agents and retest
                self.keystackObj.logWarning('Start traffic failed to start within 90secs. Reboot agents and retest ...')
                self.stopTest()
                self.checkSessionState(status="STOPPED")
                
                if self.verifyLicenseSettings() == False:
                    self.keystackObj.logWarning(f'startTest: The license server type got reverted. Resetting it back to {self.licenseServerType}')
                    self.setLicenseServer()
                        
                self.rebootAgents()
                self.verifyAllAgentsStatusUp()
                
                if self.verifyLicenseSettings() == False:
                    self.logWarning(f'startTest: The license server type somehow got reverted. Resetting it back to {self.licenseServerType}')
                    self.setLicenseServer()
                                    
                retry = 1
                response = self.post('/api/v2/sessions/{0}/test-run/operations/start'.format(self.sessionId), headers=self.headers)
                self.logDebug(pformat(response.content))
                self.logDebug(pformat(response.json()))
                assert response.status_code == statusCode
                wait = waitTime
                rest_url = '/api/v2/sessions/{0}/test-run/operations/start/{1}'.format(self.sessionId, response.json()['id'])
            else:
                msg='Test failed to start in {} sec'.format(waitTime)
                self.logError(msg)
            
        # if state is ERROR, stop the test and print the error message.
        #assert (False, msg='State: {} - Error MSG: {}'.format(state.json()['state'], state.json()['message']))
        msg = 'startTraffic: State: {} - Error MSG: {}'.format(state.json()['state'], state.json()['message'])
        self.logError(msg)

    def stopTest(self,  result='SUCCESS', wait=40, statusCode=202):
        response = self.post('/api/v2/sessions/{0}/test-run/operations/stop'.format(self.sessionId), headers=self.headers)
        self.logDebug(pformat(response.content))
        self.logDebug(pformat(response.status_code))

        assert response.status_code == statusCode
        rest_url = '/api/v2/sessions/{0}/test-run/operations/stop/{1}'.format(self.sessionId, response.json()['id'])

        while wait > 0:
            try:
                state = self.get(rest_url, headers=self.headers)
                # self.logDebug(pformat(state))
                # self.logDebug(pformat(state.content))

                if state.json()['state'] == result:
                    return state.json()

                if state.json()['state'] == 'ERROR':  # break when start goes to ERROR state
                    break

                wait -= 1
                time.sleep(2)
                self.logDebug(pformat(state.json()))

            except:
                return response.json()

        else:
            #assert(False, msg='Test failed to stop')
            msg='Test failed to stop'
            self.logError(msg)

        # if state is ERROR, stop the test and print the error message.
        #assert(False, msg='State: {} - Error MSG: {}'.format(state.json()['state'], state.json()['message']))
        msg = 'State: {} - Error MSG: {}'.format(state.json()['state'], state.json()['message'])
        self.logError(msg)

    def modifySessionState(self, state='STOPPED'):
        """
        Modify a session's state.
        
        Mostly used on a stucked session in the "Test is Stopping" state.  
        To get out of a stucked state,  modify the state to 'STOPPED' and then call deleteSession().
        """
        data = {'status': state}
        response = self.patch('/api/v2/sessions/{0}/test'.format(self.sessionId), data=data, headers=self.headers)
        if response.status_code != 204:
            self.logError(f'Failed to modify session state: {state}')
        
    def checkSessionState(self,  status, waitTime=300):
        """
        Check the status of a state for up to the waitTime.
        """
        elapsedTime = 0
        testResponse = self.get('/api/v2/sessions/{0}/test'.format(self.sessionId), headers=self.headers)
        while elapsedTime < waitTime and testResponse.json()['status'] != status:
            try:
                testResponse = self.get('/api/v2/sessions/{0}/test'.format(self.sessionId), headers=self.headers)
            except ConnectionError as e:
                break
            
            time.sleep(5)
            elapsedTime += 5

        if testResponse.json()['status'] == False:
            # logError will raise an exception
            self.logError('The test failed to start')
          
        return True if testResponse.json()['status'] == status else False

    def verifyLicenseSettings(self):
        self.logInfo(f'verifyLicenseSettings ...')
        response = self.get('/api/v2/globalsettings', headers=self.headers)

        self.logInfo(f'verifyLicenseSettings: The middleware license is set to: {response.json()["licenseServer"]} type={response.json()["licenseType"]}. Expecting: {self.licenseServer} {self.licenseServerType}')
        
        if response.json()["licenseServer"].strip() != self.licenseServer.strip():
            self.logError(f'verifyLicenseSettings: Expecting license server IP: {self.licenseServer}. Got {response.json()["licenseServer"]}')
              
        if response.json()["licenseType"].strip() != self.licenseServerType.strip():
            self.logError(f'verifyLicenseSettings: Expecting: license server type: {self.licenseServerType}. Got {response.json()["licenseType"]}')
            
    def setLicenseServer(self):
        """ 
        license server types: 
           vLM: Old <= 1.5 external license server
           ExternalKCOS: External license server
           KCOS: Embeded license server
        """
        self.logInfo(f'setLicenseServer: type:{self.licenseServerType}  licenseServer:{self.licenseServer}')  
        payload = {"licenseServer": self.licenseServer, "licenseType": self.licenseServerType}
        response = self.put('/api/v2/globalsettings', payload, headers=self.headers)                        

        self.verifyLicenseSettings()
             
    def getTestId(self, statusCode=200):
        response = self.get('/api/v2/sessions/{0}/test'.format(self.sessionId), headers=self.headers)
        assert response.status_code == statusCode
        return response.json()['testId']

    def getAllStats(self, statName, statusCode=200):
        response = self.get('/api/v2/results/{0}/stats/{1}'.format(self.testId, statName), headers=self.headers)
        if response.status_code != statusCode:
            self.logWarning(f'getAllStats Error: {response.json()}')
            return None
        
        col = {}
        statList = []

        if response.json()['columns'] == None:
            # Stats not ready. Ready None.
            return None
            
        if response.json()['columns'][0] == "timestamp":
            try:
                for i in range(len(response.json()['columns']) - 1):
                    n = response.json()['columns'][i+1]
                    for j in range(len(response.json()['snapshots'])):
                        statList.append(float(response.json()['snapshots'][j]['values'][0][i+1]))
                    col[n] = statList
                    statList = []

                # returns a dictionary. The keys are the statistics.
                # The value for each key is a list of values with the polling interval 2 seconds.
                return col   
            except:
                self.logError("Exception raised: No stats available for {}. Test didn't run as expected".format(statName))
                pass

        else:
            try:
                # this is used for SBI stats.
                for i in range(len(response.json()['columns'])-1):      
                    n = response.json()['columns'][i+1]
                    for j in range(len(response.json()['snapshots'][0]['values'])):
                        statList.append(float(response.json()['snapshots'][0]['values'][j][i+1]))
                    col[n] = sum(statList)
                    statList = []
                return col
            except:
                self.logDebug("Exception raised: No stats available for {}. Test didn't run as expected".format(statName))
                pass

    def showStats(self, stats):
        """
        Show the stats on stdout
        """
        if stats:
            # for x in sorted(stats):
            #     #self.logInfo('%s = %s\nMax - %s : %s' % (x, stats[x], x, self.getMaxStat(stats[x])))
            
            for statName,value in stats.items():
                self.logInfo(f'{statName}: {value}')
            
    def getMaxStat(self, stat):
        return max(stat)

    def getAvgNonZeroStat(self, stat):
        statList = []
        for i in stat:
            if i != 0:
                statList.append(i)
        if len(statList) == 0:
            # if all values are zero, return 0 - For Failed/Timeout stats
            return 0                                        
        else:
            # Returns AVG on non-zero values
            return round(sum(statList) / len(statList), 2)    

    def getTestDuration(self,  multiplier=2):
        # return total test duration x multiplier (when test takes longer because of retries)
        response = self.get('/api/v2/sessions/{0}/test'.format(self.sessionId), headers=self.headers)
        assert response.status_code == 200
        total_duration = response.json()['testDuration'] * multiplier
        return total_duration

    def getAgentsInfo(self):
        response = self.get('/api/v2/agents', headers=self.headers)
        if response.status_code != 200:
            self.logError(response.json())
            
        #assert response.status_code == 200
        agents=response.json()
        agents_list = []
        for agent in agents:
            interface_list = []
            for interface in agent['Interfaces']:
                interface_list.append({'Name': interface['Name'], 'Mac': interface['Mac']})
                
            interface_list.sort(key=lambda x: x['Name'])
            # interfaces are stored in a list.
            agents_list.append({'id':agent['id'], 'IP':agent['IP'], 'Interfaces': interface_list})  

        return agents_list

    def getAgentDetails(self, agentsInfo, agentIP):
        for agent in agentsInfo:
            if agent['IP'] == agentIP:
                return agent

    def RemapAgents(self, configToModify, agentsDict, sbaTesterTopology=False):
        import copy
        newConfig = copy.deepcopy(configToModify)
        topology = 'Config' if sbaTesterTopology is False else 'SBAConfig'

        for node in agentsDict:
            if newConfig['configData'][topology]['nodes'][node]['settings']['enable'] == True:
                path = newConfig['configData'][topology]['nodes'][node]['settings']['mappedAgents'][0]
                path['agentId'] = agentsDict[node][0]
                for i in range(len(path['interfaceMappings'])):
                    if path['interfaceMappings'][i]['agentInterface'] != 'none':
                        path['interfaceMappings'][i]['agentInterface'] = agentsDict[node][1]
                        path['interfaceMappings'][i]['agentInterfaceMac'] = agentsDict[node][2]
        return newConfig
    
    def getTopologyFromSessionConfig(self, config):
        category = config['ConfigType']

        if category == 'Full Core':
            return 'Config'
        elif category == 'SBA':
            return 'sbaConfig'
        elif category == 'UPF Isolation':
            return 'upfIsolationConfig'
        elif category == 'iRAT':
            return 'IRATConfig'

    def getAgentNodeID(self, agentsInfo, agentIP):
        for agent in agentsInfo:
            if agent['IP'] == agentIP:
                return agent['id']
    
    def getInterfaceMAC(self, agentsInfo, agentIP, interfaceName):
        for agent in agentsInfo:
            if agent['IP'] == agentIP:
                for interface in agent['Interfaces']:
                    if interface['Name'] == interfaceName:
                        return interface['Mac']  
 
    def getAgentInterfaces(self, agentsInfo, agentIP):
        for agent in agentsInfo:
            if agent['IP'] == agentIP:
                return agent['Interfaces']
                
    def changeNetworkSettings(self, agentIP, interface, **kwargs):
        """
        Used to manipulate capture, networkStack and sriov. These options are available per interface
        
        'networkStack': 'linuxStack' -> for linuxstack

        'networkStack': 'ixStack' -> ixStack with Raw Sockets

        'networkStack': 'dpdk' -> ixStack with DPDK

        'capture': True / False

        'sriov': True / False
        """      
        config = self.getSessionConfig()
        topology = self.getTopologyFromSessionConfig(config)
        AgentsInfo = self.getAgentsInfo()
        networkSettings = config[topology]['networkSettings']
        agentId = self.getAgentNodeID(AgentsInfo, agentIP)

        for agent in networkSettings['agentsInfos']:
            if agent['agentId'] == agentId:
                for interfaceName in agent['interfacesSettings']:
                    if interfaceName['interfaceName'] == interface:
                        interfaceName['interfaceMac'] = self.getInterfaceMAC(AgentsInfo, agentIP, interface)
                        for key, value in kwargs.items():
                            interfaceName[key] = value
        
        if topology == 'Config':
            topology = topology.lower()
        response = self.patch('/api/v2/sessions/{}/config/{}/networkSettings'.format(self.sessionId, topology), data=networkSettings, headers=self.headers)
        assert response.status_code == 204

    def updateNetworkSettings(self, configToModify, networkSettings, topology):
        import copy
        newConfig = copy.deepcopy(configToModify)
        AgentsInfo = self.getAgentsInfo()

        # modify networkSettings structure
        agentsInfos = []

        for agent in networkSettings:
            d = {'agentId':agent, \
                'id': '', \
                'impairmentId': '-1'
                }
            temp = []
            for interface in networkSettings[agent]:
                 temp.append({'capture': False, 'interfaceName': interface, 'interfaceMac': self.getInterfaceMAC(AgentsInfo, self.getAgentIP(agent), interface), \
                            "networkStack": "linuxStack", "sriov": False})
            d['interfacesSettings'] = temp
            agentsInfos.append(d)

        # a config json file is different from a config extracted from session
        newConfig[topology]['networkSettings']['agentsInfos'] = agentsInfos
        # print(newConfig['configData'][path])

        return newConfig

    def interfaceConnectivity(self, localIpAddress, rangeNumber):
        """
        {
           'localIpAddress': string,
           'ipPrefix': 16,
           'gwStart': '0.0.0.0',
           'gwIncrement': '0.0.0.0',
           'mtu': 1500,
           'mss': 1460,
           'macStart': "0011bb000001",
           'macIncrement': "000000000001",
           'erAddress': '',
           'erPrefix': 24,
           'peerIds': ['1'],
           'n2Port': 3842'
           'sourceSCTPPort': 38412
        }
        """
        response = self.patch(f'/api/v2/sessions/{self.sessionId}/config/config/nodes/ran/ranges/{rangeNumber}/interfaces/n2/connectivitySettings', headers=self.headers)
        
    def reassignAgents(self, params):
        """
        This is an internal helper function. It was not provided by LoadCore Eng team.
        This function takes in yml parameter from a testcase yml file and construct
        an agentDict for all the LC agent nodes and then use it to call assignAgents.
        The reason is because assignAgents() requires a defined dict structure.
        
        # 1> [{ip: [172.16.1.14]}]  or  [{ip: [172.16.1.14, 172.16.1.41]}]
        #    This will use the agent's first test interface
        # 
        # 2> [{ip: [172.16.1.14, {nodesAndInterfaces: [{n3: ens192}, {n6: ens160}]} ]}]
        #    This will assign the agent to the node as described in the dict
        #
        # 3> [{ip: [172.16.1.14, {interface: ens192}] }]
        #    This will use the exact test interface (ens192)
        """
        # simatedNodes are ran, dn, amf, pcf, ...
        simulatedNodes = params['reassignAgentNodes'].keys()
        agentsDict = {}
        for simulationNode in simulatedNodes:
            agentsDict[simulationNode] = []
                        
            for key,value in params['reassignAgentNodes'][simulationNode].items(): 
                                    
                if len(value) > 1 and 'lcNodesAndInterfaces' in value[1]:
                    interfaceDict = {}

                    # n = [{'n6': 'ens33'}]
                    for index,lcInterface in enumerate(value):
                        if index == 0:
                            interfaceDict = {'agent': lcInterface} #Store the agent IP address first
                        
                        if type(lcInterface) == dict:
                            for eachLcInterface in lcInterface['lcNodesAndInterfaces']:
                                for key,value in eachLcInterface.items():
                                    interfaceDict.update({key: value})
                                    
                    agentsDict[simulationNode] = [interfaceDict]              
                    
                elif len(value) > 1 and 'interface' in value[1]:
                    # {nodes: [172.16.1.14, {interface: ens192}] }
                    # n = [{'n6': 'ens33'}]
                    for index,agentInterface in enumerate(value):
                        if index == 0:
                            agentIp = agentInterface
                        
                        if type(agentInterface) == dict:
                            for key,value in agentInterface.items():
                                agentsDict[simulationNode].append((agentIp, value))
                                
                elif len(value) == 1:
                    # Just the agent's ip address
                    agentsDict[simulationNode].append(value[0])
        
        self.logInfo(json.dumps(agentsDict, indent=4))
        self.assignAgents(agentsDict)
                                         
    def assignAgents(self, agentsDict):
        """
        four methods to assign agent to  5G nodes:
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

        """
        def __create_Mappings(agentsInfo, agentIP, testInterface, networkSettings):
            topology = self.getTopologyFromSessionConfig(config)
            defaultDict = defaultFullcoreDict
            if topology == 'sbaConfig':
                defaultDict = defaultSBATesterDict
            AgentNodeID = self.getAgentNodeID(agentsInfo, agentIP)
            if AgentNodeID not in networkSettings:      # check if agent already exist. If not, create key.
                networkSettings[AgentNodeID] = []
            for interface in defaultDict[node]:                 # go through each node interface and create the dict
                agentInterface = testInterface
                agentInterfaceMac = self.getInterfaceMAC(agentsInfo, agentIP, testInterface)
                if interface == 'passthroughDevice' or (node == 'upf' and interface == 'n6'):    # check for passthrough on ran and n6 on upf
                    agentInterface = "none"
                    agentInterfaceMac = "none"
                interfaceMappings.append({
                                        'agentInterface': agentInterface, \
                                        'agentInterfaceMac': agentInterfaceMac, \
                                        'nodeInterface': interface
                                        })
                if agentInterface not in networkSettings[AgentNodeID] and agentInterface != 'none':
                    networkSettings[AgentNodeID].append(agentInterface)
            
            return AgentNodeID, interfaceMappings, networkSettings[AgentNodeID]

        # each 5G node with its interfaces. This can suffer changes between releases
        defaultFullcoreDict = { 
                        'amf': ['n2', 'namf', 'n26'], 'ausf': ['nausf'], 'dn': ['n6'], 'eir': ['n5geir'], \
                        'ims': ['n6','rx'], 'mediaforwarder': ['n6'], 'mme': [], 'nrf': ['nnrf'], 'nssf': ['nnssf'], 'pcf': ['npcf', 'rx'], \
                        'ran': ['n2', 'n3', 'passthroughDevice', 's1u', 'n26', 's6a', 's5c', 's5u', 's11','s1'], 
                        'sgw': [], 'smf': ['n4', 'nsmf', 's5c', 's11'], 'smsf': ['nsmsf'], 'udm': ['nudm', 's6a'], 'udr': ['nudr'], \
                        'upf': ['n3', 'n4', 'n6', 'n9'], 'sbaTester': ['namf','nsmf','npcf'], 'chf': ['nchf']
                        }

        defaultSBATesterDict = { 
                        'ausf': ['nausf'], 'nrf': ['nnrf'], 'nssf': ['nnssf'], 'pcf': ['npcf'], 'udm': ['nudm'], 'udr': ['nudr'], \
                        'sbaTester': ['namf','nsmf','npcf'], 'chf': ['nchf']
                        }


        config = self.getSessionConfig()
        topology = self.getTopologyFromSessionConfig(config)
        path = config[topology]['nodes']
        agentsInfo = self.getAgentsInfo()
        networkSettings = {}
        payload = {}

        for node in agentsDict:         # go through each node
            mappedAgents = []
            if type(agentsDict[node]) is not list:                  # if not list, convert to list. This helps multi agent support
                agentsDict[node] = agentsDict[node].split("-")
            for agent in agentsDict[node]:                          # go through each agent.
                interfaceMappings = []
                mappedDict = {}

                if type(agent) is dict:       #[{'agent': self.lizardAgent2, 'n3': 'ens160', 'n4': 'ens160', 'n6': 'none' , 'n9': 'ens160'}]
                    agentIP = agent['agent']
                    AgentNodeID = self.getAgentNodeID(agentsInfo, agentIP)
                    if AgentNodeID not in networkSettings:      # check if agent already exist. If not, create key.
                        networkSettings[AgentNodeID] = []
                    del agent['agent']
                    nodeInterfaces = agent
                    
                    for interface in nodeInterfaces:
                        if nodeInterfaces[interface] == 'none':
                            agentInterfaceMac = 'none'
                        else:
                            agentInterfaceMac = self.getInterfaceMAC(agentsInfo, agentIP, nodeInterfaces[interface])
                        interfaceMappings.append({
                                        'agentInterface': nodeInterfaces[interface], \
                                        'agentInterfaceMac': agentInterfaceMac, \
                                        'nodeInterface': interface
                                        })
                        if nodeInterfaces[interface] not in networkSettings[AgentNodeID] and nodeInterfaces[interface] != 'none':
                            networkSettings[AgentNodeID].append(nodeInterfaces[interface])
                        # print(interfaceMappings)
                elif type(agent) is tuple:
                    AgentNodeID, interfaceMappings, networkSettings[AgentNodeID] = __create_Mappings(agentsInfo, agent[0], agent[1], networkSettings)

                else:
                    AgentNodeID, interfaceMappings, networkSettings[AgentNodeID] = __create_Mappings(agentsInfo, agent, \
                                                                                    self.getAgentInterfaces(agentsInfo, agent)[0]['Name'], networkSettings)

                # create list of assigned agents.
                mappedDict = {'agentId': AgentNodeID, 'id': "", "interfaceMappings": interfaceMappings}
                mappedAgents.append(mappedDict)

            path[node]['settings']['mappedAgents'] = mappedAgents

            payload[node] = path[node]      # create payload

        response = self.patch('/api/v2/sessions/{}/config/{}/nodes'.format(self.sessionId,topology.lower() if topology == 'Config' else topology), data=payload, headers=self.headers)
        assert response.status_code == 204

        # populate networkSettings with current agents
        updatedNetworkSettings = self.updateNetworkSettings(config, networkSettings, topology)[topology]['networkSettings']

        response = self.patch('/api/v2/sessions/{}/config/{}/networkSettings'.format(self.sessionId, topology.lower() if topology == 'Config' else topology), data=updatedNetworkSettings, headers=self.headers)
        assert response.status_code == 204
                        
    def getStartEndTestTimestamp(self):
        response = self.get('/api/v2/sessions/{0}/test'.format(self.sessionId), headers=self.headers)
        return response.json()['testStarted']*1000, response.json()['testStopped']*1000

    def configSustainTime(self,  sustainTime):
        # https://192.168.129.154/api/v1/sessions/1/appsec/sessions/wireless-70d29f83-cd12-414b-9c6e-e52993684ee2/config/config/nodes/ue/ranges/1/controlPlane/primaryObjective/activeSubscribers

        response = self.patch('/api/v2/sessions/{0}/config/config/nodes/ue/ranges/1/controlPlane/primaryObjective/activeSubscribers'.format(self.sessionId),
                             data={'sustain': sustainTime}, headers=self.headers)

        if response.status_code != 204:
            self.logError(response.json())
            
    def getSustainTime(self):
        response = self.get('/api/v2/sessions/{0}/config/config/nodes/ue/ranges/1/controlPlane/primaryObjective/activeSubscribers'.format(self.sessionId),
                    headers=self.headers)
        assert response.status_code == 200
        return response.json()['sustain']

    def createHTMLreport(self,  listOfStatistics, reportName, startTime, endTime,
                         logoFolder=None):
        html = self.getHTML(listOfStatistics, reportName, startTime, endTime)
        
        # ./ConfigFiles/TC145_b2b_With_Agents.json
        reportName = reportName.split('/')[-1].split('.json')[0]
        filename = '{}/{}.html'.format(self.testcaseResultsFolder, reportName)
        self.logInfo('\ncreateHTMLreport: filename: {}'.format(filename))
        
        with open(filename, 'w') as f:
            f.write(html)

        shutil.copy("{}/keysightlogo.png".format(logoFolder), self.testcaseResultsFolder)
        shutil.copy("{}/loadcorelogo.PNG".format(logoFolder), self.testcaseResultsFolder)

        return filename
      
    def getHTML(self, statsList, reportName, startTime, endTime):
        testId = self.getTestId()
        t1, t2 = self.getStartEndTestTimestamp()
        data = {}
        l = []
        start = startTime.strftime('%Y-%m-%d %H:%M:%S')
        end = endTime.strftime('%Y-%m-%d %H:%M:%S')

        html = """<html><head>
                <style>
                .collapsible {
                background-color: #282828;
                color: white;
                cursor: pointer;
                padding: 18px;
                width: 100%;
                border: none;
                text-align: left;
                outline: none;
                font-size: 15px;
                }

                .active, .collapsible:hover {
                background-color: #808080;
                }
                .collapsible:after {
                content: '\\002B';
                color: white;
                font-weight: bold;
                float: right;
                margin-left: 5px;
                }

                .active:after {
                content: "\\2212";
                }


                .content {
                display: inline-block;
                padding: 0 18px;
                max-height: 0;
                overflow: hidden;
                transition: max-height 0.2s ease-out;
                overflow: hidden;
                background-color: white;
                }

                .column {
				  float: left;
				  padding: 1px;
				}

				.row:after {
				  content: "";
				  display: table;
				  clear: both;
				}
				.left {
				  width: 20%;
				}
				.middle {
				  width: 15%;
                  color: #282828;
				}
				.right {
				  float: right;
				  width: 20%;
				}
                </style>
                </head>
                <body>
                <div class="row">
					<div class="column left">
						<img src="loadcorelogo.PNG",
						 height = 48 width = 158/>
					</div>
                """
        session = self.getSessionInfo()
        html += '<div class="column middle"><center><b>{}</b></center></div>'.format(session['ownerID'])
        html += '<div class="column middle"><center><b>{}</b></center></div>'.format(reportName)
        html += '<div class="column middle"><center><b>{}</b></center></div>'.format(start)
        html += '<div class="column middle"><center><b>{}</b></center></div>'.format(end)

        html += """<div class="column right"><img src="keysightlogo.PNG",
						height = 48 width = 158 style="float:right;margin-top: -25px;"/>
					</div>
				</div>
                """

        for stat in statsList:
            response = self.get('/api/v2/results/{}/stats/{}?from={}'.format(testId, stat, t1), headers=self.headers)
            try:
                if response.json()['columns'][0] == "timestamp":
                    for i in range(len(response.json()['columns'])):
                        n = response.json()['columns'][i]
                        for j in range(len(response.json()['snapshots'])):
                            if n == 'timestamp':
                                t = float(response.json()['snapshots'][j]['values'][0][i])/1000
                                l.append(datetime.datetime.fromtimestamp(t) .strftime('%Y-%m-%d %H:%M:%S'))
                            else:
                                l.append(response.json()['snapshots'][j]['values'][0][i])
                        data[n] = l
                        l = []

                    html += '<button type="button" class="collapsible">{}</button><div class="content">'.format(stat)
                    html += '<table border="1"><tr><th>' + '</th><th>'.join(data.keys()) + '</th></tr>'

                    for row in zip(*data.values()):
                        html += '<tr><td>' + '</td><td>'.join(row) + '</td></tr>'

                    html += '</table></div>'
                    data.clear()

                else:
                    for i in range(len(response.json()['columns'])):
                        n = response.json()['columns'][i]
                        for j in range(len(response.json()['snapshots'][0]['values'])):
                            l.append(response.json()['snapshots'][0]['values'][j][i])
                        data[n] = l
                        l = []

                    html += '<button type="button" class="collapsible">{}</button><div class="content">'.format(stat)
                    html += '<table border="1"><tr><th>' + '</th><th>'.join(data.keys()) + '</th></tr>'

                    for row in zip(*data.values()):
                        html += '<tr><td>' + '</td><td>'.join(row) + '</td></tr>'

                    html += '</table></div>'
                    data.clear()

            except:
                self.logDebug("Exception raised: No stats available for {} view.".format(stat))
                pass

        #print(data)

        html += """
                </body>
                <script>
                var coll = document.getElementsByClassName("collapsible");
                var i;

                for (i = 0; i < coll.length; i++) {
                coll[i].addEventListener("click", function() {
                    this.classList.toggle("active");
                    var content = this.nextElementSibling;
                    if (content.style.maxHeight){
                    content.style.maxHeight = null;
                    } else {
                    content.style.maxHeight = content.scrollHeight + "px";
                    }
                });
                }
                </script>
                </html>
                """

        return html

    def getPDFreport(self, wait=120, statusCode=202):
        """
        folderName = The config file name. This allows passing in the full path. Will parse out the last string.
        """
        testID = self.getTestId()
        response = self.post('/api/v2/results/{0}/operations/generate-pdf'.format(testID), headers=self.headers)
        if response.status_code != statusCode:
            self.logWarning(f'getPDFreport failed to get from LoadCore middleware')
            return None

        operation_url = '/api/v2/results/{0}/operations/generate-pdf/{1}'.format(testID, response.json()['id'])

        pdfReportDone = False
        while wait > 0:
            state = self.get(operation_url, headers=self.headers)
            self.logDebug(pformat(state.json()))

            if state.json()['state'] == 'SUCCESS':
                pdfReportDone = True
                pdfReport = self.get(state.json()['resultUrl'], headers=self.headers)
                break

            if state.json()['state'] == 'ERROR':
                self.logWarning('getPDFreport: Could not get the pdf report')
                return None

            wait -= 5
            time.sleep(5)

        if pdfReportDone == False:
            self.logWarning(f'GetPDFreport: Failed to download the pdf report after {wait} seconds. Try increasing the wait time.')
            return None
        
        filename = '{}/{}.pdf'.format(self.testcaseResultsFolder, self.testcaseName)
        self.logInfo('getPDFreport: filename: {}'.format(filename))
        
        with open(filename, 'wb') as f:
            f.write(pdfReport.content)
        
        os.chmod(filename, 0o774)

        return filename

    def getCSVs(self, csvFilesToGet='all', convertCsvToJson=False, wait=180, statusCode=202):
        """
        Retrieve the CSV result zip file from LoadCore Middleware.
        Create a CSV folder and store all csvFilesToGet
        
        Parameters:
           csvFilesToGet: A list of specific csv files to save in the CSV folder
           convertCsvToJson: Create a JSON folder and convert a copy of each csv file to json format
           
        """
        testID = self.getTestId()
        response = self.post('/api/v2/results/{0}/operations/generate-csv'.format(testID), headers=self.headers)
        if response.status_code != statusCode:
            self.logWarning(f'getCSVs: Failed to get from LoadCore middleware')
            return None
        
        operation_url = '/api/v2/results/{0}/operations/generate-csv/{1}'.format(testID, response.json()['id'])
        csvReportDone = False

        while wait > 0:
            state = self.get(operation_url, headers=self.headers)
            self.logDebug(pformat(state.json()))

            if state.json()['state'] == 'SUCCESS':
                csvReportDone = True
                archive = self.get(state.json()['resultUrl'], headers=self.headers)
                break

            if state.json()['state'] == 'ERROR':
                self.logWarning('getCSV: Could not get the results archive')
                return None

            wait -= 5
            time.sleep(5)

        
        if csvReportDone == False:
            self.logWarning(f'getCSVs: Failed to download the csv report after {wait} seconds. Try increasing the wait time.')
            return None
        
        # csv-reports-2021-05-26-17-37-19.zip
        csvHeaders = archive.headers['Content-Disposition']
        
        filename = '{}/{}_csv.zip'.format(self.testcaseResultsFolder, self.testcaseName)
        self.logInfo('getCSVs: filename: {}'.format(filename))

        with open(filename, 'wb') as f:
            f.write(archive.content)

        os.chmod(filename, 0o774)

        #if csvFilesToGet != 'all':
        # Copy the zip file to
        import shutil
        from zipfile import ZipFile

        testcaseCsvFolder = f'{self.testcaseResultsFolder}/CSV'
        makeFolder(testcaseCsvFolder)
            
        # Unzip file
        self.logInfo(f'Unzip selected CSV results from {filename} -> {testcaseCsvFolder}')
        with ZipFile(filename, 'r') as zipObj:
            zipObj.extractall(f'{testcaseCsvFolder}')
                    
        if convertCsvToJson:
            # Convert all KPIs to JSON format                
            allKpiJsonFolder = f'{self.testcaseResultsFolder}/JSON_KPIs'
            makeFolder(allKpiJsonFolder)
            
            # Create a folder to store selected KPI results
            testcaseJsonFolder = f'{self.testcaseResultsFolder}/JSON_KPIResults'
            makeFolder(testcaseJsonFolder)

        # Convert all csv results to json format
        for eachCsvFile in os.listdir(f'{testcaseCsvFolder}'):
            if '.csv' not in eachCsvFile:
                continue
            
            # Current CSV file name
            currentFilename = eachCsvFile.split('.csv')[0]
            renamedFile = eachCsvFile.split('Fullcore')[-1]
            renamedFilePath = f'{testcaseCsvFolder}/{renamedFile}'
            
            # Rename the CSV file
            os.rename(f'{testcaseCsvFolder}/{eachCsvFile}', renamedFilePath)
            renamedToJsonExtension = f'{allKpiJsonFolder}/{renamedFile}'.replace('.csv', '.json')

            # Creating two JSON result folders:
            #    1> One folder called JSON_KPIs, which translates all of the CSV files to JSON format
            #    2> One folder called JSON_KPIResults, which translates the testcase expected KPIs
            #       from CSV to JSON format.
            if self.convertCsvFileToJsonFile(renamedFilePath, renamedToJsonExtension) == False:
                continue
            
            os.chmod(renamedToJsonExtension, 0o774)
            
            if currentFilename in csvFilesToGet:
                if os.path.getsize(renamedFilePath) == 0:
                    self.keystackObj.logWarning(msg=f'Expected KPI CSV result file is empty: {renamedFilePath}')
                    continue

                renamedToJsonExtension = f'{testcaseJsonFolder}/{renamedFile}'.replace('.csv', '.json')
                self.convertCsvFileToJsonFile(renamedFilePath, renamedToJsonExtension)
                os.chmod(renamedToJsonExtension, 0o774)
        
        shutil.rmtree(testcaseCsvFolder)
            
        # if csvFilesToGet == 'all':
        #     with ZipFile(filename, 'r') as zipObj:
        #         zipObj.extractall(f'{testcaseCsvFolder}')

        # Return a zip file that contains all the LoadCore CSV result files
        return filename
    
    def getCapturedLogs(self, wait=120, statusCode=202):
        testID = self.getTestId()
        response = self.post('/api/v2/results/{0}/operations/export-results'.format(testID), headers=self.headers)
        if response.status_code != statusCode:
            self.logWarning(f'getCapturedLogs: Failed to get from LoadCore middleware')
            return None

        operation_url = '/api/v2/results/{0}/operations/generate-results/{1}'.format(testID, str(response.json()['id']))
        logReportDone = False

        while wait > 0:
            state = self.get(operation_url, headers=self.headers)
            self.logDebug(pformat(state.json()))

            if state.json()['state'] == 'SUCCESS':
                logReportDone = True
                archive = self.get(state.json()['resultUrl'], headers=self.headers)
                break

            if state.json()['state'] == 'ERROR':
                self.logWarning('getCapturedLogs: Could not get the captures/logs archive')
                return None
            
            wait -= 5
            time.sleep(5)

        if logReportDone == False:
            self.logWarning(f'getCapturedLogs: Failed to download the capture and log report after {wait} seconds. Try increasing the timeout value.')
            return None

        filename = '{}/{}-{}'.format(self.testcaseResultsFolder, self.testcaseName, archive.headers['Content-Disposition'].split("=")[1].replace('"', ''))
        self.logInfo('getCapturedLogs: filename: {}'.format(filename))
        
        with open(filename, 'wb') as f:
            f.write(archive.content)

        os.chmod(filename, 0o774)
        return filename

    def deleteTestLogsAndResults(self):
        """
        This rest api has to be called after the session is deleted.
        Because LoadCore MW doesn't allow you to delete results and logs when
        the session is still active.
        """
        self.logInfo('deleteTestLogAndResults ...')
        url = '/api/v2/results/{}'.format(self.testId)
        response = self.delete(url, headers=self.headers)
        
    def deleteTestConfig(self):
        """
        Delete the test configurations.
        """
        self.logInfo(f'deleteTestConfigs: {self.configId}')
        url = f'/api/v2/configs/{self.configId}'
        response = self.delete(url, headers=self.headers)
        
                
class Main():
    def __init__(self, mainObj):
        """ 
        This class is a Keystack module
        """
        # The keystack framework object
        self.mainObj = mainObj
        
        self.configFile = mainObj.exportedConfigFullPath
        self.eachTestcase = mainObj.eachTestcase
        self.testcaseDict = mainObj.testcaseDict
        self.testcaseDebugLogFile = mainObj.testcaseDebugLogFile
        self.testcaseResultsFolder = mainObj.testcaseResultsFolder
        self.testcaseYmlFilename = mainObj.testcaseYmlFilename
        self.testcaseSortedOrderList = mainObj.testcaseSortedOrderList
        self.debug = mainObj.debug
        self.createKpiTracker()

        if self.mainObj.moduleProperties.get('envParams') is None:
            raise Exception('Running LoadCore requires an env setup to use which is missing in the playbook')
        
        # Mandatory to set license details in the Env file 
        for licenseParam in ['licenseServerIp', 'licenseServerType']:
            if licenseParam not in self.mainObj.moduleProperties['envParams']:
                raise Exception(f'LoadCore __init__(): The Keystack Env file {self.mainObj.moduleProperties["env"]} is missing parameter: {licenseParam}')
                        
    def createKpiTracker(self):
        """
        KPI dict:  Create a dictionary to keep track of each KPI passed/failed results
        """  
        self.kpiStatTracker = dict() ;# Keeping track of each KPI result

        for eachTestcase in self.testcaseSortedOrderList:
            # kpiStatTracker = Set all KPIs to failed. Run time will set KPI to passed if it meets the expected max value.
            # testcaseKPIs   = Get a dict of test case KPI for summary file at the end of each test. 
            self.kpiStatTracker[eachTestcase] = dict()
            for statName in self.testcaseDict[eachTestcase]['KPI']:
                statName = statName.strip()

                if 'NA' in self.testcaseDict[eachTestcase]['KPI'][statName] or self.testcaseDict[eachTestcase]['KPI'][statName] == "":
                    continue

                self.kpiStatTracker[eachTestcase][statName] = dict()

                for kpiKeyValue in self.testcaseDict[eachTestcase]['KPI'][statName]:
                    if '<=' in kpiKeyValue:
                        kpi = kpiKeyValue.split('<=')[0]
                    elif '>=' in kpiKeyValue:
                        kpi = kpiKeyValue.split('>=')[0]
                    elif '<' in kpiKeyValue:
                        kpi = kpiKeyValue.split('<')[0]
                    elif '>' in kpiKeyValue:
                        kpi = kpiKeyValue.split('>')[0]
                    elif '==' in kpiKeyValue:
                        kpi = kpiKeyValue.split('==')[0]
                    elif '=' in kpiKeyValue:
                        kpi = kpiKeyValue.split('=')[0]
                    
                    self.kpiStatTracker[eachTestcase][statName][kpi] = {'result': None, 'expectedValue': None, 'maxValue': None}

    def verifySessionForStoppedState(self):
        # Wait until the session is stopped before continuing
        self.loadCoreObj.checkSessionState(status='STOPPED', waitTime=self.loadCoreObj.getTestDuration())

        loadCoreCurrentStatus = self.loadCoreObj.getSessionStatus()
        self.loadCoreObj.logInfo(f'LoadCore current status: {loadCoreCurrentStatus}')
    
        # Self recovery if the session is stuck in the STOPPING state
        if loadCoreCurrentStatus == 'STOPPING':
            self.loadCoreObj.modifySessionState(state='STOPPED')
            self.loadCoreObj.checkSessionState(status='STOPPED', waitTime=60)  
            loadCoreCurrentStatus = self.loadCoreObj.getSessionStatus()
            self.loadCoreObj.logInfo(f'LoadCore current status: {loadCoreCurrentStatus}')
        
        if loadCoreCurrentStatus != 'STOPPED':
            self.loadCoreObj.logError(f'LoadCore is stuck in status: {loadCoreCurrentStatus}. It will not be able to run anymore testing.  Please go troubleshoot LoadCore to find out why the session is stuck in status {loadCoreCurrentStatus}.')                  
                            
    def runTestcase(self):
        """
        This function runs one testcase passed in from the main script.
        """
        # For each test, get a list of LoadCore CSV result files to verify KPIs
        try:
            newSessionId = None
            sessionStatus = False
            loadcoreCsvResultsToVerify = []
            for csvFile in self.testcaseDict[self.eachTestcase]['KPI']:
                loadcoreCsvResultsToVerify.append(csvFile)

            self.mainObj.writeToMainLogFile(f'Executing testcase: {self.eachTestcase}')
            self.mainObj.writeToMainLogFile(f'Loading config file: {self.configFile}')
            
            # This login is to support an engineering private image that doesn't require login
            if 'login' in self.mainObj.moduleProperties['envParams'] and self.mainObj.moduleProperties['envParams']['login'] == False:
                login = False
            else:
                login = True
            
            self.loadCoreObj = MW(host=self.mainObj.moduleProperties['envParams']['mwIp'],
                                  licenseServer=self.mainObj.moduleProperties['envParams']['licenseServerIp'],
                                  username=self.mainObj.moduleProperties['envParams']['username'],
                                  password=self.mainObj.moduleProperties['envParams']['password'],
                                  debugMode=self.debug, testcaseLogFile=self.testcaseDebugLogFile, login=login,
                                  testcaseResultsFolder=self.testcaseResultsFolder, testcaseName=self.testcaseYmlFilename,
                                  keystackObj=self.mainObj,)
          
            self.loadCoreObj.setLicenseServer()
           
            if self.mainObj.moduleProperties['rebootAgentsBeforeEachTest']:
                self.mainObj.updateModuleStatusData(status="Rebooting Agents")
                self.loadCoreObj.rebootAgents()
            
            # Verify if all agents are ready for testing. If not, reboot agents and verify for status up.
            # If agents still cannot come up after a reboot, then raise exception to abort testing.
            allAgentsInfo = self.loadCoreObj.verifyAllAgentsStatusUp()

            self.loadCoreObj.logInfo(f'Running test: {self.configFile}')
            self.loadCoreObj.logInfo(json.dumps(self.testcaseDict, indent=4, sort_keys=True))

            # Create new session using the specified config file
            self.mainObj.updateModuleStatusData(status="Loading Config File")
            if 'json' in self.configFile:
                response = self.loadCoreObj.newSession(configName=self.configFile)
            if 'zip' in self.configFile:
                response = self.loadCoreObj.newSession(configArchive=self.configFile)
            
            newSessionId = response.json()[0]['id']
            
            # The LoadCore test session index ID
            self.mainObj.testcaseData['testSessionIndex'] = response.json()[0]['index']           
            # Get the test session web link
            self.mainObj.testcaseData['testSessionId'] = f"https://{self.mainObj.moduleProperties['envParams']['mwIp']}/wireless/#{newSessionId}"
            
            self.loadCoreObj.logInfo(f'Test session index: {self.mainObj.testcaseData["testSessionIndex"]}')
             
            # ------ Do all LoadCore reconfigurations here -------
            # Define all parameters here and set to default
            pollStatInterval = None
            
            try:
                if self.mainObj.testcaseConfigParams.get('configParams', None):
                    for execFunction in self.mainObj.testcaseConfigParams['configParams'].get('executeFunctions', None):
                        libraryModule = execFunction['libraryModule']
                        if os.path.exists(libraryModule) == False:
                            self.loadCoreObj.logError(f'No such execFunction library module found: {execFunction["libraryModule"]}')

                        functionName = execFunction['functionName']
                        functionParams = execFunction.get('functionParams', None)
                        libraryModuleFilename = libraryModule.split('/')[-1].split('.')[0]
                        libraryModulePath = libraryModule.split('/')
                        del libraryModulePath[-1]  ;# Get rid of the filename. Just get the path.
                        libraryModulePath = '/'.join(libraryModulePath)
                        sys.path.insert(0, libraryModulePath)

                        modifyFileObj = __import__(libraryModuleFilename)

                        functionObj = getattr(modifyFileObj, functionName)

                        # The function could have multiple parameters. functionParams contains
                        # all parameters in a list.
                        functionObj(mainObj=self.mainObj, loadCoreObj=self.loadCoreObj, testcaseParams=functionParams)

                        sys.path.pop(0)

                    # Get all the individual parameters
                    if self.mainObj.testcaseConfigParams['configParams'].get('params', None):
                        pollStatIntervalIndex = getDictItemFromList(listOfDict=self.mainObj.testcaseConfigParams['configParams']['params'], key='name', value='pollStatInterval')
                        if pollStatIntervalIndex is not None:
                            pollStatInterval = self.mainObj.testcaseConfigParams['configParams']['params'][pollStatIntervalIndex]['value']

            except Exception as errMsg:
                self.loadCoreObj.logError(errMsg)

            # ------- Reconfigurations ends ----------
            # startTest status: {'id': 1891, 'type': '/api/v2/sessions/{sessions-id}/test-run/operations/start', 'state': 'SUCCESS', 'progress': 100, 'message': '', 'url': 'https://192.168.28.6/api/v2/sessions/wireless-6449a738-5e93-4c8c-b77c-3e42c775a83c/test-run/operations/start/1891', 'resultUrl': '/api/v2/sessions/wireless-6449a738-5e93-4c8c-b77c-3e42c775a83c', 'result': {'testId': 'wireless-6a772f62-327c-4762-a59c-18d33cb50b63'}}
            status = self.loadCoreObj.startTest()
            sessionStatus = self.loadCoreObj.checkSessionState(status='STARTED')
            if sessionStatus == False:
                self.loadCoreObj.logError('Start traffic failed to start')
                raise Exception('Start test failed to start')
                            
            realtestConfiguredDuration = self.loadCoreObj.getTestDuration(multiplier=1)                
            testConfiguredDuration = round(realtestConfiguredDuration/60, 2)
            self.loadCoreObj.logInfo(f'testConfiguredDuration: {testConfiguredDuration} minutes')
            
            self.mainObj.testcaseData['testConfiguredDuration'] = f'{testConfiguredDuration} minutes'
            self.mainObj.testcaseData['status'] = 'Running'
            self.mainObj.updateModuleStatusData(status="Running")
            
            while True:
                for statName in loadcoreCsvResultsToVerify:
                    # Get the KPIs for the statName
                    #    currentStats: {'PDU Session Establishment Failed':    [0.0, 0.0],
                    #                   'PDU Session Establishment Initiated': [0.0, 0.0],
                    #                   'PDU Session Establishment Succeeded': [0.0, 0.0]}
                    currentStats = self.loadCoreObj.getAllStats(statName)
                    if currentStats is None:
                        continue

                    self.loadCoreObj.logInfo(f'Polling KPI stats: {statName}')
                    kpiList = self.testcaseDict[self.eachTestcase]['KPI'][statName]
                        
                    # Runtime KPIs.  Here, ignore the value. Just need the runtime KPI name. 
                    # In case you are curios, the value variable is constantly appending current stat value in a list
                    for runtimeKpi, value in currentStats.items():
                        index = None
                        
                        # Get the relevant KPI from CSV
                        # Ex: kpiKeyValue = ['Registration Initiated=100', 'Registration Succeeded=20'
                        for userDefinedKpi in kpiList:
                            # Use regex to compare the KPI spelling in case user messed up the case sensitivity
                            if bool(re.match(runtimeKpi, userDefinedKpi, re.I)):
                                index = kpiList.index(userDefinedKpi)
                        
                        # Each CSV stat has many KPIs. Ignore the ones that the user did not defined in the testcase yml file.
                        if index is None:
                            continue

                        if '<=' in self.testcaseDict[self.eachTestcase]['KPI'][statName][index]:
                            expectedKpiOperator = '<='
                            expectedValue = self.testcaseDict[self.eachTestcase]['KPI'][statName][index].split('<=')[1]
                        elif '>=' in self.testcaseDict[self.eachTestcase]['KPI'][statName][index]:
                            expectedKpiOperator = '>='
                            expectedValue = self.testcaseDict[self.eachTestcase]['KPI'][statName][index].split('>=')[1]
                        elif '>' in self.testcaseDict[self.eachTestcase]['KPI'][statName][index]:
                            expectedKpiOperator = '>'
                            expectedValue = self.testcaseDict[self.eachTestcase]['KPI'][statName][index].split('>')[1]
                        elif '<' in self.testcaseDict[self.eachTestcase]['KPI'][statName][index]:
                            expectedKpiOperator = '<'
                            expectedValue = self.testcaseDict[self.eachTestcase]['KPI'][statName][index].split('<')[1]
                        elif '==' in self.testcaseDict[self.eachTestcase]['KPI'][statName][index]:
                            expectedKpiOperator = '='
                            expectedValue = self.testcaseDict[self.eachTestcase]['KPI'][statName][index].split('==')[1]
                        elif '=' in self.testcaseDict[self.eachTestcase]['KPI'][statName][index]:
                            expectedKpiOperator = '='
                            expectedValue = self.testcaseDict[self.eachTestcase]['KPI'][statName][index].split('=')[1]
                                                        
                        # kpiKeyValue = Registration Succeeded=20 or Bits Received/s=430000000-450000000
                        kpi = self.testcaseDict[self.eachTestcase]['KPI'][statName][index].split(expectedKpiOperator)[0].strip()
                        
                        maxValue = max(currentStats[runtimeKpi])
                        
                        self.loadCoreObj.logInfo(f'\n\tKPI: [{kpi}]  expectedValue{expectedKpiOperator}{expectedValue}   maxValue={maxValue}', includeTimestamp=False)
                        self.loadCoreObj.logInfo(f'\tKPI acummulated values: {value}', includeTimestamp=False)

                        # NOTE: This while loop is continuously overwriting the results for each KPI.
                        #       Once the test is done, the kpiStatTracker will contain the latest maxValue.
                        # Ex: expectedValue = ['20-50']
                        if '-' in expectedValue:
                            # Range value
                            minimumValue = int(expectedValue.split('-')[0].strip())
                            maximumValue = int(expectedValue.split('-')[1].strip())
                            if maxValue in range(minimumValue, maximumValue + 1):
                                result = 'passed'
                                self.loadCoreObj.logInfo(f'\tPassed!  The expected range value is achieved.', includeTimestamp=False)
                            else:
                                result = 'failed'
                        else:
                            op = self.mainObj.operators.get(expectedKpiOperator)
                            
                            # Note: If runtime stat (maxValue) $expectedKpiOperator expectedValue
                            if op(maxValue, float(expectedValue)):
                                result = 'passed'
                                self.loadCoreObj.logInfo(f'\tPassed!  The expected value is achieved.', includeTimestamp=False)
                            else:
                                result = 'failed'
                                
                        self.kpiStatTracker[self.eachTestcase][statName][kpi].update({'result': result,
                                                                                    'expectedValue': f'{expectedKpiOperator}{expectedValue}',
                                                                                    'maxValue': maxValue})
                
                status = self.loadCoreObj.getSessionStatus()
                self.loadCoreObj.logInfo(f'Session status: {status}')            
                if status in ['STOPPING', 'STOPPED']:
                    self.mainObj.updateModuleStatusData(status="Stopping")
                    break
                
                if pollStatInterval is None:
                    # Default stat poll to 30 seconds
                    setPollInterval = .30 * 100
                    pollInterval = .30
                else:
                    setPollInterval = pollStatInterval * 100
                    pollInterval = pollStatInterval
                    
                self.loadCoreObj.logInfo(f'Currently running: {self.eachTestcase}\n\t\tTest time remaining approximately: {testConfiguredDuration} minutes\n\t\tPollStatInterval: Waiting {setPollInterval} seconds')
                
                time.sleep(setPollInterval)
                testConfiguredDuration -= pollInterval
                self.mainObj.testcaseData['KPIs'] = self.kpiStatTracker[self.eachTestcase] ;# Update current results

            self.mainObj.testcaseData['timeStop'] = getTimestamp()
            testStop = datetime.datetime.now()
            self.mainObj.testcaseData['testDuration'] = str(testStop - self.mainObj.testStart)

            # Must verify for StOPPED state or else the session could not be deleted
            self.verifySessionForStoppedState()
            time.sleep(5)
                            
            self.mainObj.updateModuleStatusData(status="Collecting Artifacts")
            
            if self.mainObj.moduleProperties['getPdfResultsFile']:
                pdfFile = self.loadCoreObj.getPDFreport()
                if pdfFile:
                    self.mainObj.emailAttachmentList.append(pdfFile) ;# For emailResults
                    self.loadCoreObj.logInfo(f'pdfFile: {pdfFile}')

            if self.mainObj.moduleProperties['getCsvResultsFile']:
                csvFile = self.loadCoreObj.getCSVs(csvFilesToGet=loadcoreCsvResultsToVerify, convertCsvToJson=True)
                if csvFile:
                    self.loadCoreObj.logInfo(f'csvFile: {csvFile}')

            if self.mainObj.moduleProperties['getCapturesAndLogs']:
                # /Automation/Keysight_TestResults/LoadCore/12-09-2021-17:12:28:592709/01_20UE_NGRAN_Simulation_450Mbps_HTTP_DL_Throughput_test/TC1_20UE_NGRAN_Simulation_450Mbps_HTTP_DL_Throughput_Test-wireless-fb7a8355-9caa-4867-af0f-f49ea5dfc366.zip
                capturedLogs = self.loadCoreObj.getCapturedLogs()
                if capturedLogs:
                    self.loadCoreObj.logInfo(f'capturedLogs: {capturedLogs}')
                        
            self.loadCoreObj.logInfo(f'KPI Results: {json.dumps(self.kpiStatTracker[self.eachTestcase], indent=4)}')
                
            # ------ Verify KPI test results ----
            for csvResultFile, values in self.kpiStatTracker[self.eachTestcase].items():
                for kpi,values in values.items():
                    if values['result'] == 'failed':
                        self.mainObj.testcaseResult = 'Failed'
                        overallResult = 'Failed'
                        
                        self.mainObj.testcaseData['failures'].append({csvResultFile: {kpi: f"Result={values['result']}  ExpectedValue{values['expectedValue']}  MaxValue={values['maxValue']}" }})

                        # 1 or more test could have been aborted. We want to preserve the result status
                        if self.mainObj.moduleSummaryData['result'] != 'Incomplete':
                            self.mainObj.moduleSummaryData['result'] = 'Failed'
                            
                        # These counters are supposedly done automatically by using mainObj.logFailed(), but
                        # since this isn't logging a failure message, have to increment these counters here.
                        self.mainObj.playbookObj.overallSummaryData['totalFailures'] += 1
                        self.mainObj.moduleSummaryData['totalFailures'] += 1
                        self.mainObj.testcaseData['totalFailures'] += 1
                        self.mainObj.testcaseData['result'] = 'Failed'
                        
                    if values['result'] == 'passed':
                        self.mainObj.testcaseData['passed'].append({csvResultFile: {kpi: f"Result={values['result']}  ExpectedValue{values['expectedValue']}  MaxValue={values['maxValue']}" }})
                            
            self.mainObj.testcaseData['result'] = self.mainObj.testcaseResult

            #if self.mainObj.testcaseResult == 'Failed':
            #    self.mainObj.playbookObj.overallSummaryData['totalFailed'] += 1  
            #    self.mainObj.moduleSummaryData['totalFailed'] += 1
                                
            # Done testing
            self.mainObj.testcaseData['KPIs'] = self.kpiStatTracker[self.eachTestcase]

            if self.mainObj.moduleProperties['deleteSession']:
                if self.mainObj.testcaseResult == 'Failed' and self.mainObj.moduleProperties['deleteSessionOnFailure'] == False:
                    self.loadCoreObj.logInfo('Test failed. Not deleting test session.')
                else:
                    self.mainObj.updateModuleStatusData(status="Deleting Test Session")
                    time.sleep(3)
                    self.loadCoreObj.deleteSession()
                    
            if self.mainObj.moduleProperties['deleteTestLogsAndResultsOnLoadCore']:
                if self.mainObj.testcaseResult == 'Failed' and self.mainObj.moduleProperties['deleteSessionOnFailure'] == False:
                    self.loadCoreObj.logInfo('Test failed. Not deleting session, results and logs on LoadCore Middleware.')
                else:
                    self.loadCoreObj.deleteTestLogsAndResults()
            
            self.loadCoreObj.deleteTestConfig()
            
            # Safety check: Remove the wait time when license verification is added
            if len(self.testcaseSortedOrderList) > 1:
                if self.eachTestcase != self.testcaseSortedOrderList[-1]:
                    # Don't wait on the last testcase. Waste of time.  
                    self.loadCoreObj.logInfo(f'Testcase completed: {self.testcaseYmlFilename}\nWait {self.mainObj.waitTimeBetweenTests} seconds before running the next test to give some time for LoadCore Middleware to reset')
                    time.sleep(self.mainObj.waitTimeBetweenTests)
                    
        except Exception as errMsg:
            self.mainObj.updateModuleStatusData(status="Aborting")
            try:
                # Capture these sequences in a try/except because the abortion might 
                # not have a loadcore obj to delete the session
                if sessionStatus:
                    self.verifySessionForStoppedState()
                    
                if self.loadCoreObj.testId and self.mainObj.moduleProperties['deleteSession']:
                    if self.mainObj.moduleProperties['deleteSessionOnFailure']:
                        self.loadCoreObj.deleteSession()
                    else:
                        self.loadCoreObj.logInfo('Test aborting. Not deleting session')
            except Exception as errMsg2:
                pass
                                        
            # Pass the exception message to the main script try/except statement
            raise Exception(traceback.format_exc(None, errMsg))


def showLicenseDetails(licenseServerIp, licenseServerIpPort, login, password):
    """ 
    Show all the licenses on the license server to get all the required licenses
    so you could add them in the env yaml file.  This is for Keystack framework
    to verify if there is available licenses before starting test.
    For example:
    
    requiredLicenses:                                                                  
       - VMP-WRLS-5GC-UE: 1 
       - WRLS-5GC-UPFLOW: 1 
       - WRLS-5GC-UPTPUT-10G: 1 
       - VMP-WRLS-5GC-INTERFACE: 13
       - VMP-WRLS-5GC-RATE: 1
    """
    # Get all required licenses
    obj = LoadCoreLicense(licenseServerIp, licenseServerIpPort, login, password)
    obj.connect()
    obj.showLicenseDetails()
            
if __name__ == "__main__":
    showLicenseDetails('172.16.102.9', 7443, 'admin', 'admin')

