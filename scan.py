import requests
import os
from bs4 import BeautifulSoup
import time
import schedule
import json

username = os.environ.get('GITHUB_USERNAME')
token = os.environ.get('GITHUB_TOKEN')
repository = os.environ.get('GITHUB_ORG_NAME')
wekbook_url = os.environ.get('SLACK_WEBHOOK_URL')
cloningpath = "cloning_path"
signature_file = "mount/signature.json"

def getMembersAPIURL():
    return 'https://api.github.com/orgs/' + repository + '/members'

def getRepoAPIUrlForUser(user):
    return 'https://api.github.com/users/' + user + '/repos'

def getCommitsAPIForRepo(user , repo):
    return 'https://api.github.com/repos/' + user + '/' + repo + '/commits'

def getGithubUsernameListFromResponse(responsejson):
    usernamelist = []
    for i in responsejson:
        usernamelist.append(i['login'])
    return usernamelist

def getCompleteUserNameList():
    response = requests.get(getMembersAPIURL(), auth=(username, token))
    completeUserNameList = getGithubUsernameListFromResponse(response.json())
    while 'next' in response.links:
        response = requests.get(response.links['next']['url'], auth=(username, token))
        completeUserNameList.extend(getGithubUsernameListFromResponse(response.json()))
    return completeUserNameList

def getInfoListForUsers(usernamelist):
    infoList = []
    for user in usernamelist:
        githubResponseForRepos = requests.get(getRepoAPIUrlForUser(user), auth=(username, token))
        publicReposList = githubResponseForRepos.json()
        # getting only the user repositories which are not forked
        for repoJSON in publicReposList:
            if ('fork' in repoJSON) and (not repoJSON["fork"]):
                # get all latest commits of an user
                gitHubResponseForCommits = requests.get(getCommitsAPIForRepo(user, repoJSON['name']),auth=(username, token))
                commitsJSON = gitHubResponseForCommits.json()
                if not ('message' in commitsJSON):
                    latestCommit = commitsJSON[0]['sha']
                    repoMap = constructGithubInfoMapForUser(latestCommit, repoJSON, user)
                    infoList.append(repoMap)
    return infoList

def constructGithubInfoMapForUser(commitsHistoryList, repoJSON, user):
    repoMap = {}
    repoMap['repo_name'] = repoJSON['name']
    repoMap['git_url'] = repoJSON['git_url']
    repoMap['github_user'] = user
    repoMap['commit_id'] = commitsHistoryList
    return repoMap

def doscheduledjob():
    if not flag:
        return
    for repoInfo in infoList:
        gitHubResponseForCommits = requests.get(
            'https://api.github.com/repos/' + repoInfo['github_user'] + '/' + repoInfo['repo_name'] + '/commits', auth=(username, token))
        commitsJSON = gitHubResponseForCommits.json()

        if not ('message' in commitsJSON):
            commitsToBeScanned = []
            for i in commitsJSON:
                if repoInfo['commit_id'] == i['sha']:
                    break
                else:
                    commitsToBeScanned.append(i['sha'])
            if len(commitsToBeScanned) == 0 :
                print("it is the same for " + repoInfo['repo_name'])
            else:
                for newCommit in commitsToBeScanned:
                    doScan(newCommit, repoInfo, cloningpath)
                    repoInfo['commit_id'] = newCommit
        else:
            print("empty repo...",repoInfo['repo_name'])

