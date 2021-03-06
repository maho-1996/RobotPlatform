from django.shortcuts import render, redirect, Http404, HttpResponse
from django.contrib.auth.decorators import permission_required
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from .models import server, profile, uploadFile
import time, hmac, hashlib, json, socket
from .forms import profileForm, loginForm, userForm, uploadFileForm, downloadFileForm, commandForm
from django.contrib.auth.models import User
from ast import literal_eval
from .socketConnect import establishContainerConnect, establishRobotConnect, sendRequest
from Robot.settings import CONTAINER_TARGET_SERVER_IP, CONTAINER_TARGET_SERVER_PORT, ROBOT_TARGET_SERVER_IP, \
    ROBOT_TARGET_SERVER_PORT, MEDIA_ROOT, GateOneServer
from django.http import FileResponse
import os

# 该文件用于定义后台使用方法

# 全局变量，用于保存TCP连接对象

# 容器消息接收器TCP连接
global containerSock
# 实体机器人消息接收器TCP连接
global robotSock

# 全局变量，用于保存实体机器人ID和用户使用的关系对
realRobotDict = {}
# 全局变量，用于保存VNC连接容器和端口的关系对
VNCCOntainerDict = {}


# 建立TCP连接方法
def establishConnection():
    try:
        global containerSock
        global robotSock
        containerSock = establishContainerConnect(CONTAINER_TARGET_SERVER_IP, CONTAINER_TARGET_SERVER_PORT)
        robotSock = establishRobotConnect(ROBOT_TARGET_SERVER_IP, ROBOT_TARGET_SERVER_PORT)
    except:
        pass


# 测试连接方法
def testConnection():
    data = {'heartbeat': 'no'}
    jsonData = json.dumps(data)
    try:
        receivingMessage = sendRequest(containerSock, jsonData)
    except socket.timeout:
        return HttpResponse('timeout')
    except:
        establishConnection()


# 建立连接
establishConnection()
# 测试连接
testConnection()


# 创建SSH连接
def hostConnect(request):
    host_ip = request.POST.get('host', None)
    host_user = request.user.username
    host_port = request.POST.get('port', 22)

    if host_port == "": host_port = 22
    uniqueLabel = hash(time.time())
    print(host_port)
    return render(request, 'gateone.html',
                  {'host_ip': host_ip, 'host_user': host_user, 'host_port': host_port, 'uniqueLabel': uniqueLabel})


# SSH连接相关——创建签名
def createSignature(secret, *parts):
    hash = hmac.new(secret, digestmod=hashlib.sha1)
    for part in parts:
        hash.update(part.encode('utf-8'))
    return hash.hexdigest()


# 建立SSH连接相关——验证连接合法性
def getAuthObj(request):
    # 安装gateone的服务器以及端口.
    gateone_server = GateOneServer
    # 之前生成的api_key 和secret
    secret = 'MzAwNmVkODAwNGJlNDRmYjlkZTIxMDgyZjU2YTMyMDczN'
    api_key = 'MzUxMmRhNTY5YmY5NGNiNWE2ZmJkZGUwODIxY2VlNjYwZ'

    authobj = {
        'api_key': api_key,
        'upn': 'gateone',
        'timestamp': str(int(time.time() * 1000)),
        'signature_method': 'HMAC-SHA1',
        'api_version': '1.0'
    }

    authobj['signature'] = createSignature(secret.encode('utf-8'), authobj['api_key'], authobj['upn'],
                                           authobj['timestamp'])
    auth_info_and_server = {"url": gateone_server, "auth": authobj}
    valid_json_auth_info = json.dumps(auth_info_and_server)
    #   print valid_json_auth_info
    return HttpResponse(valid_json_auth_info)


