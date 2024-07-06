from _thread import start_new_thread, allocate_lock
import base64
import os
import array
import struct
import hashlib
import json
import zlib
import ssl
import uuid
import _socket
import xbmc
import xbmcgui
from helper import utils, queue, artworkcache
from database import dbio
from core import common
from hooks import websocket


class HTTP:
    def __init__(self, EmbyServer):
        self.EmbyServer = EmbyServer
        self.Intros = []
        self.Queues = {"ASYNC": queue.Queue(), "DOWNLOAD": queue.Queue()}
        self.Connection = {}
        self.SocketBusy = {"MAIN": allocate_lock()}
        self.Connecting = allocate_lock()
        self.Running = False
        self.inProgressWebSocket = False
        self.SSLContext = ssl.SSLContext(ssl.PROTOCOL_TLS)
        self.SSLContext.load_default_certs()
        self.Websocket = websocket.WebSocket(EmbyServer)
        self.WebsocketBuffer = b""
        self.AddrInfo = {}

        if utils.sslverify:
            self.SSLContext.verify_mode = ssl.CERT_REQUIRED
        else:
            self.SSLContext.verify_mode = ssl.CERT_NONE

    def start(self):
        with self.Connecting:
            if not self.Running:
                self.Running = True
                xbmc.log("EMBY.emby.http: --->[ HTTP ]", 1) # LOGINFO
                self.Queues["ASYNC"].clear()
                self.Queues["DOWNLOAD"].clear()
                start_new_thread(self.Ping, ())
                start_new_thread(self.async_commands, ())
                start_new_thread(self.download_file, ())

                if utils.websocketenabled:
                    start_new_thread(self.Websocket.Message, ())
                    start_new_thread(self.websocket_listen, ())

    def stop(self):
        with self.Connecting:
            if self.Running:
                self.Running = False
                xbmc.log("EMBY.emby.http: ---<[ HTTP ]", 1) # LOGINFO
                self.Queues["ASYNC"].put("QUIT")
                self.Queues["DOWNLOAD"].put("QUIT")

                if utils.websocketenabled:
                    self.Websocket.MessageQueue.put("QUIT")

                for ConnectionId in list(self.Connection.keys()):
                    self.socket_close(ConnectionId)

    def socket_addrinfo(self, ConnectionId, Hostname, Force):
        if Hostname in self.AddrInfo and not Force:
            return 0

        try:
            AddrInfo = _socket.getaddrinfo(Hostname, None)
            xbmc.log(f"EMBY.emby.http: AddrInfo: {AddrInfo}", 0) # LOGDEBUG
            self.AddrInfo[Hostname] = (AddrInfo[0][4][0], AddrInfo[0][0])
        except Exception as error:
            xbmc.log(f"EMBY.emby.http: Socket open {ConnectionId}: Wrong Hostname: {error}", 2) # LOGWARNING

            if ConnectionId == "MAIN":
                utils.Dialog.notification(heading=utils.addon_name, icon="DefaultIconError.png", message=utils.Translate(33678), time=utils.displayMessage, sound=False)

            if ConnectionId in self.Connection:
                del self.Connection[ConnectionId]

            return 609

        return 0

    def socket_open(self, ConnectionString, ConnectionId):
        NewHeader = False

        if ConnectionId not in self.Connection:
            self.Connection[ConnectionId] = {}

        if "ConnectionString" not in self.Connection[ConnectionId]:
            self.Connection[ConnectionId]["ConnectionString"] = ConnectionString
            NewHeader = True
        else:
            if self.Connection[ConnectionId]["ConnectionString"] != ConnectionString:
                self.Connection[ConnectionId]["ConnectionString"] = ConnectionString
                NewHeader = True

        if NewHeader:
            try:
                Scheme, self.Connection[ConnectionId]["Hostname"], self.Connection[ConnectionId]["Port"], self.Connection[ConnectionId]["SubUrl"] = utils.get_url_info(ConnectionString)
            except Exception as error:
                xbmc.log(f"EMBY.emby.http: Socket open {ConnectionId}: Wrong ConnectionString: {ConnectionString} / {error}", 2) # LOGWARNING

                if ConnectionId == "MAIN":
                    utils.Dialog.notification(heading=utils.addon_name, icon="DefaultIconError.png", message=utils.Translate(33678), time=utils.displayMessage, sound=False)

                if ConnectionId in self.Connection:
                    del self.Connection[ConnectionId]

                return 611

            self.Connection[ConnectionId]["SSL"] = bool(Scheme == "https")
            self.Connection[ConnectionId]["RequestHeader"] = {"Host": f"{self.Connection[ConnectionId]['Hostname']}:{self.Connection[ConnectionId]['Port']}", 'Content-type': 'application/json; charset=utf-8', 'Accept-Charset': 'utf-8', 'Accept-encoding': 'gzip', 'User-Agent': f"{utils.addon_name}/{utils.addon_version}", 'Connection': 'keep-alive', 'Authorization': f'Emby Client="{utils.addon_name}", Device="{utils.device_name}", DeviceId="{self.EmbyServer.ServerData["DeviceId"]}", Version="{utils.addon_version}"'}

            if ConnectionId == "DOWNLOAD":
                self.Connection[ConnectionId]["RequestHeader"]['Accept-encoding'] = "identity"

            StatusCodeSocket = self.socket_addrinfo(ConnectionId, self.Connection[ConnectionId]["Hostname"], False)

            if StatusCodeSocket:
                return StatusCodeSocket

        RetryCounter = 0

        while True:
            try:
                self.Connection[ConnectionId]["Socket"] = _socket.socket(self.AddrInfo[self.Connection[ConnectionId]["Hostname"]][1], _socket.SOCK_STREAM)
                self.Connection[ConnectionId]["Socket"].setsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)
                self.Connection[ConnectionId]["Socket"].settimeout(1) # set timeout
                self.Connection[ConnectionId]["Socket"].connect((self.AddrInfo[self.Connection[ConnectionId]["Hostname"]][0], self.Connection[ConnectionId]['Port']))
                break
            except TimeoutError:
                if ConnectionId not in self.Connection:
                    xbmc.log(f"EMBY.emby.http: TimeoutError: No {ConnectionId}", 2) # LOGWARNING
                    return 699

                RetryCounter += 1

                if RetryCounter == 1:
                    StatusCodeSocket = self.socket_addrinfo(ConnectionId, self.Connection[ConnectionId]["Hostname"], True)

                    if StatusCodeSocket:
                        return StatusCodeSocket

                if RetryCounter <= 10:
                    continue

                xbmc.log(f"EMBY.emby.http: Socket open {ConnectionId}: Timeout", 2) # LOGWARNING

                if ConnectionId in self.Connection:
                    del self.Connection[ConnectionId]

                return 606
            except ConnectionRefusedError:
                if ConnectionId not in self.Connection:
                    xbmc.log(f"EMBY.emby.http: ConnectionRefusedError: No {ConnectionId}", 2) # LOGWARNING
                    return 699

                RetryCounter += 1

                if RetryCounter == 1:
                    StatusCodeSocket = self.socket_addrinfo(ConnectionId, self.Connection[ConnectionId]["Hostname"], True)

                    if StatusCodeSocket:
                        return StatusCodeSocket

                if RetryCounter == 1:
                    continue

                if ConnectionId in self.Connection:
                    del self.Connection[ConnectionId]

                xbmc.log(f"EMBY.emby.http: [ ServerUnreachable ] {ConnectionId}", 2) # LOGWARNING
                xbmc.log(f"EMBY.emby.http: [ ServerUnreachable ] {ConnectionString}", 0) # LOGDEBUG
                return 607
            except Exception as error:
                if ConnectionId not in self.Connection:
                    xbmc.log(f"EMBY.emby.http: No ConnectionId {ConnectionId}", 2) # LOGWARNING
                    return 699

                RetryCounter += 1

                if RetryCounter == 1:
                    StatusCodeSocket = self.socket_addrinfo(ConnectionId, self.Connection[ConnectionId]["Hostname"], True)

                    if StatusCodeSocket:
                        return StatusCodeSocket

                if str(error) == "timed out": # workaround when TimeoutError not raised
                    if RetryCounter <= 10:
                        continue

                    xbmc.log(f"EMBY.emby.http: Socket open {ConnectionId}: Timeout", 2) # LOGWARNING

                    if ConnectionId in self.Connection:
                        del self.Connection[ConnectionId]

                    return 606

                if RetryCounter == 1:
                    continue

                if str(error).lower().find("errno 22") != -1 or str(error).lower().find("invalid argument") != -1: # [Errno 22] Invalid argument
                    if ConnectionId in self.Connection:
                        del self.Connection[ConnectionId]

                    xbmc.log(f"EMBY.emby.http: Socket open {ConnectionId}: Invalid argument", 2) # LOGWARNING

                    if ConnectionId == "MAIN":
                        utils.Dialog.notification(heading=utils.addon_name, icon="DefaultIconError.png", message=utils.Translate(33679), time=utils.displayMessage, sound=False)

                    return 610

                xbmc.log(f"EMBY.emby.http: Socket open {ConnectionId}: Undefined error: {error}", 2) # LOGWARNING
                xbmc.log(f"EMBY.emby.http: Socket open {ConnectionId}: Undefined error type {type(error)}", 2) # LOGWARNING

                if ConnectionId in self.Connection:
                    del self.Connection[ConnectionId]

                return 699

        if ConnectionId in self.Connection:
            if self.Connection[ConnectionId]["SSL"]:
                try:
                    self.Connection[ConnectionId]["Socket"] = self.SSLContext.wrap_socket(self.Connection[ConnectionId]["Socket"], do_handshake_on_connect=True, suppress_ragged_eofs=True, server_hostname=self.Connection[ConnectionId]["Hostname"])
                except ssl.CertificateError:
                    if ConnectionId in self.Connection:
                        del self.Connection[ConnectionId]

                    xbmc.log("EMBY.emby.http: socket_open ssl certificate error", 3) # LOGERROR

                    if ConnectionId == "MAIN":
                        utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33428), time=utils.displayMessage)

                    return 608
                except Exception as error:
                    if ConnectionId in self.Connection:
                        del self.Connection[ConnectionId]

                    xbmc.log(f"EMBY.emby.http: socket_open ssl undefined error: {error}", 2) # LOGWARNING
                    return 699
        else:
            xbmc.log(f"EMBY.emby.http: socket_open ssl: No ConnectionId {ConnectionId}", 2) # LOGWARNING
            return 699

        xbmc.log(f"EMBY.emby.http: Socket {ConnectionId} opened", 0) # LOGDEBUG
        return 0

    def socket_close(self, ConnectionId):
        if ConnectionId in self.Connection:
            try:
                self.Connection[ConnectionId]["Socket"].close()
            except Exception as error:
                xbmc.log(f"EMBY.emby.http: Socket {ConnectionId} close error: {error}", 2) # LOGWARNING

            try:
                del self.Connection[ConnectionId]
            except Exception as error:
                xbmc.log(f"EMBY.emby.http: Socket {ConnectionId} reset error: {error}", 2) # LOGWARNING

            if ConnectionId != "MAIN" and ConnectionId in self.SocketBusy:
                del self.SocketBusy[ConnectionId]
        else:
            xbmc.log(f"EMBY.emby.http: Socket {ConnectionId} already closed", 0) # LOGDEBUG
            return

        xbmc.log(f"EMBY.emby.http: Socket {ConnectionId} closed", 0) # LOGDEBUG

    def socket_io(self, Request, ConnectionId, Timeout):
        IncomingData = b""
        StatusCode = 0
        TimeoutCounter = 0
        BytesSend = 0
        BytesSendTotal = len(Request)

        while True:
            try:
                self.Connection[ConnectionId]["Socket"].settimeout(1) # set timeout

                if Request:
                    while BytesSend < BytesSendTotal:
                        BytesSend += self.Connection[ConnectionId]["Socket"].send(Request[BytesSend:])
                else:
                    IncomingData = self.Connection[ConnectionId]["Socket"].recv(1048576)

                    if not IncomingData: # No Data received -> Socket closed by Emby server
                        xbmc.log(f"EMBY.emby.http: Socket IO {ConnectionId}: ({bool(Request)}): Empty data", 0) # LOGDEBUG
                        StatusCode = 600

                break
            except TimeoutError:
                if not Timeout or (ConnectionId != "MAIN" and self.SocketBusy["MAIN"].locked()): # Websocket or binary -> wait longer for e.g. images. MAIN queries could block IO
                    continue

                TimeoutCounter += 1

                if TimeoutCounter < Timeout:
                    continue

                xbmc.log(f"EMBY.emby.http: Socket IO {ConnectionId}: ({bool(Request)}): Timeout", 2) # LOGWARNING
                StatusCode = 603
                break
            except BrokenPipeError:
                xbmc.log(f"EMBY.emby.http: Socket IO {ConnectionId}: ({bool(Request)}): Pipe error", 2) # LOGWARNING
                StatusCode = 605
                break
            except Exception as error:
                if str(error) == "timed out": # workaround when TimeoutError not raised
                    if not Timeout or (ConnectionId != "MAIN" and self.SocketBusy["MAIN"].locked()): # Websocket or binary -> wait longer for e.g. images. MAIN queries could block IO
                        continue

                    TimeoutCounter += 1

                    if TimeoutCounter < Timeout:
                        continue

                    xbmc.log(f"EMBY.emby.http: Socket IO {ConnectionId}: ({bool(Request)}): Timeout (workaround)", 2) # LOGWARNING
                    StatusCode = 603
                    break

                xbmc.log(f"EMBY.emby.http: Socket IO {ConnectionId}: ({bool(Request)}): Undefined error {error}", 3) # LOGERROR
                xbmc.log(f"EMBY.emby.http: Socket IO {ConnectionId}: ({bool(Request)}): Undefined error type {type(error)}", 3) # LOGERROR
                StatusCode = 699
                break

        return StatusCode, IncomingData

    def socket_request(self, Method, Handler, Params, Binary, TimeoutSend, TimeoutRecv, ConnectionId, DownloadPath, DownloadName):
        if ConnectionId not in self.Connection:
            return 601, {}, {}

        PayloadTotal = b""
        PayloadTotalPosition = 0

        # Prepare HTTP Header
        HeaderString = ""

        for Key, Values in list(self.Connection[ConnectionId]['RequestHeader'].items()):
            HeaderString += f"{Key}: {Values}\r\n"

        # Prepare HTTP Payload
        if Method == "GET":
            ParamsString = ""

            for Query, Param in list(Params.items()):
                if Param not in ([], None):
                    ParamsString += f"{Query}={Param}&"

            if ParamsString:
                ParamsString = f"?{ParamsString[:-1]}"

            StatusCodeSocket, _ = self.socket_io(f"{Method} {self.Connection[ConnectionId]['SubUrl']}{Handler}{ParamsString} HTTP/1.1\r\n{HeaderString}Content-Length: 0\r\n\r\n".encode("utf-8"), ConnectionId, TimeoutSend)
        else:
            if Params:
                ParamsString = json.dumps(Params)
            else:
                ParamsString = ""

            StatusCodeSocket, _ = self.socket_io(f"{Method} {self.Connection[ConnectionId]['SubUrl']}{Handler} HTTP/1.1\r\n{HeaderString}Content-Length: {len(ParamsString)}\r\n\r\n{ParamsString}".encode("utf-8"), ConnectionId, TimeoutSend)

        if StatusCodeSocket:
            return StatusCodeSocket, {}, ""

        IncomingData = b""

        while True:
            StatusCodeSocket, RecvData = self.socket_io("", ConnectionId, TimeoutRecv)
            IncomingData += RecvData

            if StatusCodeSocket:
                return StatusCodeSocket, {}, ""

            if b'\x0d\x0a\x0d\x0a' not in IncomingData:
                xbmc.log("EMBY.emby.emby: Incomplete header", 0) # LOGDEBUG
                continue

            IncomingData = IncomingData.split(b'\x0d\x0a\x0d\x0a', 1) # Split header/payload
            IncomingMetaData = IncomingData[0].decode("utf-8").split("\r\n")
            StatusCode = int(IncomingMetaData[0].split(" ")[1])

            if StatusCode not in (200, 206, 301, 302, 307, 308, 101) or StatusCode == 204: # 200 = OK, 206 = Partial content, 204 = OK but no content, 3XX redirects, 101 wesocket
                return StatusCode, {}, ""

            IncomingDataHeaderArray = IncomingMetaData[1:]
            IncomingDataHeader = {}

            for IncomingDataHeaderArrayData in IncomingDataHeaderArray:
                Temp = IncomingDataHeaderArrayData.split(": ")
                IncomingDataHeader[Temp[0].lower()] = Temp[1]

            # Redirects 3XX, websocket 1XX or HEAD requests
            if StatusCode in (301, 302, 307, 308, 101) or Method == "HEAD":
                return StatusCode, IncomingDataHeader, ""

            try:
                # Decompress flags
                isGzip = IncomingDataHeader.get("content-encoding", "") == "gzip"
                isDeflate = IncomingDataHeader.get("content-encoding", "") == "deflate"

                # Recv frame
                PayloadLenghtTotal = int(IncomingDataHeader["content-length"])
            except Exception as error: # Can happen on Emby server hard reboot
                xbmc.log(f"EMBY.emby.http: Header error {ConnectionId}: Undefined error {error}", 3) # LOGERROR
                return 612, {}, ""

            # Recv frame
            PayloadTotalPosition += PayloadLenghtTotal
            Payload = IncomingData[1]
            del IncomingData
            PayloadLenght = len(Payload)

            if DownloadPath:
                ProgressBar = xbmcgui.DialogProgressBG()
                ProgressBar.create("Download", DownloadName)
                ProgressBarTotal = PayloadLenghtTotal / 100
                OutFile = open(DownloadPath, 'wb')

            while PayloadLenght < PayloadLenghtTotal:
                self.wait_for_main(ConnectionId)
                StatusCodeSocket, PayloadRecv = self.socket_io("", ConnectionId, TimeoutRecv)

                if StatusCodeSocket:
                    if DownloadPath:
                        OutFile.close()
                        ProgressBar.close()
                        del ProgressBar

                    return StatusCodeSocket, {}, ""

                Payload += PayloadRecv
                PayloadLenght += len(PayloadRecv)
                del PayloadRecv

                if DownloadPath:
                    OutFile.write(Payload)
                    Payload = b""
                    ProgressBar.update(int(PayloadLenght / ProgressBarTotal), "Download", DownloadName)

            if DownloadPath:
                OutFile.close()
                ProgressBar.close()
                del ProgressBar

            PayloadTotal += Payload
            del Payload

            # request additional data
            if StatusCode == 206: # partial content
                xbmc.log(f"EMBY.emby.http: Partial content {ConnectionId} closed", 1) # LOGINFO

                if Method == "GET":
                    StatusCodeSocket, _ = self.socket_io(f"{Method} /{Handler}{ParamsString} HTTP/1.1\r\n{HeaderString}Range: bytes={PayloadTotalPosition}-\r\nContent-Length: 0\r\n\r\n".encode("utf-8"), ConnectionId, TimeoutSend)
                else:
                    StatusCodeSocket, _ = self.socket_io(f"{Method} /{Handler} HTTP/1.1\r\n{HeaderString}Content-Length: {len(ParamsString)}\r\n\r\n{ParamsString}".encode("utf-8"), ConnectionId, TimeoutSend)

                if StatusCodeSocket:
                    return 601, {}, ""
            else:
                break

        # Decompress data
        if isDeflate:
            PayloadTotal = zlib.decompress(PayloadTotal, -zlib.MAX_WBITS)
        elif isGzip:
            PayloadTotal = zlib.decompress(PayloadTotal, zlib.MAX_WBITS|32)

        if Binary:
            if DownloadPath and PayloadTotal:
                with open(DownloadPath, 'wb') as OutFile:
                    OutFile.write(PayloadTotal)

                PayloadTotal = b""

            return StatusCode, IncomingDataHeader, PayloadTotal

        try:
            return StatusCode, IncomingDataHeader, json.loads(PayloadTotal)
        except:
            xbmc.log(f"EMBY.emby.emby: Invalid content {ConnectionId}: {IncomingDataHeader}", 0) # LOGDEBUG
            return 601, {}, ""

    def download_file(self):
        xbmc.log("EMBY.emby.http: THREAD: --->[ file download ]", 0) # LOGDEBUG

        while True:
            Command = self.Queues["DOWNLOAD"].get() # EmbyId, ParentPath, Path, FilePath, FileSize, Name, KodiType, KodiPathIdBeforeDownload, KodiFileId, KodiId

            if Command == "QUIT":
                xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Download {self.EmbyServer.ServerData['ServerId']} ] shutdown 1", 0) # LOGDEBUG
                self.Queues["DOWNLOAD"].clear()
                utils.delFile(Command[3])
                self.socket_close("DOWNLOAD")
                return

            # check if free space below 2GB
            if utils.getFreeSpace(Command[2]) < (2097152 + Command[4] / 1024):
                utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33429), icon=utils.icon, time=utils.displayMessage, sound=True)
                xbmc.log("EMBY.emby.http: THREAD: ---<[ file download ] terminated by filesize", 2) # LOGWARNING
                return

            while True:
                if self.socket_open(self.EmbyServer.ServerData['ServerUrl'], "DOWNLOAD"):
                    if utils.sleep(10):
                        xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Download {self.EmbyServer.ServerData['ServerId']} shutdown ]", 0) # LOGDEBUG
                        return

                    continue

                self.update_header("DOWNLOAD")
                StatusCode, _, _ = self.socket_request("GET", f"Items/{Command[0]}/Download", {}, True, 10, 300, "DOWNLOAD", Command[3], Command[5])

                if StatusCode == 601: # quit
                    xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Download {self.EmbyServer.ServerData['ServerId']} ] shutdown 2", 0) # LOGDEBUG
                    self.Queues["DOWNLOAD"].clear()
                    utils.delFile(Command[3])
                    self.socket_close("DOWNLOAD")
                    return

                if StatusCode in (600, 602, 603, 604, 605, 612):
                    xbmc.log(f"EMBY.emby.http: Download retry {StatusCode}", 2) # LOGWARNING
                    utils.delFile(Command[3])
                    self.socket_close("DOWNLOAD")
                    continue

                try:
                    if StatusCode != 200:
                        utils.delFile(Command[3])
                    else:
                        if Command[9]: # KodiId
                            SQLs = dbio.DBOpenRW(self.EmbyServer.ServerData['ServerId'], "download_item", {})
                            SQLs['emby'].add_DownloadItem(Command[0], Command[7], Command[8], Command[9], Command[6])
                            dbio.DBCloseRW(self.EmbyServer.ServerData['ServerId'], "download_item", {})
                            SQLs = dbio.DBOpenRW("video", "download_item_replace", {})
                            Artworks = ()
                            ArtworksData = SQLs['video'].get_artworks(Command[9], Command[6])

                            for ArtworkData in ArtworksData:
                                if ArtworkData[3] in ("poster", "thumb", "landscape"):
                                    UrlMod = ArtworkData[4].split("|")
                                    UrlMod = f"{UrlMod[0].replace('-download', '')}-download|redirect-limit=1000"
                                    SQLs['video'].update_artwork(ArtworkData[0], UrlMod)
                                    Artworks += ((UrlMod,),)

                            SQLs['video'].update_Name(Command[9], Command[6], True)
                            SQLs['video'].replace_Path_ContentItem(Command[9], Command[6], Command[2])

                            if Command[6] == "episode":
                                KodiPathId = SQLs['video'].get_add_path(Command[2], None, Command[1])
                                Artworks = SQLs['video'].set_Subcontent_download_tags(Command[9], True)

                                if Artworks:
                                    artworkcache.CacheAllEntries(Artworks, None)
                            elif Command[6] == "movie":
                                KodiPathId = SQLs['video'].get_add_path(Command[2], "movie", None)
                            elif Command[6] == "musicvideo":
                                KodiPathId = SQLs['video'].get_add_path(Command[2], "musicvideos", None)
                            else:
                                KodiPathId = None
                                xbmc.log(f"EMBY.emby.http: Download invalid: KodiPathId: {Command[1]['Path']} / {Command[6]}", 2) # LOGWARNING

                            if KodiPathId:
                                SQLs['video'].replace_PathId(Command[8], KodiPathId)

                            dbio.DBCloseRW("video", "download_item_replace", {})
                            artworkcache.CacheAllEntries(Artworks, None)

                    if self.Queues["DOWNLOAD"].isEmpty():
                        utils.refresh_widgets(True)
                except Exception as error:
                    xbmc.log(f"EMBY.emby.http: Download Emby server did not respond: error: {error}", 2) # LOGWARNING

                break

        xbmc.log("EMBY.emby.http: THREAD: ---<[ file download ]", 0) # LOGDEBUG

    def request(self, Method, Handler, Params, RequestHeader, Binary, ConnectionString, CloseConnection):
        xbmc.log(f"EMBY.emby.http: [ http ] Method: {Method} / Handler: {Handler} / Params: {Params} / Binary: {Binary} / ConnectionString: {ConnectionString} / CloseConnection: {CloseConnection} / RequestHeader: {RequestHeader}", 0) # LOGDEBUG

        if CloseConnection:
            ConnectionId = str(uuid.uuid4())
        else:
            ConnectionId = "MAIN"

        if ConnectionId not in self.SocketBusy:
            self.SocketBusy[ConnectionId] = allocate_lock()

        with self.SocketBusy[ConnectionId]:
            if not ConnectionString:
                ConnectionString = self.EmbyServer.ServerData['ServerUrl']

            # Connectionstring changed
            if not CloseConnection and ConnectionId in self.Connection and ConnectionString.find(self.Connection[ConnectionId]['Hostname']) == -1:
                self.socket_close(ConnectionId)

            while True:
                StatusCode = 0

                # Shutdown
                if utils.SystemShutdown:
                    self.socket_close(ConnectionId)
                    return noData(StatusCode, {}, Binary)

                # open socket
                if ConnectionId not in self.Connection:
                    StatusCode = self.socket_open(ConnectionString, ConnectionId)

                    if StatusCode:
                        if StatusCode not in (608, 609, 610, 611): # wrong Emby server address or SSL issue
                            self.EmbyServer.ServerReconnect(True)

                        return noData(StatusCode, {}, Binary)

                # Update Header information
                if RequestHeader:
                    self.Connection[ConnectionId]["RequestHeader"] = {"Host": f"{self.Connection[ConnectionId]['Hostname']}:{self.Connection[ConnectionId]['Port']}", 'Accept': "application/json", 'Accept-Charset': "utf-8", 'X-Application': f"{utils.addon_name}/{utils.addon_version}", 'Content-type': 'application/json'}
                    self.Connection[ConnectionId]["RequestHeader"].update(RequestHeader)
                else:
                    self.update_header(ConnectionId)

                StatusCode, Header, Payload = self.socket_request(Method, Handler, Params, Binary, 10, 300, ConnectionId, "", "")

                # Redirects
                if StatusCode in (301, 302, 307, 308):
                    self.socket_close(ConnectionId)
                    Location = Header.get("location", "")
                    Scheme, Hostname, Port, _ = utils.get_url_info(Location)
                    ConnectionString = f"{Scheme}://{Hostname}:{Port}"
                    ConnectionStringNoPort = f"{Scheme}://{Hostname}"
                    Handler = Location.replace(ConnectionString, "").replace(ConnectionStringNoPort, "")

                    if Handler.startswith("/"):
                        Handler = Handler[1:]

                    if ConnectionId == "MAIN" and StatusCode in (301, 308):
                        self.EmbyServer.ServerData['ServerUrl'] = ConnectionString

                    continue

                if CloseConnection:
                    self.socket_close(ConnectionId)

                if StatusCode == 200: # OK
                    return StatusCode, Header, Payload

                if StatusCode == 204: # OK, no data
                    return noData(StatusCode, Header, Binary)

                if StatusCode == 401: # Unauthorized
                    xbmc.log(f"EMBY.emby.http: Request unauthorized {StatusCode} / {ConnectionId}", 3) # LOGERROR
                    utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33147), time=utils.displayMessage)
                    return noData(StatusCode, Header, Binary)

                if StatusCode in (600, 604, 605, 612): # not data received, broken pipes, header issue
                    xbmc.log(f"EMBY.emby.http: Request retry {StatusCode} / {ConnectionId}", 2) # LOGWARNING
                    self.socket_close(ConnectionId)
                    continue

                if StatusCode in (602, 603): # timeouts
                    xbmc.log(f"EMBY.emby.http: Request timeout {StatusCode} / {ConnectionId}", 2) # LOGWARNING
                    self.socket_close(ConnectionId)
                    return noData(StatusCode, Header, Binary)

                if StatusCode == 601: # quit
                    return noData(StatusCode, Header, Binary)

                xbmc.log(f"EMBY.emby.http: [ Statuscode ] {StatusCode}", 3) # LOGERROR
                xbmc.log(f"EMBY.emby.http: [ Statuscode ] {Payload}", 0) # LOGDEBUG
                return noData(StatusCode, Header, Binary)

    def websocket_listen(self):
        xbmc.log(f"EMBY.emby.emby: THREAD: --->[ Websocket {self.EmbyServer.ServerData['ServerId']} ]", 0) # LOGDEBUG

        while self.Running:
            xbmc.log("EMBY.emby.emby: Websocket connecting", 1) # LOGINFO
            self.inProgressWebSocket = False

            if self.socket_open(self.EmbyServer.ServerData['ServerUrl'], "WEBSOCKET"):
                if utils.sleep(10):
                    xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Download {self.EmbyServer.ServerData['ServerId']} shutdown ]", 0) # LOGDEBUG
                    return

                continue

            uid = uuid.uuid4()
            EncodingKey = base64.b64encode(uid.bytes).strip().decode('utf-8')
            self.Connection["WEBSOCKET"]["RequestHeader"].update({"Upgrade": "websocket", "Connection": "Upgrade", "Sec-WebSocket-Key": EncodingKey, "Sec-WebSocket-Version": "13"})
            StatusCode, Header, _ = self.socket_request("GET", f"embywebsocket?api_key={self.EmbyServer.ServerData['AccessToken']}&deviceId={self.EmbyServer.ServerData['DeviceId']}", {}, True, 10, 30, "WEBSOCKET", "", "")

            if StatusCode == 601: # quit
                xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Websocket {self.EmbyServer.ServerData['ServerId']} quit ]", 0) # LOGDEBUG
                return

            if StatusCode != 101:
                self.inProgressWebSocket = False
                self.socket_close("WEBSOCKET")

                if utils.sleep(1):
                    xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Websocket {self.EmbyServer.ServerData['ServerId']} shutdown ]", 0) # LOGDEBUG
                    return

            result = Header.get("sec-websocket-accept", "")

            if not result:
                utils.Dialog.notification(heading=utils.addon_name, icon="DefaultIconError.png", message=utils.Translate(33235), sound=True, time=utils.newContentTime)
                return

            value = f"{EncodingKey}258EAFA5-E914-47DA-95CA-C5AB0DC85B11".encode("utf-8")
            hashed = base64.b64encode(hashlib.sha1(value).digest()).strip().lower().decode('utf-8')

            if hashed != result.lower():
                return

            self.inProgressWebSocket = True
            self.websocket_send('{"MessageType": "ScheduledTasksInfoStart", "Data": "0,1500"}', 0x1) # subscribe notifications

            if "WEBSOCKET" not in self.Connection:
                continue

            self.Connection["WEBSOCKET"]["Socket"].settimeout(1)
            self.WebsocketBuffer = b""

            while self.Running:
                ConnectionClosed = False
                StatusCodeSocket, PayloadRecv = self.socket_io("", "WEBSOCKET", 0)

                if StatusCodeSocket:
                    xbmc.log(f"EMBY.emby.emby: Websocket receive interupted {StatusCodeSocket}", 1) # LOGINFO
                    break

                self.WebsocketBuffer += PayloadRecv

                while True:
                    if len(self.WebsocketBuffer) < 2:
                        break

                    FrameHeader = self.WebsocketBuffer[:2]
                    Curser = 2
                    fin = FrameHeader[0] >> 7 & 1

                    if not fin:
                        xbmc.log("EMBY.emby.emby: Websocket not fin", 0) # LOGDEBUG
                        break

                    opcode = FrameHeader[0] & 0xf
                    has_mask = FrameHeader[1] >> 7 & 1

                    # Frame length
                    FrameLength = FrameHeader[1] & 0x7f

                    if FrameLength == 0x7e:
                        length_data = self.WebsocketBuffer[Curser:Curser + 2]
                        Curser += 2
                        FrameLength = struct.unpack("!H", length_data)[0]
                    elif FrameLength == 0x7f:
                        length_data = self.WebsocketBuffer[Curser:Curser + 8]
                        Curser += 8
                        FrameLength = struct.unpack("!Q", length_data)[0]

                    # Mask
                    if has_mask:
                        FrameMask = self.WebsocketBuffer[Curser:Curser + 4]
                        Curser += 4

                    # Payload
                    if FrameLength:
                        FrameLengthEndPos = Curser + FrameLength

                        if len(self.WebsocketBuffer) < FrameLengthEndPos: # Incomplete Frame
                            xbmc.log("EMBY.emby.emby: Websocket incomplete frame", 0) # LOGDEBUG
                            break

                        payload = self.WebsocketBuffer[Curser:FrameLengthEndPos]
                        Curser = FrameLengthEndPos

                    if has_mask:
                        payload = maskData(FrameMask, payload)

                    if opcode in (0x2, 0x1, 0x0): # 1 textframe, 2 binaryframe, 0 continueframe
                        if fin:
                            self.Websocket.MessageQueue.put(payload)
                    elif opcode == 0x8: # Connection close
                        xbmc.log("EMBY.emby.emby: Websocket connection closed", 0) # LOGDEBUG
                        ConnectionClosed = True
                    elif opcode == 0x9: # Ping
                        self.websocket_send(payload, 0xa)  # Pong
                    elif opcode == 0xa: # Pong
                        xbmc.log("EMBY.emby.emby: Websocket Pong received", 0) # LOGDEBUG
                    else:
                        xbmc.log(f"EMBY.hooks.websocket: Uncovered Opcode: {opcode} / Payload: {payload} / FrameHeader: {FrameHeader} / FrameLength: {FrameLength} / FrameMask: {FrameMask}", 3) # LOGERROR

                    self.WebsocketBuffer = self.WebsocketBuffer[Curser:]
                    continue

            if ConnectionClosed:
                break

        self.inProgressWebSocket = False
        xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Websocket {self.EmbyServer.ServerData['ServerId']} ]", 0) # LOGDEBUG

    def websocket_send(self, payload, opcode):
        if opcode == 0x1:
            payload = payload.encode("utf-8")

        length = len(payload)
        frame_header = struct.pack("B", (1 << 7 | 0 << 6 | 0 << 5 | 0 << 4 | opcode))

        if length < 0x7d:
            frame_header += struct.pack("B", (1 << 7 | length))
        elif length < 1 << 16:  # LENGTH_16
            frame_header += struct.pack("B", (1 << 7 | 0x7e))
            frame_header += struct.pack("!H", length)
        else:
            frame_header += struct.pack("B", (1 << 7 | 0x7f))
            frame_header += struct.pack("!Q", length)

        mask_key = os.urandom(4)
        data = frame_header + mask_key + maskData(mask_key, payload)
        self.socket_io(data, "WEBSOCKET", 300)

    # Delay low priority tasks
    def wait_for_main(self, ConnectionId):
        if ConnectionId == "MAIN":
            return False

        while self.SocketBusy["MAIN"].locked():
            if utils.sleep(2):
                return True

        return False

    def update_header(self, ConnectionId):
        if 'X-Emby-Token' not in self.Connection[ConnectionId]["RequestHeader"] and self.EmbyServer.ServerData['AccessToken'] and self.EmbyServer.ServerData['UserId']:
            self.Connection[ConnectionId]["RequestHeader"].update({'Authorization': f'{self.Connection[ConnectionId]["RequestHeader"]["Authorization"]}, Emby UserId="{self.EmbyServer.ServerData["UserId"]}"', 'X-Emby-Token': self.EmbyServer.ServerData['AccessToken']})

    # No return values are expected, usually also lower priority
    def async_commands(self):
        xbmc.log("EMBY.emby.http: THREAD: --->[ Async ]", 0) # LOGDEBUG
        CommandsTotal = ()

        # Sort tasks: priority tasks first, quit tasks second, others last
        while True:
            CommandsSorted = ()
            CommandsPriority = ()
            CommandsRegular = ()

            # merge commands
            Commands = self.Queues["ASYNC"].getall() # (Method, URL-handler, Parameters, Priority)
            CommandsTotal += Commands

            if not self.Queues["ASYNC"].isEmpty():
                continue

            # Sort commands
            QUIT = False

            for CommandTotal in CommandsTotal:
                if len(CommandTotal) > 1:
                    if CommandTotal[3]:
                        CommandsPriority += (CommandTotal,)
                    else:
                        CommandsRegular += (CommandTotal,)
                else:
                    QUIT = True

            if QUIT:
                CommandsSorted = CommandsPriority + ("QUIT",)
            else:
                CommandsSorted = CommandsPriority + CommandsRegular

            CommandsTotal = ()

            # Process commands
            for CommandSorted in CommandsSorted: # (Method, URL-handler, Parameters, Priority)
                if CommandSorted == "QUIT":
                    xbmc.log("EMBY.emby.http: Async closed", 1) # LOGINFO
                    xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Async {self.EmbyServer.ServerData['ServerId']} ]", 0) # LOGDEBUG
                    return

                while True:
                    if not CommandSorted[3] and self.wait_for_main("ASYNC"):
                        self.socket_close("ASYNC")
                        return

                    if self.socket_open(self.EmbyServer.ServerData['ServerUrl'], "ASYNC"):
                        self.socket_close("ASYNC")

                        if utils.sleep(1):
                            xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Async {self.EmbyServer.ServerData['ServerId']} shutdown ]", 0) # LOGDEBUG
                            return

                        continue

                    self.update_header("ASYNC")
                    StatusCode, _, _ = self.socket_request(CommandSorted[0], CommandSorted[1], CommandSorted[2], False, 1, 1, "ASYNC", "", "")

                    if StatusCode == 601: # quit
                        self.Queues["ASYNC"].clear()
                        self.socket_close("ASYNC")
                        xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Async {self.EmbyServer.ServerData['ServerId']} ] shutdown 2", 0) # LOGDEBUG
                        return

                    if StatusCode in (600, 602, 603, 604, 605, 612):
                        xbmc.log(f"EMBY.emby.http: Async retry {StatusCode}", 2) # LOGWARNING
                        self.socket_close("ASYNC")
                        continue

                    break

        self.Queues["ASYNC"].clear()
        self.socket_close("ASYNC")
        xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Async {self.EmbyServer.ServerData['ServerId']} ]", 0) # LOGDEBUG

    # Ping server -> keep http session open (timer)
    def Ping(self):
        xbmc.log(f"EMBY.emby.emby: THREAD: --->[ Ping {self.EmbyServer.ServerData['ServerId']} ]", 0) # LOGDEBUG

        while True:
            for Counter in range(20): # ping every 10 seconds
                if utils.sleep(0.5) or not self.Running:
                    xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Ping {self.EmbyServer.ServerData['ServerId']} shutdown or quit ]", 0) # LOGDEBUG
                    return

                if Counter == 9 and self.inProgressWebSocket:
                    self.websocket_send(b"", 0x9)

                if Counter == 19 and not self.SocketBusy["MAIN"].locked():
                    _, _, _ = self.request("POST", "System/Ping", {}, {}, True, "", False)

        xbmc.log(f"EMBY.emby.emby: THREAD: ---<[ Ping {self.EmbyServer.ServerData['ServerId']} ]", 0) # LOGDEBUG

    # Intros and Trailers
    def verify_intros(self, Intro):
        xbmc.log("EMBY.emby.http: THREAD: --->[ verify intros ]", 0) # LOGDEBUG

        if Intro['Path'].find("http") == -1: # Local Trailer
            Intro['Path'], _ = common.get_path_type_from_item(self.EmbyServer.ServerData['ServerId'], Intro, False, True)
            self.Intros.append(Intro)
            xbmc.log("EMBY.emby.http: THREAD: ---<[ verify intros ] valid local intro", 0) # LOGDEBUG
            return True

        status_code = self.EmbyServer.API.get_stream_statuscode(Intro['Id'], Intro['MediaSources'][0]['Id'])

        if status_code == 200:
            Intro['Path'], _ = common.get_path_type_from_item(self.EmbyServer.ServerData['ServerId'], Intro, False, True)
            self.Intros.append(Intro)
            xbmc.log("EMBY.emby.http: THREAD: ---<[ verify intros ] valid http", 0) # LOGDEBUG
            return True

        xbmc.log(f"EMBY.emby.http: Invalid Trailer: {Intro['Path']} / {status_code}", 3) # LOGERROR
        xbmc.log("EMBY.emby.http: THREAD: ---<[ verify intros ] invalid", 0) # LOGDEBUG
        return False

    def load_Trailers(self, EmbyId):
        ReceivedIntros = []
        self.Intros = []

        if utils.localTrailers:
            LocalTrailers = self.EmbyServer.API.get_local_trailers(EmbyId)

            for LocalTrailer in LocalTrailers:
                ReceivedIntros.append(LocalTrailer)

        if utils.Trailers:
            Intros = self.EmbyServer.API.get_intros(EmbyId)

            if 'Items' in Intros:
                for Intro in Intros['Items']:
                    ReceivedIntros.append(Intro)

        if ReceivedIntros:
            Index = 0

            for Index, Intro in enumerate(ReceivedIntros):
                if self.verify_intros(Intro):
                    break

            for Intro in ReceivedIntros[Index + 1:]:
                start_new_thread(self.verify_intros, (Intro,))

# Return empty data
def noData(StatusCode, Header, Binary):
    if Binary:
        return StatusCode, Header, b""

    return StatusCode, Header, {}

def maskData(mask_key, data):
    _m = array.array("B", mask_key)
    _d = array.array("B", data)

    for i in range(len(_d)):
        _d[i] ^= _m[i % 4]  # i xor

    return _d.tobytes()