def doScan(commitID, repoInfo, cloningpath):
    print(' new commit is ' + commitID)
    commitAPIURL = 'https://api.github.com/repos/' + repoInfo['github_user'] + '/' + repoInfo[
        'repo_name'] + '/compare/' + repoInfo['commit_id'] + '...' + commitID
    commitsAPIResponseJSON = requests.get(commitAPIURL, auth=(username, token)).json()
    if 'files' in commitsAPIResponseJSON:
        changedFiles = commitsAPIResponseJSON['files']
        changedFilesList = []
        for file in changedFiles:
            if 'raw_url' in file:
                newFileURL = file['raw_url']
                changedFilesList.append(file['blob_url'])
                fileName = file['filename']
                if not os.path.exists(cloningpath):
                    os.mkdir(cloningpath)
                if not os.path.exists(cloningpath + "/" + commitID):
                    os.mkdir(cloningpath + "/" + commitID)
                fileName = cloningpath + "/" + commitID + "/" + fileName

                print('new file...', newFileURL)
                r = requests.get(newFileURL)
                soup = BeautifulSoup(r.content, 'html5lib')

                with open(fileName, "w") as file1:
                    file1.write(soup.get_text())

        time.sleep(10)
        with open(signature_file) as f:
            signature_json = json.load(f)
        parentlist = signature_json.get("signatures")
        fullpath = cloningpath + "/" + commitID
        for i in parentlist:
            stringtoconcatenate = ""
            if "part" in i and "contents" == i.get("part"):
                if "match" in i:
                    stringtoconcatenate = i.get("match")
                    stringtoconcatenate = "grep -rnE --exclude-dir='.*' \"" + stringtoconcatenate + "$\" " + fullpath + " ; "

                elif "regex" in i:
                    stringtoconcatenate = i.get("regex")
                    stringtoconcatenate = stringtoconcatenate.replace("^", "")
                    stringtoconcatenate = stringtoconcatenate.replace('\\', "\\\\")
                    stringtoconcatenate = stringtoconcatenate.replace('/', "\/")
                    stringtoconcatenate = "grep -rnE --exclude-dir='.*' \"(" + stringtoconcatenate + ")\" " + fullpath + " ; "
            else:
                if "match" in i:
                    stringtoconcatenate = i.get("match")
                    stringtoconcatenate = "find " + fullpath + " -name " + stringtoconcatenate
                elif "regex" in i:
                    stringtoconcatenate = i.get("regex")
                    stringtoconcatenate = stringtoconcatenate.replace("^", "")
                    stringtoconcatenate = stringtoconcatenate.replace('\\', "\\\\")
                    stringtoconcatenate = stringtoconcatenate.replace('/', "\/")
                    stringtoconcatenate = "find " + fullpath + " -regex \"" + stringtoconcatenate + "\""
            command = "cd " + fullpath + " ; " + stringtoconcatenate
            result = os.popen(command).read()
            if result:
                resultMap = repoInfo
                resultMap['result'] = result
                resultMap['commit_id'] = commitID
                resultMap['url'] = changedFilesList
                sendSlackNotifications(resultMap, cloningpath + "/" + commitID+"/")

def sendSlackNotifications(resultMap, searchPath):
    data = constructSlackMsg(resultMap, searchPath)
    response = requests.post(wekbook_url, data=json.dumps(
        data), headers={'Content-Type': 'application/json'})

def constructSlackMsg(resultMap, searchPath):
    urls = ""
    for i in resultMap['url']:
        urls = urls+i+"\n"
    resultTrace = str(resultMap['result'])
    resultTrace = resultTrace.replace(searchPath,"" )
    print(resultTrace)
    data = {
        "blocks": [{
            "type": "divider"
        },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Sensitive information found in File(s):* "+urls
                }
            },
            {
                "type": "section",
                "fields": [{
                    "type": "mrkdwn",
                    "text": "*github_user:*\n"+resultMap['github_user']
                },
                    {
                        "type": "mrkdwn",
                        "text": "*repo_name:*\n"+resultMap['repo_name']
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*commit_id:*\n"+resultMap['commit_id']
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*result(s):*\n"+resultTrace
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
    }
    return data

def doJobToGetUserInfoList():
    print("collecting github repo info...")
    global infoList
    global flag
    flag = False
    usernamelist = getCompleteUserNameList()
    # usernamelist = [username]
    print('total users... ', len(usernamelist))
    print('starting to get repo information of users...')
    infoList = getInfoListForUsers(usernamelist)
    flag = True

infoList= []
flag = False
if (__name__ == "__main__"):
    print('starting incremental scan...')
    doJobToGetUserInfoList()
    doscheduledjob()
    schedule.every(30).days.do(doJobToGetUserInfoList)
    schedule.every(1).hour.do(doscheduledjob)
    while True:
        schedule.run_pending()
        time.sleep(1)