# 虚拟机器人创建用户
def createUserRequest(request, serverName):
    _server = server.objects.get(hostName=serverName)
    serverPort = _server.hostPort
    userName = request.user.username
    data = {'createcuser':
                {'port': int(serverPort),
                 'username': userName}}
    jsonData = json.dumps(data)
    try:
        receivingMessage = sendRequest(containerSock, jsonData)
    except socket.timeout:
        return HttpResponse('timeout')
    if receivingMessage['createcuser']['response'] == 'ok':
        _user = request.user
        _serverNum = _user.profile.serverNum
        _serverNum = literal_eval(_serverNum)
        newServers = set(_serverNum)
        newServers.add(serverName)
        _user.profile.serverNum = str(list(newServers))
        _user.save()
        return redirect('/robotPage/')
    elif receivingMessage['createcuser']['response'] == 'fail':
        return HttpResponse('失败')
    else:
        raise Http404


# 虚拟机器人删除用户
def deleteUserRequest(request, serverName):
    _server = server.objects.get(hostName=serverName)
    serverPort = _server.hostPort
    userName = request.user.username
    data = {'deletecuser':
                {'port': int(serverPort),
                 'username': '%s' % userName}}
    jsonData = json.dumps(data)
    try:
        receivingMessage = sendRequest(containerSock, jsonData)
    except socket.timeout:
        return HttpResponse('timeout')
    if receivingMessage['deletecuser']['response'] == 'ok':
        _user = request.user
        _serverNum = _user.profile.serverNum
        _serverNum = literal_eval(_serverNum)
        newServers = set(_serverNum)
        newServers.remove(serverName)
        _user.profile.serverNum = str(list(newServers))
        _user.save()
        return redirect('/robotPage/')
    elif receivingMessage['deletecuser']['response'] == 'fail':
        return HttpResponse('失败')
    else:
        raise Http404


# 首页
def mainPage(request):
    if request.user.is_authenticated == True:
        return render(request, 'index.html', {'logStatus': request.user.is_authenticated, 'title': '机器人实验平台'})
    return render(request, 'loginPage.html', {'logStatus': request.user.is_authenticated, 'title': '机器人实验平台 - 登录'})


# 注册
def register(request):
    logStatus = request.user.is_authenticated
    serverNums = server.objects.all()
    if request.method == 'POST':
        _userForm = userForm(request.POST)
        if _userForm.is_valid():
            _username = request.POST.get('username')
            _password = request.POST.get('password')
            User.objects.create_user(username=_username, password=_password)
            _user = User.objects.select_related('profile').get(username=_username)
            _user.profile.serverNum = []
            _user.save()
            loginUser = auth.authenticate(username=_username, password=_password)
            if loginUser is not None and loginUser.is_active:
                auth.login(request, loginUser)
            return redirect('/')
    else:
        _userForm = userForm()
    return render(request, 'register.html',
                  {'userForm': _userForm, 'logStatus': logStatus,
                   'serverNums': serverNums, 'title': '机器人实验平台 - 注册'})


# 登录
def login(request):
    log_status = request.user.is_authenticated
    if request.method == 'POST':
        form = loginForm(request.POST)
        if form.is_valid():
            username = request.POST.get('username')
            password = request.POST.get('password')
            user = auth.authenticate(username=username, password=password)
            if user is not None and user.is_active:
                auth.login(request, user)
                return redirect('/')
            else:
                return render(request, 'loginPage.html',
                              {'form': form, 'password_is_wrong': True, 'logStatus': log_status})
    else:
        form = loginForm()
        return render(request, 'loginPage.html', {'form': form, 'logStatus': log_status, 'title': '机器人实验平台 - 登录'})


# 登出
@login_required(login_url="/login/")
def logout(request):
    auth.logout(request)
    return redirect('/')


# 修改用户使用的服务器（测试用方法，正式不使用）
@login_required(login_url="/login/")
def manageAccountServers(request):
    logStatus = request.user.is_authenticated
    serverNums = server.objects.all()
    if request.method == 'POST':
        _profileForm = profileForm(request.POST, instance=request.user.profile)
        if _profileForm.is_valid():
            _serverNum = request.POST.getlist('serverNum')
            _user = request.user
            _user.profile.serverNum = _serverNum
            _user.save()
            return redirect('/')
    else:
        _profileForm = profileForm(instance=request.user.profile)
    return render(request, 'modify.html',
                  {'profileForm': _profileForm, 'logStatus': logStatus,
                   'serverNums': serverNums})


