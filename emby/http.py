from _thread import start_new_thread
import _socket
import urllib3
import xbmc
import xbmcgui
from helper import utils, queue, artworkcache
from database import dbio
from core import common

TimeoutPriority = urllib3.util.timeout.Timeout(connect=1, read=0.5)
TimeoutRegular = urllib3.util.timeout.Timeout(connect=15, read=300)
TimeoutAsync = urllib3.util.timeout.Timeout(connect=5, read=2)
urllib3v1 = False

if urllib3.__version__[:1] == "1":
    import json
    urllib3v1 = True

class HTTP:
    def __init__(self, EmbyServer):
        self.session = None
        self.EmbyServer = EmbyServer
        self.Intros = []
        self.HeaderCache = {}
        self.AsyncCommandQueue = queue.Queue()
        self.FileDownloadQueue = queue.Queue()
        self.Priority = False

    def download_file(self):
        xbmc.log("EMBY.emby.http: THREAD: --->[ async file download ]", 0) # LOGDEBUG

        while True:
            Command = self.FileDownloadQueue.get()

            if Command == "QUIT":
                xbmc.log("EMBY.emby.http: Download Queue closed", 1) # LOGINFO
                self.FileDownloadQueue.clear()
                break

            self.wait_for_priority_request()

            if utils.getFreeSpace(Command[1]["Path"]) < (2097152 + Command[1]["FileSize"] / 1024): # check if free space below 2GB
                utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33429), icon=utils.icon, time=utils.displayMessage, sound=True)
                xbmc.log("EMBY.emby.http: THREAD: ---<[ async file download ] terminated by filesize", 2) # LOGWARNING
                return

            ProgressBar = xbmcgui.DialogProgressBG()
            ProgressBar.create("Download", Command[1]["Name"])
            ProgressBarTotal = Command[1]["FileSize"] / 100
            ProgressBarCounter = 0
            Terminate = False

            try:
                if urllib3v1:
                    r = self.session.request("GET", Command[0]['url'], body=json.dumps(Command[1].get("params", {})).encode('utf-8'), preload_content=False)
                else:
                    r = self.session.request("GET", Command[0]['url'], json=Command[1].get("params", {}), preload_content=False)

                with open(Command[1]["FilePath"], 'wb') as outfile:
                    for chunk in r.stream(4194304): # 4 MB chunks
                        outfile.write(chunk)
                        ProgressBarCounter += 4194304

                        if ProgressBarCounter > Command[1]["FileSize"]:
                            ProgressBarCounter = Command[1]["FileSize"]

                        ProgressBar.update(int(ProgressBarCounter / ProgressBarTotal), "Download", Command[1]["Name"])

                        if utils.SystemShutdown:
                            r.close()
                            Terminate = True
                            break

                r.release_conn()

                if Terminate:
                    utils.delFile(Command[1]["FilePath"])
                else:
                    if "KodiId" in Command[1]:
                        SQLs = dbio.DBOpenRW(self.EmbyServer.ServerData['ServerId'], "download_item", {})
                        SQLs['emby'].add_DownloadItem(Command[1]["Id"], Command[1]["KodiPathIdBeforeDownload"], Command[1]["KodiFileId"], Command[1]["KodiId"], Command[1]["KodiType"])
                        dbio.DBCloseRW(self.EmbyServer.ServerData['ServerId'], "download_item", {})
                        SQLs = dbio.DBOpenRW("video", "download_item_replace", {})
                        Artworks = ()
                        ArtworksData = SQLs['video'].get_artworks(Command[1]["KodiId"], Command[1]["KodiType"])

                        for ArtworkData in ArtworksData:
                            if ArtworkData[3] in ("poster", "thumb", "landscape"):
                                UrlMod = ArtworkData[4].split("|")
                                UrlMod = f"{UrlMod[0].replace('-download', '')}-download|redirect-limit=1000"
                                SQLs['video'].update_artwork(ArtworkData[0], UrlMod)
                                Artworks += ((UrlMod,),)

                        SQLs['video'].update_Name(Command[1]["KodiId"], Command[1]["KodiType"], True)
                        SQLs['video'].replace_Path_ContentItem(Command[1]["KodiId"], Command[1]["KodiType"], Command[1]["Path"])

                        if Command[1]["KodiType"] == "episode":
                            KodiPathId = SQLs['video'].get_add_path(Command[1]["Path"], None, Command[1]["ParentPath"])
                            Artworks = SQLs['video'].set_Subcontent_download_tags(Command[1]["KodiId"], True)

                            if Artworks:
                                artworkcache.CacheAllEntries(Artworks, None)
                        elif Command[1]["KodiType"] == "movie":
                            KodiPathId = SQLs['video'].get_add_path(Command[1]["Path"], "movie", None)
                        elif Command[1]["KodiType"] == "musicvideo":
                            KodiPathId = SQLs['video'].get_add_path(Command[1]["Path"], "musicvideos", None)
                        else:
                            KodiPathId = None
                            xbmc.log(f"EMBY.emby.http: Download invalid: KodiPathId: {Command[1]['Path']} / {Command[1]['KodiType']}", 2) # LOGWARNING

                        if KodiPathId:
                            SQLs['video'].replace_PathId(Command[1]["KodiFileId"], KodiPathId)

                        dbio.DBCloseRW("video", "download_item_replace", {})
                        artworkcache.CacheAllEntries(Artworks, ProgressBar)

                ProgressBar.close()
                del ProgressBar

                if self.FileDownloadQueue.isEmpty():
                    utils.refresh_widgets(True)
            except Exception as error:
                xbmc.log(f"EMBY.emby.http: Download Emby server did not respond: error: {error}", 2) # LOGWARNING
                ProgressBar.close()
                del ProgressBar

        xbmc.log("EMBY.emby.http: THREAD: ---<[ async file download ]", 0) # LOGDEBUG

    def async_commands(self):
        xbmc.log("EMBY.emby.http: THREAD: --->[ async queue ]", 0) # LOGDEBUG
        PingTimeoutCounter = 0

        while True:
            Command = self.AsyncCommandQueue.get()

            try:
                if Command == "QUIT":
                    xbmc.log("EMBY.emby.http: Queue closed", 1) # LOGINFO
                    self.AsyncCommandQueue.clear()
                    break

                self.wait_for_priority_request()

                if Command['type'] in ("POST", "DELETE"):
                    if urllib3v1:
                        r = self.session.request(Command['type'], Command['url'], body=json.dumps(Command.get("params", {})).encode('utf-8'), timeout=TimeoutAsync)
                    else:
                        r = self.session.request(Command['type'], Command['url'], json=Command.get("params", {}), timeout=TimeoutAsync)

                    r.close()

                if Command['url'].find("System/Ping") != -1:
                    PingTimeoutCounter = 0
            except Exception as error:
                xbmc.log(f"EMBY.emby.http: Async_commands Emby server did not respond: error: {error}", 2) # LOGWARNING

                if Command['url'].find("System/Ping") != -1: # ping timeout
                    if PingTimeoutCounter == 4:
                        xbmc.log("EMBY.emby.http: Ping re-establish connection", 2) # LOGWARNING
                        self.EmbyServer.ServerReconnect()
                    else:
                        PingTimeoutCounter += 1
                        xbmc.log(f"EMBY.emby.http: Ping timeout: {PingTimeoutCounter}", 2) # LOGWARNING

        xbmc.log("EMBY.emby.http: THREAD: ---<[ async queue ]", 0) # LOGDEBUG

    def wait_for_priority_request(self):
        LOGDone = False

        while self.Priority:
            if not LOGDone:
                LOGDone = True
                xbmc.log("EMBY.emby.http: Delay queries, priority request in progress", 1) # LOGINFO

            if utils.sleep(0.1):
                return

        if LOGDone:
            xbmc.log("EMBY.emby.http: Delay queries, continue", 1) # LOGINFO

    def stop_session(self):
        if not self.session:
            xbmc.log("EMBY.emby.http: Session close: No session found", 0) # LOGDEBUG
            return

        try:
            self.session.clear()
        except Exception as error:
            xbmc.log(f"EMBY.emby.http: Session close error: {error}", 2) # LOGWARNING

        self.session = None
        self.AsyncCommandQueue.put("QUIT")
        self.FileDownloadQueue.put("QUIT")
        xbmc.log("EMBY.emby.http: Session close", 1) # LOGINFO

    # decide threaded or wait for response
    def request(self, data, ForceReceiveData, Binary, GetHeaders=False, LastWill=False, Priority=False, Download=None):
        ServerUnreachable = False

        if Priority:
            self.Priority = True

        if 'url' not in data:
            data['url'] = f"{self.EmbyServer.ServerData['ServerUrl']}/emby/{data.pop('handler', '')}"

        if 'headers' not in data:
            Header = {'Content-type': "application/json", 'Accept-Charset': "UTF-8,*", 'Accept-encoding': "gzip", 'User-Agent': f"{utils.addon_name}/{utils.addon_version}"}
        else:
            Header = data['headers']
            del data['headers']

        if 'Authorization' not in Header:
            auth = f"Emby Client={utils.addon_name},Device={utils.device_name},DeviceId={self.EmbyServer.ServerData['DeviceId']},Version={utils.addon_version}"

            if self.EmbyServer.ServerData['AccessToken'] and self.EmbyServer.ServerData['UserId']:
                Header.update({'Authorization': f"{auth},UserId={self.EmbyServer.ServerData['UserId']}", 'X-Emby-Token': self.EmbyServer.ServerData['AccessToken']})
            else:
                Header.update({'Authorization': auth})

        if not ForceReceiveData and (Priority or data['type'] in ("POST", "DELETE")):
            Timeout = TimeoutPriority
            RepeatSend = 20
        else:
            Timeout = TimeoutRegular
            RepeatSend = 2

        xbmc.log(f"EMBY.emby.http: [ http ] {data}", 0) # LOGDEBUG
        for Index in range(RepeatSend): # timeout 10 seconds
            if not Priority:
                self.wait_for_priority_request()

            if Index > 0:
                xbmc.log(f"EMBY.emby.http: Request no send, retry: {Index}", 2) # LOGWARNING

            # Shutdown
            if utils.SystemShutdown and not LastWill:
                self.stop_session()
                return self.noData(Binary, GetHeaders)

            # start session
            if not self.session:
                self.HeaderCache = {}

                if utils.sslverify:
                    self.session = urllib3.PoolManager(10, None, socket_options=[(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)])
                else:
                    self.session = urllib3.PoolManager(10, None, cert_reqs='CERT_NONE', assert_hostname=False, socket_options=[(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)])

                start_new_thread(self.async_commands, ())
                start_new_thread(self.download_file, ())

            # Update session headers
            if Header != self.HeaderCache:
                self.HeaderCache = Header.copy()
                self.session.headers = Header

            # http request
            try:
                if data['type'] == "HEAD":
                    if urllib3v1:
                        r = self.session.request('HEAD', data['url'], body=json.dumps(data.get("params", {})).encode('utf-8'), timeout=Timeout)
                    else:
                        r = self.session.request('HEAD', data['url'], json=data.get("params", {}), timeout=Timeout)

                    r.close()
                    self.Priority = False
                    return r.status

                if data['type'] == "GET":
                    if Download:
                        self.FileDownloadQueue.put(((data, Download),))
                        return None

                    if urllib3v1:
                        r = self.session.request('GET', data['url'], body=json.dumps(data.get("params", {})).encode('utf-8'), timeout=Timeout)
                    else:
                        r = self.session.request('GET', data['url'], json=data.get("params", {}), timeout=Timeout)

                    r.close()
                    self.Priority = False

                    if r.status == 200:
                        if Binary:
                            if GetHeaders:
                                return r.data, r.headers

                            return r.data

                        if urllib3v1:
                            return json.loads(r.data.decode('utf-8'))

                        return r.json()

                    if r.status == 401:
                        utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33147), time=utils.displayMessage)

                    xbmc.log(f"EMBY.emby.http: [ Statuscode ] {r.status}", 3) # LOGERROR
                    xbmc.log(f"EMBY.emby.http: [ Statuscode ] {data}", 0) # LOGDEBUG
                    return self.noData(Binary, GetHeaders)

                if data['type'] == "POST":
                    if Priority or ForceReceiveData:
                        if urllib3v1:
                            r = self.session.request('POST', data['url'], body=json.dumps(data.get("params", {})).encode('utf-8'), timeout=Timeout)
                        else:
                            r = self.session.request('POST', data['url'], json=data.get("params", {}), timeout=Timeout)

                        r.close()
                        self.Priority = False

                        if GetHeaders:
                            return r.data, r.headers

                        if urllib3v1:
                            return json.loads(r.data.decode('utf-8'))

                        return r.json()

                    self.AsyncCommandQueue.put(data)
                elif data['type'] == "DELETE":
                    self.AsyncCommandQueue.put(data)

                return self.noData(Binary, GetHeaders)
            except urllib3.exceptions.SSLError:
                xbmc.log("EMBY.emby.http: [ SSL error ]", 3) # LOGERROR
                xbmc.log(f"EMBY.emby.http: [ SSL error ] {data}", 0) # LOGDEBUG
                utils.Dialog.notification(heading=utils.addon_name, message=utils.Translate(33428), time=utils.displayMessage)
                self.stop_session()
                return self.noData(Binary, GetHeaders)
            except urllib3.exceptions.ConnectionError:
                xbmc.log("EMBY.emby.http: [ ServerUnreachable ]", 3) # LOGERROR
                xbmc.log(f"EMBY.emby.http: [ ServerUnreachable ] {data}", 0) # LOGDEBUG
                ServerUnreachable = True
                continue
            except urllib3.exceptions.TimeoutError:
                xbmc.log("EMBY.emby.http: [ ServerTimeout ]", 3) # LOGERROR
                xbmc.log(f"EMBY.emby.http: [ ServerTimeout ] {data}", 0) # LOGDEBUG
                continue
            except Exception as error:
                xbmc.log(f"EMBY.emby.http: [ Unknown ] {error}", 3) # LOGERROR
                xbmc.log(f"EMBY.emby.http: [ Unknown ] {data} / {error}", 0) # LOGDEBUG
                return self.noData(Binary, GetHeaders)

        if ServerUnreachable:
            self.EmbyServer.ServerReconnect()

        return self.noData(Binary, GetHeaders)

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

    def noData(self, Binary, GetHeaders):
        self.Priority = False

        if Binary:
            if GetHeaders:
                return b"", {}

            return b""

        return {}
