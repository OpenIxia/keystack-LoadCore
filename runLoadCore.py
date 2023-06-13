"""
Tested with LoadCore 2.20, 2.30, 3.20, 3.40
"""

import traceback
from keystackEnv import keystackObj
from LoadCore.LoadCoreLib import Main
    
try:
    # TODO: Bogdan will provided new rest apis to verify required licenses for license verification
    '''
    # License check: Returns None if all licenses are available. Return a list of license not avaiable.
    lcLicenseObj = LoadCoreLicense(mainObj.moduleProperties['envParams']['licenseServerIp'],
    mainObj.moduleProperties['envParams']['licenseIpPort'],
    mainObj.moduleProperties['envParams']['licenseServerUser'], 
    mainObj.moduleProperties['envParams']['licenseServerPassword'],
    mainObj.testcaseDebugLogFile)

    if 'requiredLicenses' in mainObj.moduleProperties['envParams']:
        licenseCheckResult = lcLicenseObj.checkForLicenses(mainObj.moduleProperties['envParams']['requiredLicenses'])
        if licenseCheckResult:
            raise Exception(f'LoadCore licenses are not available: {licenseCheckResult}')
    '''

    Main(keystackObj).runTestcase()

except Exception as errMsg:
    raise Exception(traceback.format_exc(None, errMsg))