# 连接虚拟机器人主页
@login_required(login_url="/login/")
def robotPage(request):
    logStatus = request.user.is_authenticated
    usingServers = literal_eval(request.user.profile.serverNum)
    print(usingServers)
    tempList = []
    for item in usingServers:
        tempList.append(server.objects.get(hostName=item))
    return render(request, 'robotPage.html', {'hosts': tempList, 'logStatus': logStatus, 'title': '机器人实验平台 - 连接虚拟机器人'})


# 用户管理虚拟机器人主页
@login_required(login_url="/login/")
def manageServers(request):
    logStatus = request.user.is_authenticated
    allServers = server.objects.values_list('hostName', flat=True)
    usingServers = literal_eval(request.user.profile.serverNum)
    notUsingServers = list(set(allServers) - set(usingServers))
    return render(request, 'manageServers.html',
                  {'usingHosts': usingServers, 'notUsingHosts': notUsingServers, 'logStatus': logStatus,
                   'title': '机器人实验平台 - 用户设置'})


# 连接实体机器人
@login_required(login_url="/login/")
def connectRobot(request):
    data = {'linkrobot':
                {'username': 'stu'}}
    jsonData = json.dumps(data)
    try:
        receivingMessage = sendRequest(robotSock, jsonData)
    except socket.timeout:
        return HttpResponse('timeout')
    if receivingMessage['linkrobot']['response'] == 'ok':
        robotIP = receivingMessage['linkrobot']['robotip']
        robotPort = receivingMessage['linkrobot']['robotport']
        robotNo = receivingMessage['linkrobot']['robotno']
        uniqueLabel = hash(time.time())
        global realRobotDict
        realRobotDict.setdefault(request.user.username, [])
        realRobotDict[request.user.username].append(robotNo)
        print(robotIP, robotPort, robotNo)
        return render(request, 'gateoneRobot.html',
                      {'host_ip': ROBOT_TARGET_SERVER_IP, 'host_user': 'stu', 'host_port': robotPort,
                       'robotNo': robotNo, 'uniqueLabel': uniqueLabel})
    elif receivingMessage['linkrobot']['response'] == 'fail':
        return HttpResponse(receivingMessage['linkrobot']['reason'])
    else:
        raise Http404


# 断开实体机器人连接
@login_required(login_url="/login/")
def disconnectRobot(request, _robotNo):
    data = {'unlinkrobot':
                {'robotno': _robotNo}}
    jsonData = json.dumps(data)
    try:
        receivingMessage = sendRequest(robotSock, jsonData)
    except socket.timeout:
        return HttpResponse('timeout')
    if receivingMessage['unlinkrobot']['response'] == 'ok':
        robotNo = receivingMessage['unlinkrobot']['robotno']
        global realRobotDict
        realRobotDict[request.user.username].remove(robotNo)
        print(robotNo)
        return HttpResponse('released robot')
    elif receivingMessage['unlinkrobot']['response'] == 'fail':
        return HttpResponse(receivingMessage['unlinkrobot']['reason'])
    else:
        raise Http404


