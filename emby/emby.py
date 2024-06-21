import uuid
import json
from _thread import start_new_thread
import _socket
import xbmc
from dialogs import serverconnect, usersconnect, loginconnect, loginmanual, servermanual
from helper import utils, playerops, pluginmenu
from database import library
from . import views, api, http


class EmbyServer:
    def __init__(self, ServerSettings):
        self.ShutdownInProgress = False
        self.EmbySession = []
        self.Found_Servers = []
        self.ServerSettings = ServerSettings
        self.Firstrun = not bool(self.ServerSettings)
        self.ServerData = {'AccessToken': "", 'UserId': "", 'UserName': "", 'UserImageUrl': "", 'ServerName': "", 'ServerId': "", 'ServerUrl': "", 'EmbyConnectExchangeToken': "", 'EmbyConnectUserId': "", 'EmbyConnectUserName': "", 'EmbyConnectAccessToken': "", 'ManualAddress': "", 'RemoteAddress': "", 'LocalAddress': "" ,'AdditionalUsers': {}, "DeviceId": "", "ServerVersion": ""}
        self.ServerReconnecting = False
        self.http = http.HTTP(self)
        self.API = api.API(self)
        self.Views = views.Views(self)
        self.library = library.Library(self)
        self.Online = False
        xbmc.log("EMBY.emby.emby: ---[ INIT EMBYCLIENT: ]---", 1) # LOGINFO

    def ServerReconnect(self):
        if self.Firstrun:
            return

        if not self.ServerReconnecting:
            start_new_thread(self.worker_ServerReconnect, ())

    def worker_ServerReconnect(self):
        xbmc.log(f"EMBY.emby.emby: THREAD: --->[ Reconnecting ] {self.ServerData['ServerName']} / {self.ServerData['ServerId']}", 0) # LOGDEBUG

        if not self.ServerReconnecting:
            utils.Dialog.notification(heading=utils.addon_name, icon="DefaultIconError.png", message=utils.Translate(33575), time=utils.displayMessage, sound=False)
            utils.SyncPause.update({f"server_reconnecting_{self.ServerData['ServerId']}": True, f"server_busy_{self.ServerData['ServerId']}": False})
            self.ServerReconnecting = True

            while True:
                self.stop()

                if utils.sleep(1):
                    break

                if not self.ServerData['ServerUrl']:
                    xbmc.log("EMBY.emby.emby: Reconnect exit by empty ServerUrl", 1) # LOGINFO
                    break

                xbmc.log(f"EMBY.emby.emby: Reconnect try again: {self.ServerData['ServerName']} / {self.ServerData['ServerId']}", 1) # LOGINFO

                if self.ServerHandshake():
                    self.start()
                    break

            utils.SyncPause[f"server_reconnecting_{self.ServerData['ServerId']}"] = False
            self.ServerReconnecting = False

        xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Reconnecting ] {self.ServerData['ServerName']} / {self.ServerData['ServerId']}", 0) # LOGDEBUG

    def start(self):
        xbmc.log(f"EMBY.emby.emby: ---[ START EMBYCLIENT: {self.ServerData['ServerName']} / {self.ServerData['ServerId']}]---", 1) # LOGINFO
        utils.SyncPause[f"server_starting_{self.ServerData['ServerId']}"] = True
        self.Online = True
        self.library.load_settings()
        playerops.init_RemoteClient(self.ServerData['ServerId'])
        self.Views.update_views()
        self.Views.update_nodes()
        self.http.start()
        start_new_thread(self.library.KodiStartSync, (self.Firstrun,))  # start initial sync
        self.Firstrun = False

        if utils.connectMsg:
            utils.Dialog.notification(heading=utils.addon_name, message=f"{utils.Translate(33000)} {self.ServerData['UserName']}", icon=self.ServerData['UserImageUrl'], time=utils.displayMessage, sound=False)

        utils.SyncPause[f"server_starting_{self.ServerData['ServerId']}"] = False
        xbmc.log("EMBY.emby.emby: [ Server Online ]", 1) # LOGINFO

    def stop(self):
        xbmc.log(f"EMBY.emby.emby: --->[ STOP EMBYCLIENT: {self.ServerData['ServerId']} ]---", 1) # LOGINFO

        if self.EmbySession and not self.ShutdownInProgress:
            xbmc.log("EMBY.emby.emby: Emby client stop", 0) # LOGDEBUG
            self.ShutdownInProgress = True
            utils.SyncPause.update({f"server_starting_{self.ServerData['ServerId']}": True, f"server_busy_{self.ServerData['ServerId']}": False})
            playerops.delete_RemoteClient(self.ServerData['ServerId'], [self.EmbySession[0]['Id']], True)
            self.EmbySession = []
            self.Online = False
            self.ShutdownInProgress = False
        else:
            xbmc.log("EMBY.emby.emby: Emby client already closed", 0) # LOGDEBUG

        self.http.stop()
        xbmc.log(f"EMBY.emby.emby: ---<[ STOP EMBYCLIENT: {self.ServerData['ServerId']} ]---", 1) # LOGINFO

    def add_AdditionalUser(self, UserId, UserName):
        self.ServerData['AdditionalUsers'][UserId] = UserName
        self.save_credentials()
        self.API.session_add_user(self.EmbySession[0]['Id'], UserId, True)

    def remove_AdditionalUser(self, UserId):
        if UserId in self.ServerData['AdditionalUsers']:
            del self.ServerData['AdditionalUsers'][UserId]

        self.save_credentials()
        self.API.session_add_user(self.EmbySession[0]['Id'], UserId, False)

    # Login into server. If server is None, then it will show the proper prompts to login, etc.
    # If a server id is specified then only a login dialog will be shown for that server.
    def ServerInitConnection(self):
        xbmc.log("EMBY.emby.emby: --[ server/DEFAULT ]", 1) # LOGINFO

        # load credentials from file
        if self.ServerSettings:
            FileData = utils.readFileString(self.ServerSettings)

            if FileData:
                LoadedServerSettings = json.loads(FileData)

                if 'ServerId' in LoadedServerSettings and LoadedServerSettings['ServerId']: # file content is valid
                    self.ServerData = LoadedServerSettings

            utils.DatabaseFiles[self.ServerData['ServerId']] = utils.translatePath(f"special://profile/Database/emby_{self.ServerData['ServerId']}.db")
        else:
            self.ServerData["DeviceId"] = str(uuid.uuid4())

        # Refresh EmbyConnect Emby server addresses (dynamic IP)
        if self.ServerData["EmbyConnectAccessToken"]:
            xbmc.log("EMBY.emby.emby: Refresh Emby server urls from EmbyConnect", 1) # LOGINFO
            EmbyConnectServers = self.API.get_embyconnect_servers()

            if EmbyConnectServers:
                for EmbyConnectServer in EmbyConnectServers:
                    if EmbyConnectServer['SystemId'] == self.ServerData['ServerId']:
                        if self.ServerData['RemoteAddress'] != EmbyConnectServer['Url'] or self.ServerData['LocalAddress'] != EmbyConnectServer['LocalAddress']: # update server settings
                            self.ServerData.update({'RemoteAddress': EmbyConnectServer['Url'], 'LocalAddress': EmbyConnectServer['LocalAddress']})
                            self.save_credentials()
                            xbmc.log("EMBY.emby.emby: Update Emby server urls from EmbyConnect", 1) # LOGINFO

                        xbmc.log("EMBY.emby.emby: Refresh Emby server urls from EmbyConnect, found", 1) # LOGINFO
                        break

        if self.Firstrun:
            SignedIn = True
            self.ServerDetect()

            # Menu dialogs
            while True:
                if utils.SystemShutdown:
                    SignedIn = False
                    break

                Dialog = serverconnect.ServerConnect("script-emby-connect-server.xml", *utils.CustomDialogParameters)
                Dialog.Servers = self.Found_Servers
                Dialog.UserImageUrl = self.ServerData['UserImageUrl']
                Dialog.emby_connect = not self.ServerData['UserId']
                Dialog.doModal()
                ConnectionMode = Dialog.ConnectionMode
                self.ServerData.update(Dialog.ServerSelected)
                del Dialog

                if ConnectionMode == "ListSelection":
                    isValid, _, _ = self.TestConnections()

                    if isValid:
                        Password = self.UserSelection()

                        if self.ServerLogin(Password):
                            if self.ServerHandshake():
                                break
                elif ConnectionMode == "ManualAddress":
                    xbmc.log("EMBY.emby.emby: Adding manual server", 0) # LOGDEBUG
                    Dialog = servermanual.ServerManual("script-emby-connect-server-manual.xml", *utils.CustomDialogParameters)
                    Dialog.doModal()
                    self.ServerData['ManualAddress'] = Dialog.ManualAddress
                    del Dialog

                    if self.ServerData['ManualAddress']:
                        isValid, _, _ = self.TestConnections()

                        if isValid:
                            Password = self.UserSelection()

                            if self.ServerLogin(Password):
                                if self.ServerHandshake():
                                    break
                elif ConnectionMode == "EmbyConnect":
                    Dialog = loginconnect.LoginConnect("script-emby-connect-login.xml", *utils.CustomDialogParameters)
                    Dialog.doModal()
                    Username, Password = Dialog.Login
                    del Dialog

                    if Username and Password:
                        self.EmbyConnectServers(Username, Password)
                        continue
                else: # cancel
                    SignedIn = False
                    break

            if SignedIn:
                self.save_credentials()
                utils.EmbyServers[self.ServerData['ServerId']] = self
                self.start()
                return

        # re-establish connection
        utils.EmbyServers[self.ServerData['ServerId']] = self
        start_new_thread(self.EstablishExistingConnection, ())

    def EstablishExistingConnection(self):
        xbmc.log("EMBY.emby.emby: THREAD: --->[ EstablishExistingConnection ]", 0) # LOGDEBUG
        isValid, Resync, SaveConfig = self.TestConnections()

        if isValid:
            ForceResync = False

            if Resync:
                xbmc.log("EMBY.emby.emby: EstablishExistingConnection: init resync", 0) # LOGDEBUG
                ForceResync = utils.Dialog.yesno(heading=utils.addon_name, message=utils.Translate(33222)) # final warning

                if not ForceResync: # final warning
                    xbmc.log("EMBY.emby.emby: THREAD: ---<[ EstablishExistingConnection ] resync abort", 0) # LOGDEBUG
                    return

            if self.ServerHandshake():
                self.start()

                if ForceResync:
                    xbmc.log("EMBY.emby.emby: EstablishExistingConnection: init resync", 0) # LOGDEBUG
                    self.ServerData["ServerVersion"] = Resync
                    self.save_credentials()
                    pluginmenu.factoryreset(True, True)
                elif SaveConfig:
                    xbmc.log("EMBY.emby.emby: EstablishExistingConnection: Save config", 0) # LOGDEBUG
                    self.save_credentials()

        xbmc.log("EMBY.emby.emby: THREAD: ---<[ EstablishExistingConnection ]", 0) # LOGDEBUG

    def save_credentials(self):
        if not self.ServerSettings:
            self.ServerSettings = f"{utils.FolderAddonUserdata}servers_{self.ServerData['ServerId']}.json"

        utils.writeFileString(self.ServerSettings, json.dumps(self.ServerData, sort_keys=True, indent=4, ensure_ascii=False))

    def ServerDisconnect(self):
        xbmc.log("EMBY.emby.emby: Disconnect", 1) # LOGINFO
        utils.EmbyServers[self.ServerData['ServerId']].API.session_logout()
        utils.EmbyServers[self.ServerData['ServerId']].stop()
        utils.delFile(f"{utils.FolderAddonUserdata}servers_{self.ServerData['ServerId']}.json")
        self.EmbySession = []
        self.Online = False

    def ServerHandshake(self):
        self.EmbySession = self.API.get_device()

        if not self.EmbySession:
            xbmc.log(f"EMBY.emby.emby: ---[ SESSION ERROR EMBYCLIENT: {self.ServerData['ServerId']} ] {self.EmbySession} ---", 3) # LOGERROR
            self.http.stop()
            return False

        if not self.ServerData['UserName']:
            self.ServerData['UserName'] = self.EmbySession[0]['UserName']

        self.API.post_capabilities()

        for AdditionalUserId in self.ServerData['AdditionalUsers']:
            AddUser = True

            for SessionAdditionalUser in self.EmbySession[0]['AdditionalUsers']:
                if SessionAdditionalUser['UserId'] == AdditionalUserId:
                    AddUser = False
                    break

            if AddUser:
                if utils.connectMsg:
                    utils.Dialog.notification(heading=utils.addon_name, message=f"{utils.Translate(33067)} {self.ServerData['AdditionalUsers'][AdditionalUserId]}", icon=utils.icon, time=utils.displayMessage, sound=False)
                self.API.session_add_user(self.EmbySession[0]['Id'], AdditionalUserId, True)

        return True

    def UserSelection(self):
        Username = ""
        Users = self.API.get_public_users()

        if Users:
            UsersInfo = []

            for User in Users:
                UserData = User.copy()
                UserData['UserImageUrl'] = utils.icon

                # Download user picture
                BinaryData, _, FileExtension = self.API.get_Image_Binary(UserData['Id'], "Primary", 0, 0, True)

                if BinaryData:
                    Filename = utils.valid_Filename(f"{self.ServerData['ServerName']}_{UserData['Name']}_{UserData['Id']}.{FileExtension}")
                    iconpath = f"{utils.FolderEmbyTemp}{Filename}"
                    utils.delFile(iconpath)
                    utils.writeFileBinary(iconpath, BinaryData)
                    UserData['UserImageUrl'] = iconpath

                UsersInfo.append(UserData)

            Dialog = usersconnect.UsersConnect("script-emby-connect-users.xml", *utils.CustomDialogParameters)
            Dialog.users = UsersInfo
            Dialog.doModal()
            SelectedUser = Dialog.SelectedUser
            del Dialog

            if SelectedUser and SelectedUser != "MANUAL":
                self.ServerData.update({'UserImageUrl': SelectedUser['UserImageUrl'], 'UserName': SelectedUser['Name']})


                if SelectedUser['HasPassword']:
                    xbmc.log("EMBY.emby.emby: User has password, present manual login", 0) # LOGDEBUG
                    Username = SelectedUser['Name']
                else:
                    self.ServerData["UserName"] = SelectedUser['Name']
                    return ""

        Dialog = loginmanual.LoginManual("script-emby-connect-login-manual.xml", *utils.CustomDialogParameters)
        Dialog.username = Username
        Dialog.doModal()
        SelectedUser = Dialog.SelectedUser
        del Dialog
        self.ServerData["UserName"], Password = SelectedUser
        return Password

    def EmbyConnectServers(self, Username, Password):
        Data = self.API.get_embyconnect_authenticate(Username, Password)

        if not Data:  # Failed to login
            return

        self.ServerData.update({'EmbyConnectUserId': Data['User']['Id'], 'EmbyConnectUserName': Data['User']['Name'], 'EmbyConnectAccessToken': Data['AccessToken']})
        xbmc.log("EMBY.emby.emby: Begin getConnectServers", 0) # LOGDEBUG
        EmbyConnectServers = self.API.get_embyconnect_servers()

        if EmbyConnectServers:
            for EmbyConnectServer in EmbyConnectServers:
                self.Found_Servers.append({'ExchangeToken': EmbyConnectServer['AccessKey'], 'ConnectServerId': EmbyConnectServer['Id'], 'Id': EmbyConnectServer['SystemId'], 'Name': f"Emby Connect: {EmbyConnectServer['Name']}", 'RemoteAddress': EmbyConnectServer['Url'], 'LocalAddress': EmbyConnectServer['LocalAddress'], 'UserLinkType': "Guest" if EmbyConnectServer['UserType'].lower() == "guest" else "LinkedUser"})

    def ServerLogin(self, password):
        xbmc.log("EMBY.emby.emby: Login to server", 1) # LOGINFO

        if not self.ServerData["UserName"]:
            xbmc.log("EMBY.emby.emby: Username cannot be empty", 3) # LOGERROR
            return False

        # remove old access token and credential data file
        if self.ServerData['ServerId'] in utils.EmbyServers:
            self.ServerDisconnect()

        Data = self.API.get_authbyname(self.ServerData["UserName"], password)

        if not Data:
            return False

        self.ServerData.update({'UserId': Data['User']['Id'], 'AccessToken': Data['AccessToken']})
        return True

    def ServerDetect(self):
        xbmc.log("EMBY.emby.emby: Begin getAvailableServers", 0) # LOGDEBUG
        MULTI_GROUP = ("<broadcast>", 7359)
        MESSAGE = b"who is EmbyServer?"
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        sock.settimeout(1.0)  # This controls the socket.timeout exception
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
        xbmc.log(f"EMBY.emby.emby: MultiGroup: {MULTI_GROUP}", 0) # LOGDEBUG
        xbmc.log(f"EMBY.emby.emby: Sending UDP Data: {MESSAGE}", 0) # LOGDEBUG
        found_servers = []

        # get severs via broadcast
        try:
            sock.sendto(MESSAGE, MULTI_GROUP)

            while True:
                try:
                    data, _ = sock.recvfrom(1024)  # buffer size
                    IncomingData = json.loads(data)

                    if IncomingData not in found_servers:
                        found_servers.append(IncomingData)
                except _socket.timeout:
                    xbmc.log(f"EMBY.emby.emby: Found Servers: {found_servers}", 1) # LOGINFO
                    break
                except Exception as Error:
                    xbmc.log(f"EMBY.emby.emby: Error trying to find servers: {Error}", 3) # LOGERROR
                    break
        except Exception as error:
            xbmc.log(f"EMBY.emby.emby: ERROR: {error}", 3) # LOGERROR

        self.Found_Servers = []

        for found_server in found_servers:
            server = ""

            if found_server.get('Address') and found_server.get('EndpointAddress'):
                server = found_server['EndpointAddress'].split(':')[0]
                parts = found_server['Address'].split(':')

                if len(parts) > 1:
                    port_string = parts[len(parts) - 1]
                    server += f":{port_string}"
                    server = server.strip()
                    server = server.lower()

                    if 'http' not in server:
                        server = f"http://{server}"

            if not server and not found_server.get('Address'):
                xbmc.log(f"EMBY.emby.emby: Server {found_server} has no address", 2) # LOGWARNING
                continue

            self.Found_Servers.append({'Id': found_server['Id'], 'LocalAddress': server or found_server['Address'], 'Name': found_server['Name']})

    def TestConnections(self):
        xbmc.log("EMBY.emby.emby: Begin connectToServer", 0) # LOGDEBUG
        Resync = ""
        SaveConfig = False

        for Connection in ("ManualAddress", "LocalAddress", "RemoteAddress"):
            if utils.SystemShutdown:
                return False, Resync, SaveConfig

            if not self.ServerData[Connection]:
                xbmc.log(f"EMBY.emby.emby: Skip Emby server connection test: {Connection}", 1) # LOGINFO
                continue

            self.ServerData['ServerUrl'] = self.ServerData[Connection]
            PublicInfo = self.API.get_publicinfo()

            if PublicInfo:
                ServerVersion = PublicInfo.get('Version', "")
                ServerVersionPrevious = self.ServerData.get('ServerVersion', "")

                if ServerVersion:
                    if ServerVersionPrevious:
                        if ServerVersionPrevious != ServerVersion:
                            ServerVersionCompare = get_CompareVersion(ServerVersion)
                            EmbyServerVersionPreviousCompare = get_CompareVersion(ServerVersionPrevious)
                            EmbyServerVersionResyncCompare = get_CompareVersion(utils.EmbyServerVersionResync)

                            if (EmbyServerVersionPreviousCompare < EmbyServerVersionResyncCompare >= ServerVersionCompare) or (ServerVersionCompare < EmbyServerVersionPreviousCompare >= EmbyServerVersionResyncCompare):
                                Resync = ServerVersion

                            self.ServerData["ServerVersion"] = ServerVersion
                            SaveConfig = True
                    else:
                        self.ServerData["ServerVersion"] = ServerVersion
                        SaveConfig = True

                xbmc.log(f"EMBY.emby.emby: Server version: {ServerVersion}", 1) # LOGINFO
                self.ServerData.update({'RemoteAddress': PublicInfo.get('WanAddress', self.ServerData['RemoteAddress']), 'LocalAddress': PublicInfo.get('LocalAddress', self.ServerData['LocalAddress']), 'ServerName': PublicInfo.get('ServerName'), 'ServerId': PublicInfo.get('Id')})
                utils.DatabaseFiles[self.ServerData['ServerId']] = utils.translatePath(f"special://profile/Database/emby_{self.ServerData['ServerId']}.db")
                return True, Resync, SaveConfig

            self.ServerData['ServerUrl'] = ""
            continue

        xbmc.log("EMBY.emby.emby: Tested all connection modes. Failing server connection", 1) # LOGINFO
        return False, Resync, SaveConfig

def get_CompareVersion(Version):
    CompareVersion = ""
    SubVersions = Version.split(".")

    for SubVersion in SubVersions:
        SubVersionInt = int(SubVersion)
        CompareVersion += f"{SubVersionInt:03d}"

    return int(CompareVersion)