# 虚拟机器人上传文件
@login_required(login_url="/login/")
def uploadUserFile(request):
    logStatus = request.user.is_authenticated
    usingServers = literal_eval(request.user.profile.serverNum)
    tempList = []
    for item in usingServers:
        tempList.append(server.objects.get(hostName=item))
    if request.method == 'POST':
        _uploadFile = uploadFileForm(request.POST, request.FILES)
        if _uploadFile.is_valid():
            _file = request.FILES.get('uploadFile')
            _targetContainer = request.POST.get('targetContainer')
            userFile = uploadFile(belongTo=request.user, file=_file, targetContainer=_targetContainer)
            userFile.save()

            containerPort = server.objects.get(hostName=_targetContainer).hostPort
            data = {'cupload':
                        {'port': int(containerPort),
                         'image': 'containerName',
                         'username': request.user.username,
                         'filename': userFile.getFileName()}}
            jsonData = json.dumps(data)
            try:
                receivingMessage = sendRequest(containerSock, jsonData)
            except socket.timeout:
                return HttpResponse('timeout')
            if receivingMessage['cupload']['response'] == 'ok':
                return HttpResponse('success')
            elif receivingMessage['cupload']['response'] == 'failed':
                return HttpResponse('fail')
            else:
                return HttpResponse(receivingMessage)
    else:
        _uploadFile = uploadFileForm()
    return render(request, 'uploadFilePage.html',
                  {'uploadFileForm': _uploadFile, 'logStatus': logStatus, 'tempList': tempList,
                   'title': '机器人实验平台 - 虚拟机器人文件上传'})


# 虚拟机器人下载文件
@login_required(login_url="/login/")
def downloadUserFilePage(request):
    def getFilePath(filePath):
        tempFileName = filePath.replace('/', '+')
        tempFileName = tempFileName.replace(' ', '=')
        return tempFileName

    def getFileName(filePath):
        return filePath.split('/')[-1]

    logStatus = request.user.is_authenticated
    userFiles = uploadFile.objects.filter(belongTo=request.user)
    usingServers = literal_eval(request.user.profile.serverNum)
    tempList = []
    for item in usingServers:
        tempList.append(server.objects.get(hostName=item))
    if request.method == 'POST':
        _downloadFile = downloadFileForm(request.POST)
        if _downloadFile.is_valid():
            _filename = request.POST.get('filename')
            _targetContainer = request.POST.get('targetContainer')
            containerPort = server.objects.get(hostName=_targetContainer).hostPort

            data = {'cdownload':
                        {'port': int(containerPort),
                         'image': 'containerName',
                         'username': request.user.username,
                         'filename': _filename}}
            jsonData = json.dumps(data)
            try:
                receivingMessage = sendRequest(containerSock, jsonData)
            except socket.timeout:
                return HttpResponse('timeout')
            if receivingMessage['cdownload']['response'] == 'ok':
                _file = os.path.join(MEDIA_ROOT, 'files', request.user.username, _filename)

                # 只保存文件到数据库，不下载
                # _targetContainer = request.POST.get('targetContainer')
                # userFile = uploadFile()
                # userFile.belongTo = request.user
                # userFile.file.name = _file
                # userFile.targetContainer = _targetContainer
                # userFile.save()
                # return HttpResponse('success')

                # 直接下载文件
                return redirect('/downloadFile/' + getFilePath(_file))
            elif receivingMessage['cdownload']['response'] == 'fail':
                return HttpResponse('fail')
            else:
                return HttpResponse(receivingMessage)
    else:
        _downloadFile = downloadFileForm()
    return render(request, 'downloadFilePage.html',
                  {'downloadFileForm': _downloadFile, 'tempList': tempList, 'userFiles': userFiles,
                   'logStatus': logStatus, 'title': '机器人实验平台 - 虚拟机器人文件下载'})


# 文件下载
@login_required(login_url="/login/")
def downloadUserFile(request, filePath):
    realFilePath = filePath.replace('+', '/')
    realFilePath = realFilePath.replace('=', ' ')
    filename = realFilePath.split('/')[-1]
    file = open(realFilePath, 'rb')
    response = FileResponse(file)
    response['Content-Type'] = 'application/octet-stream'
    response['Content-Disposition'] = 'attachment;filename="%s' % filename
    return response


# 连接仿真终端
@login_required(login_url="/login/")
def connectVNC(request, serverName):
    userName = request.user.username
    data = {'linkcontainer':
                {'image': serverName,
                 'username': '%s' % userName}}
    jsonData = json.dumps(data)
    try:
        receivingMessage = sendRequest(containerSock, jsonData)
        global VNCCOntainerDict
        VNCCOntainerDict.setdefault(serverName, receivingMessage['port'])
    except socket.timeout:
        return HttpResponse('timeout')
    if receivingMessage['ccontrol']['response'] == 'ok':
        return redirect(
            'http://222.200.177.38:8080/vnc_lite.html?host=222.200.177.38&port=%s' % receivingMessage['port'])
    elif receivingMessage['ccontrol']['response'] == 'fail':
        return HttpResponse('失败')
    else:
        raise Http404


# 断开仿真终端连接
@login_required(login_url="/login/")
def disconnectVNC(request, serverName):
    userName = request.user.username
    data = {'unlinkcontainer':
                {'image': serverName,
                 'port': VNCCOntainerDict['serverName'],
                 'username': '%s' % userName}}
    jsonData = json.dumps(data)
    try:
        receivingMessage = sendRequest(containerSock, jsonData)
    except socket.timeout:
        return HttpResponse('timeout')
    if receivingMessage['ccontrol']['response'] == 'ok':
        return HttpResponse('success')
    elif receivingMessage['ccontrol']['response'] == 'failed':
        return HttpResponse('失败')
    else:
        raise Http404


# 批量控制
@login_required(login_url="/login/")
def makeControl(request):
    logStatus = request.user.is_authenticated
    usingServers = literal_eval(request.user.profile.serverNum)
    tempList = []
    for item in usingServers:
        tempList.append(server.objects.get(hostName=item))
    if request.method == 'POST':
        _profileForm = profileForm(request.POST)
        _commandForm = commandForm(request.POST)
        if _profileForm.is_valid() and _commandForm.is_valid():
            _serverNum = request.POST.getlist('serverNum')
            _command = request.POST.get('command')
            containerPort = server.objects.get(hostName=_serverNum[0]).hostPort
            data = {'ccontrol':
                        {'port': int(containerPort),
                         'image': 'containerName',
                         'username': request.user.username,
                         'command': _command}}
            jsonData = json.dumps(data)
            try:
                receivingMessage = sendRequest(containerSock, jsonData)
            except socket.timeout:
                return HttpResponse('timeout')
            if receivingMessage['ccontrol']['response'] == 'ok':
                return HttpResponse('success')
            elif receivingMessage['ccontrol']['response'] == 'failed':
                return HttpResponse('fail')
            else:
                return HttpResponse(receivingMessage)
    else:
        _profileForm = profileForm()
        _commandForm = commandForm()
    return render(request, 'makeControl.html',
                  {'profileForm': _profileForm, 'commandForm': _commandForm, 'tempList': tempList,
                   'logStatus': logStatus, 'title': '机器人实验平台 - 远程控制'})


# 连接虚拟机器人
@login_required(login_url="/login/")
def connectContainer(request, serverName):
    _server = server.objects.get(hostName=serverName)
    serverPort = _server.hostPort
    userName = request.user.username
    data = {'linkcontainer':
                {'image': serverName,
                 'port': int(serverPort),
                 'username': '%s' % userName}}
    jsonData = json.dumps(data)
    try:
        receivingMessage = sendRequest(containerSock, jsonData)
    except socket.timeout:
        return HttpResponse('timeout')
    if receivingMessage['linkcontainer']['response'] == 'ok':
        serverIP = _server.hostIP
        uniqueLabel = hash(time.time())
        return render(request, 'gateoneRobot.html',
                      {'host_ip': serverIP, 'host_user': userName, 'host_port': serverPort, 'host_name': serverName,
                       'uniqueLabel': uniqueLabel})
    elif receivingMessage['linkcontainer']['response'] == 'fail':
        return HttpResponse(receivingMessage['linkcontainer']['reason'])
    else:
        raise Http404


# 断开虚拟机器人连接
@login_required(login_url="/login/")
def disconnectContainer(request, serverName):
    _server = server.objects.get(hostName=serverName)
    serverPort = _server.hostPort
    userName = request.user.username
    data = {'unlinkcontainer':
                {'image': serverName,
                 'port': int(serverPort),
                 'username': '%s' % userName}}
    jsonData = json.dumps(data)
    try:
        receivingMessage = sendRequest(containerSock, jsonData)
    except socket.timeout:
        return HttpResponse('timeout')
    if receivingMessage['unlinkcontainer']['response'] == 'ok':
        return HttpResponse('unlinked')
    else:
        raise Http404


# 实体机器人上传文件
@login_required(login_url="/login/")
def RUploadUserFile(request):
    logStatus = request.user.is_authenticated
    global realRobotDict
    tempList = realRobotDict[request.user.username]
    if request.method == 'POST':
        _uploadFile = uploadFileForm(request.POST, request.FILES)
        if _uploadFile.is_valid():
            _file = request.FILES.get('uploadFile')
            _targetContainer = request.POST.get('targetContainer')
            userFile = uploadFile(belongTo=request.user, file=_file, targetContainer=_targetContainer)
            userFile.save()

            data = {'rupload':
                        {'robotno': int(_targetContainer),
                         'username': request.user.username,
                         'filename': userFile.getFileName()}}
            jsonData = json.dumps(data)
            try:
                receivingMessage = sendRequest(robotSock, jsonData)
            except socket.timeout:
                return HttpResponse('timeout')
            if receivingMessage['rupload']['response'] == 'ok':
                return HttpResponse('success')
            elif receivingMessage['rupload']['response'] == 'failed':
                return HttpResponse('fail')
            else:
                return HttpResponse(receivingMessage)
    else:
        _uploadFile = uploadFileForm()
    return render(request, 'RUploadFilePage.html',
                  {'uploadFileForm': _uploadFile, 'logStatus': logStatus, 'tempList': tempList,
                   'title': '机器人实验平台 - 实体机器人文件上传'})


# 实体机器人下载文件
@login_required(login_url="/login/")
def RDownloadUserFilePage(request):
    def getFilePath(filePath):
        tempFileName = filePath.replace('/', '+')
        tempFileName = tempFileName.replace(' ', '=')
        return tempFileName

    def getFileName(filePath):
        return filePath.split('/')[-1]

    logStatus = request.user.is_authenticated
    userFiles = uploadFile.objects.filter(belongTo=request.user)
    global realRobotDict
    tempList = realRobotDict[request.user.username]
    if request.method == 'POST':
        _downloadFile = downloadFileForm(request.POST)
        if _downloadFile.is_valid():
            _filename = request.POST.get('filename')
            _targetContainer = request.POST.get('targetContainer')

            data = {'rdownload':
                        {'robotno': int(_targetContainer),
                         'username': request.user.username,
                         'filename': _filename}}
            jsonData = json.dumps(data)
            try:
                receivingMessage = sendRequest(robotSock, jsonData)
            except socket.timeout:
                return HttpResponse('timeout')
            if receivingMessage['rdownload']['response'] == 'ok':
                _file = os.path.join(MEDIA_ROOT, 'files', request.user.username, _filename)
                # _targetContainer = request.POST.get('targetContainer')
                # userFile = uploadFile()
                # userFile.belongTo = request.user
                # userFile.file.name = _file
                # userFile.targetContainer = _targetContainer
                # userFile.save()
                # return HttpResponse('success')
                return redirect('/downloadFile/' + getFilePath(_file))
            elif receivingMessage['rdownload']['response'] == 'fail':
                return HttpResponse('fail')
            else:
                return HttpResponse(receivingMessage)
    else:
        _downloadFile = downloadFileForm()
    return render(request, 'RDownloadFilePage.html',
                  {'downloadFileForm': _downloadFile, 'tempList': tempList, 'userFiles': userFiles,
                   'logStatus': logStatus, 'title': '机器人实验平台 - 实体机器人文件下载'})
