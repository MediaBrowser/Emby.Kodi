import json
from _thread import start_new_thread, allocate_lock
import xbmc
from helper import pluginmenu, utils, playerops, xmls, player, queue, deduplicate
from database import dbio
from emby import emby
from . import webservice, favorites

QueueItemsStatusupdate = ()
QueryItemStatusThread = False
QueueItemsRemove = ()
QueryItemRemoveThread = False
FullShutdown = False
utils.FavoriteQueue = queue.Queue()
syncEmbyLock = allocate_lock()
VideoLibrary_OnUpdateLock = allocate_lock()
VideoLibrary_OnRemoveLock = allocate_lock()


class monitor(xbmc.Monitor):
    def onNotification(self, _sender, method, data):
        if method == "Player.OnPlay":
            player.PlayerEventsQueue.put((("play", data),))
        elif method == "Player.OnStop":
            player.PlayerEventsQueue.put((("stop", data),))
        elif method == 'Player.OnSeek':
            player.PlayerEventsQueue.put((("seek", data),))
        elif method == "Player.OnAVChange":
            player.PlayerEventsQueue.put((("avchange", data),))
        elif method == "Player.OnAVStart":
            player.PlayerEventsQueue.put((("avstart", data),))
        elif method == "Player.OnPause":
            player.PlayerEventsQueue.put((("pause",),))
        elif method == "Player.OnResume":
            player.PlayerEventsQueue.put((("resume",),))
        if method == "Player.OnPropertyChanged":
            player.PlayerEventsQueue.put((("propertychanged", data),))
        if method == "Player.OnSpeedChanged":
            player.PlayerEventsQueue.put((("speedchanged", data),))
        elif method == 'Application.OnVolumeChanged':
            player.PlayerEventsQueue.put((("volume", data),))
        elif method == "Playlist.OnAdd":
            player.PlayerEventsQueue.put((("add", data),))
        elif method == "Playlist.OnRemove":
            player.PlayerEventsQueue.put((("remove", data),))
        elif method == "Playlist.OnClear":
            player.PlayerEventsQueue.put((("clear", data),))
        elif method == 'System.OnWake':
            xbmc.log("EMBY.hooks.monitor: --<[ sleep ]", 1) # LOGINFO

            for EmbyServer in list(utils.EmbyServers.values()):
                EmbyServer.ServerReconnect(False)

            utils.SyncPause['kodi_sleep'] = False
        elif method == 'System.OnSleep':
            xbmc.log("EMBY.hooks.monitor: -->[ sleep ]", 1) # LOGINFO
            utils.SyncPause['kodi_sleep'] = True

            if not player.PlayBackEnded and player.PlayingItem[4]:
                player.PlayerEventsQueue.put((("stop", '{"end":"quit"}'),))

                while not player.PlayerEventsQueue.isEmpty():
                    utils.sleep(0.5)

            EmbyServer_DisconnectAll()
        elif method == 'System.OnQuit':
            xbmc.log("EMBY.hooks.monitor: System_OnQuit", 1) # LOGINFO
            ShutDown()
        elif method == 'Other.managelibsselection':
            start_new_thread(pluginmenu.select_managelibs, ())
        elif method == 'Other.deduplicate':
            start_new_thread(deduplicate.deduplicate, ())
        elif method == 'Other.settings':
            start_new_thread(opensettings, ())
        elif method == 'Other.backup':
            start_new_thread(Backup, ())
        elif method == 'Other.restore':
            start_new_thread(BackupRestore, ())
        elif method == 'Other.skinreload':
            start_new_thread(pluginmenu.reset_querycache, (None,)) # Clear Cache
            xbmc.executebuiltin('ReloadSkin()')
            xbmc.log("EMBY.hooks.monitor: Reload skin by notification", 1) # LOGINFO
        elif method == 'Other.manageserver':
            start_new_thread(pluginmenu.manage_servers, (ServerConnect,))
        elif method == 'Other.databasereset':
            start_new_thread(pluginmenu.databasereset, (favorites, ))
        elif method == 'Other.nodesreset':
            start_new_thread(utils.nodesreset, ())
        elif method == 'Other.databasevacuummanual':
            start_new_thread(dbio.DBVacuum, ())
        elif method == 'Other.factoryreset':
            start_new_thread(pluginmenu.factoryreset, (False, favorites))
        elif method == 'Other.downloadreset':
            start_new_thread(pluginmenu.downloadreset, ("",))
        elif method == 'Other.texturecache':
            if not utils.artworkcacheenable:
                utils.Dialog.notification(heading=utils.addon_name, icon=utils.icon, message=utils.Translate(33226), sound=False, time=utils.displayMessage)
            else:
                start_new_thread(pluginmenu.cache_textures, ())
        elif method == 'VideoLibrary.OnUpdate' and not playerops.RemoteMode:  # Buffer updated items -> not overloading threads
            globals()["QueueItemsStatusupdate"] += (data,)

            if not QueryItemStatusThread:
                globals()["QueryItemStatusThread"] = True
                start_new_thread(VideoLibrary_OnUpdate, ())
        elif method == 'VideoLibrary.OnRemove' and not playerops.RemoteMode:  # Buffer updated items -> not overloading threads
            if utils.enableDeleteByKodiEvent:
                globals()["QueueItemsRemove"] += (data,)

                if not QueryItemRemoveThread:
                    globals()["QueryItemRemoveThread"] = True
                    start_new_thread(VideoLibrary_OnRemove, ())

    def onScanStarted(self, library):
        xbmc.log(f"EMBY.hooks.monitor: -->[ kodi scan / {library} ]", 1) # LOGINFO

        if not playerops.RemoteMode:
            utils.SyncPause['kodi_rw'] = True

    def onScanFinished(self, library):
        xbmc.log(f"EMBY.hooks.monitor: --<[ kodi scan / {library} ]", 1) # LOGINFO
        utils.WidgetRefresh[library] = False

        if not utils.WidgetRefresh['music'] and not utils.WidgetRefresh['video']:
            utils.SyncPause['kodi_rw'] = False

            if not playerops.RemoteMode:
                start_new_thread(syncEmby, ())

    def onCleanStarted(self, library):
        xbmc.log(f"EMBY.hooks.monitor: -->[ kodi clean / {library} ]", 1) # LOGINFO

        if not playerops.RemoteMode:
            utils.SyncPause['kodi_rw'] = True

    def onCleanFinished(self, library):
        xbmc.log(f"EMBY.hooks.monitor: --<[ kodi clean / {library} ]", 1) # LOGINFO
        utils.WidgetRefresh[library] = False

        if not utils.WidgetRefresh['music'] and not utils.WidgetRefresh['video']:
            utils.SyncPause['kodi_rw'] = False

            if not playerops.RemoteMode:
                start_new_thread(syncEmby, ())

    def onSettingsChanged(self):
        xbmc.log("EMBY.hooks.monitor: Seetings changed", 1) # LOGINFO
        start_new_thread(settingschanged, ())

def opensettings():
    xbmc.executebuiltin('Dialog.Close(all,true)') # blocking
    xbmc.executebuiltin('Addon.OpenSettings(plugin.service.emby-next-gen)')

def syncEmby():
    xbmc.log("EMBY.hooks.monitor: THREAD: --->[ syncEmby ]", 0) # LOGDEBUG

    with syncEmbyLock:
        for EmbyServer in list(utils.EmbyServers.values()):
            EmbyServer.library.RunJobs(True)

        xbmc.log("EMBY.hooks.monitor: THREAD: ---<[ syncEmby ]", 0) # LOGDEBUG

# Remove Items
def VideoLibrary_OnRemove(): # Cache queries to minimize database openings
    if utils.sleep(0.5):
        return

    xbmc.log("EMBY.hooks.monitor: THREAD: --->[ VideoLibrary_OnRemove ]", 0) # LOGDEBUG
    RemoveItems = QueueItemsRemove
    globals().update({"QueueItemsRemove": (), "QueryItemRemoveThread": False})

    with VideoLibrary_OnRemoveLock:
        if utils.Dialog.yesno(heading=utils.addon_name, message=utils.Translate(33264)):
            for ServerId, EmbyServer in list(utils.EmbyServers.items()):
                embydb = dbio.DBOpenRO(ServerId, "VideoLibrary_OnRemove")

                for RemoveItem in RemoveItems:
                    data = json.loads(RemoveItem)

                    if 'item' in data:
                        KodiId = data['item']['id']
                        KodiType = data['item']['type']
                    else:
                        KodiId = data['id']
                        KodiType = data['type']

                    if KodiType in ("tvshow", "season") or not KodiType or not KodiId:
                        continue

                    EmbyId = embydb.get_EmbyId_by_KodiId_KodiType(KodiId, KodiType)

                    if not EmbyId:
                        continue

                    EmbyServer.API.delete_item(EmbyId)

                dbio.DBCloseRO(ServerId, "VideoLibrary_OnRemove")

        xbmc.log("EMBY.hooks.monitor: THREAD: ---<[ VideoLibrary_OnRemove ]", 0) # LOGDEBUG

# Mark as watched/unwatched updates
def VideoLibrary_OnUpdate():
    if utils.sleep(0.5): # Cache queries to minimize database openings and redeuce threads
        return

    xbmc.log("EMBY.hooks.monitor: THREAD: --->[ VideoLibrary_OnUpdate ]", 0) # LOGDEBUG
    UpdateItems = QueueItemsStatusupdate
    globals().update({"QueueItemsStatusupdate": (), "QueryItemStatusThread": False})

    with VideoLibrary_OnUpdateLock:
        ItemsSkipUpdateRemove = ()

        for server_id, EmbyServer in list(utils.EmbyServers.items()):
            EmbyUpdateItems = {}
            embydb = None
            EmbyId = ""

            for UpdateItem in UpdateItems:
                xbmc.log(f"EMBY.hooks.monitor: VideoLibrary_OnUpdate process item: {UpdateItem}", 1) # LOGINFO
                data = json.loads(UpdateItem)
                EmbyId = ""

                if 'item' in data:
                    KodiItemId = int(data['item']['id'])
                    KodiType = data['item']['type']
                else:
                    KodiItemId = int(data['id'])
                    KodiType = data['type']

                if KodiType in utils.KodiTypeMapping:
                    pluginmenu.reset_querycache(utils.KodiTypeMapping[KodiType])

                if KodiItemId > 1000000000: # Dynamic Item
                    EmbyId = KodiItemId - 1000000000

                if EmbyId:
                    xbmc.log(f"EMBY.hooks.monitor: VideoLibrary_OnUpdate dynamic item detected: {EmbyId}", 1) # LOGINFO
                else: # Update synced item
                    if not embydb:
                        embydb = dbio.DBOpenRO(server_id, "VideoLibrary_OnUpdate")

                    EmbyId = embydb.get_EmbyId_by_KodiId_KodiType(KodiItemId, KodiType)

                    if not EmbyId:
                        continue

                if str(EmbyId) not in ItemsSkipUpdateRemove:
                    ItemsSkipUpdateRemove += (str(EmbyId),)

                if 'item' in data and 'playcount' in data:
                    if KodiType in ("tvshow", "season"):
                        xbmc.log(f"EMBY.hooks.monitor: [ VideoLibrary_OnUpdate skip playcount {KodiType} / {EmbyId} ]", 1) # LOGINFO
                        continue

                    if f"KODI{EmbyId}" not in utils.ItemSkipUpdate:  # Check EmbyID
                        xbmc.log(f"EMBY.hooks.monitor: [ VideoLibrary_OnUpdate update playcount {EmbyId} ]", 1) # LOGINFO

                        if int(EmbyId) in EmbyUpdateItems:
                            EmbyUpdateItems[int(EmbyId)]['PlayCount'] = data['playcount']
                        else:
                            EmbyUpdateItems[int(EmbyId)] = {'PlayCount': data['playcount']}
                    else:
                        xbmc.log(f"EMBY.hooks.monitor: [ VideoLibrary_OnUpdate skip playcount {EmbyId} ]", 1) # LOGINFO
                else:
                    if 'item' not in data:
                        if f"KODI{EmbyId}" not in utils.ItemSkipUpdate and EmbyId:  # Check EmbyID
                            if f"{{'item':{UpdateItem}}}" not in UpdateItems:
                                xbmc.log(f"EMBY.hooks.monitor: [ VideoLibrary_OnUpdate reset progress {EmbyId} ]", 1) # LOGINFO

                                if int(EmbyId) in EmbyUpdateItems:
                                    EmbyUpdateItems[int(EmbyId)].update({'Progress': 0, 'KodiItemId': KodiItemId, 'KodiType': KodiType})
                                else:
                                    EmbyUpdateItems[int(EmbyId)] = {'Progress': 0, 'KodiItemId': KodiItemId, 'KodiType': KodiType}
                            else:
                                xbmc.log(f"EMBY.hooks.monitor: VideoLibrary_OnUpdate skip reset progress (UpdateItems) {EmbyId}", 1) # LOGINFO
                        else:
                            xbmc.log(f"EMBY.hooks.monitor: VideoLibrary_OnUpdate skip reset progress (ItemSkipUpdate) {EmbyId}", 1) # LOGINFO

            kodidb = None

            for EmbyItemId, EmbyUpdateItem in list(EmbyUpdateItems.items()):
                utils.ItemSkipUpdate.append(str(EmbyItemId))

                if 'Progress' in EmbyUpdateItem:
                    if 'PlayCount' in EmbyUpdateItem:
                        EmbyServer.API.set_progress(EmbyItemId, EmbyUpdateItem['Progress'], EmbyUpdateItem['PlayCount'])
                    else:
                        if not kodidb:
                            kodidb = dbio.DBOpenRO("video", "VideoLibrary_OnUpdate")

                        PlayCount = kodidb.get_playcount(EmbyUpdateItem['KodiItemId'], EmbyUpdateItem['KodiType'])
                        EmbyServer.API.set_progress(EmbyItemId, EmbyUpdateItem['Progress'], PlayCount)
                else:
                    EmbyServer.API.set_played(EmbyItemId, EmbyUpdateItem['PlayCount'])

            if kodidb:
                dbio.DBCloseRO("video", "VideoLibrary_OnUpdate")

            if embydb:
                dbio.DBCloseRO(server_id, "VideoLibrary_OnUpdate")

        for ItemSkipUpdateRemove in ItemsSkipUpdateRemove:
            ItemSkipUpdateRemoveCompare = f"KODI{ItemSkipUpdateRemove}"

            if ItemSkipUpdateRemoveCompare in utils.ItemSkipUpdate:
                utils.ItemSkipUpdate.remove(ItemSkipUpdateRemoveCompare)

        xbmc.log(f"EMBY.hooks.monitor: VideoLibrary_OnUpdate ItemSkipUpdate: {utils.ItemSkipUpdate}", 1) # LOGINFO
        xbmc.log("EMBY.hooks.monitor: THREAD: ---<[ VideoLibrary_OnUpdate ]", 0) # LOGDEBUG

def BackupRestore():
    RestoreFolder = utils.Dialog.browseSingle(type=0, heading=utils.Translate(33643), shares='files', defaultt=utils.backupPath)
    MinVersionPath = f"{RestoreFolder}minimumversion.txt"

    if not utils.checkFileExists(MinVersionPath):
        utils.Dialog.notification(heading=utils.addon_name, icon=utils.icon, message=utils.Translate(33224), sound=False, time=utils.displayMessage)
        return

    BackupVersion = utils.readFileString(MinVersionPath)

    if BackupVersion != utils.MinimumVersion:
        utils.Dialog.notification(heading=utils.addon_name, icon=utils.icon, message=utils.Translate(33225), sound=False, time=utils.displayMessage)
        return

    _, files = utils.listDir(utils.FolderAddonUserdata)

    for Filename in files:
        utils.delFile(f"{utils.FolderAddonUserdata}{Filename}")

    # delete database
    _, files = utils.listDir("special://profile/Database/")

    for Filename in files:
        if Filename.startswith('emby') or Filename.startswith('My'):
            utils.delFile(f"special://profile/Database/{Filename}")

    utils.delete_playlists()
    utils.delete_nodes()
    RestoreFolderAddonData = f"{RestoreFolder}/addon_data/plugin.service.emby-next-gen/"
    utils.copytree(RestoreFolderAddonData, utils.FolderAddonUserdata)
    RestoreFolderDatabase = f"{RestoreFolder}/Database/"
    utils.copytree(RestoreFolderDatabase, "special://profile/Database/")
    utils.restart_kodi()

# Emby backup
def Backup():
    if not utils.backupPath:
        utils.Dialog.notification(heading=utils.addon_name, icon=utils.icon, message=utils.Translate(33229), sound=False, time=utils.displayMessage)
        return None

    path = utils.backupPath
    folder_name = f"Kodi{xbmc.getInfoLabel('System.BuildVersion')[:2]} - {xbmc.getInfoLabel('System.Date(yyyy-mm-dd)')} {xbmc.getInfoLabel('System.Time(hh:mm:ss xx)').replace(':', '-')}"
    folder_name = utils.Dialog.input(heading=utils.Translate(33089), defaultt=folder_name)

    if not folder_name:
        return None

    backup = f"{path}{folder_name}/"

    if utils.checkFolderExists(backup):
        if not utils.Dialog.yesno(heading=utils.addon_name, message=utils.Translate(33090)):
            return Backup()

        utils.delFolder(backup)

    destination_data = f"{backup}addon_data/plugin.service.emby-next-gen/"
    destination_databases = f"{backup}Database/"
    utils.mkDir(backup)
    utils.mkDir(f"{backup}addon_data/")
    utils.mkDir(destination_data)
    utils.mkDir(destination_databases)
    utils.copytree(utils.FolderAddonUserdata, destination_data)
    _, files = utils.listDir("special://profile/Database/")

    for Temp in files:
        if 'MyVideos' in Temp or 'emby' in Temp or 'MyMusic' in Temp:
            utils.copyFile(f"special://profile/Database/{Temp}", f"{destination_databases}/{Temp}")
            xbmc.log(f"EMBY.hooks.monitor: Copied {Temp}", 1) # LOGINFO

    utils.writeFileString(f"{backup}minimumversion.txt", utils.MinimumVersion)
    xbmc.log("EMBY.hooks.monitor: backup completed", 1) # LOGINFO
    utils.Dialog.ok(heading=utils.addon_name, message=f"{utils.Translate(33091)} {backup}")
    return None

def ServerConnect(ServerSettings):
    EmbyServerObj = emby.EmbyServer(ServerSettings)
    EmbyServerObj.ServerInitConnection()

def EmbyServer_DisconnectAll():
    for EmbyServer in list(utils.EmbyServers.values()):
        EmbyServer.stop()

def settingschanged():  # threaded by caller
    if utils.sleep(0.5):
        return

    xbmc.log("EMBY.hooks.monitor: THREAD: --->[ reload settings ]", 0) # LOGDEBUG
    xbmc.executebuiltin('Dialog.Close(addoninformation)')
    RestartKodi = False
    syncdatePrevious = utils.syncdate
    synctimePrevious = utils.synctime
    enablehttp2Previous = utils.enablehttp2
    xspplaylistsPreviousValue = utils.xspplaylists
    enableCoverArtPreviousValue = utils.enableCoverArt
    maxnodeitemsPreviousValue = utils.maxnodeitems
    AddonModePathPreviousValue = utils.AddonModePath
    websocketenabledPreviousValue = utils.websocketenabled
    curltimeoutsPreviousValue = utils.curltimeouts
    curlBoxSetsToTagsPreviousValue = utils.BoxSetsToTags
    DownloadPathPreviousValue = utils.DownloadPath
    SyncFavoritesPreviousValue = utils.SyncFavorites
    utils.InitSettings()

    # Http2 mode or curltimeouts changed, rebuild advanced settings -> restart Kodi
    if enablehttp2Previous != utils.enablehttp2 or curltimeoutsPreviousValue != utils.curltimeouts:
        if xmls.advanced_settings():
            RestartKodi = True

    # path(substitution) changed, update database pathes
    if AddonModePathPreviousValue != utils.AddonModePath:
        SQLs = {}
        dbio.DBOpenRW("video", "settingschanged", SQLs)
        SQLs["video"].toggle_path(AddonModePathPreviousValue, utils.AddonModePath)
        dbio.DBCloseRW("video", "settingschanged", SQLs)
        dbio.DBOpenRW("music", "settingschanged", SQLs)
        SQLs["music"].toggle_path(AddonModePathPreviousValue, utils.AddonModePath)
        dbio.DBCloseRW("music", "settingschanged", SQLs)
        utils.refresh_widgets(True)
        utils.refresh_widgets(False)

    # Toggle coverart setting
    if enableCoverArtPreviousValue != utils.enableCoverArt:
        DelArtwork = utils.Dialog.yesno(heading=utils.addon_name, message=utils.Translate(33644))

        if DelArtwork:
            RestartKodi = True
            pluginmenu.DeleteThumbnails()
        else:
            utils.set_settings_bool("enableCoverArt", enableCoverArtPreviousValue)

    # Toggle node items limit
    if maxnodeitemsPreviousValue != utils.maxnodeitems:
        utils.nodesreset()

    # Toggle websocket connection
    if websocketenabledPreviousValue != utils.websocketenabled:
        for EmbyServer in list(utils.EmbyServers.values()):
            EmbyServer.toggle_websocket(utils.websocketenabled)

    # Toggle collection tags
    if curlBoxSetsToTagsPreviousValue != utils.BoxSetsToTags:
        for EmbyServer in list(utils.EmbyServers.values()):
            EmbyServer.Views.add_nodes({'ContentType': "root"}, False)
            EmbyServer.library.refresh_boxsets()

    # Restart Kodi
    if RestartKodi:
        utils.SyncPause = {}
        webservice.close()
        EmbyServer_DisconnectAll()
        utils.restart_kodi()
        xbmc.log("EMBY.hooks.monitor: THREAD: ---<[ reload settings ] restart", 0) # LOGDEBUG
        return

    # Manual adjusted sync time/date
    if syncdatePrevious != utils.syncdate or synctimePrevious != utils.synctime:
        xbmc.log("EMBY.hooks.monitor: [ Trigger KodiStartSync due to setting changed ]", 1) # LOGINFO
        SyncTimestamp = f"{utils.syncdate} {utils.synctime}:00"
        SyncTimestamp = utils.convert_to_gmt(SyncTimestamp)

        for EmbyServer in list(utils.EmbyServers.values()):
            EmbyServer.library.set_syncdate(SyncTimestamp)
            start_new_thread(EmbyServer.library.KodiStartSync, (False,))

    for EmbyServer in list(utils.EmbyServers.values()):
        EmbyServer.API.update_settings()

    # Toggle xsp playlists
    if xspplaylistsPreviousValue != utils.xspplaylists:
        if utils.xspplaylists:
            for EmbyServer in list(utils.EmbyServers.values()):
                EmbyServer.Views.update_nodes()
        else:
            # delete playlists
            for playlistfolder in ['special://profile/playlists/video/', 'special://profile/playlists/music/']:
                if utils.checkFolderExists(playlistfolder):
                    _, files = utils.listDir(playlistfolder)

                    for Filename in files:
                        utils.delFile(f"{playlistfolder}{Filename}")

    # Change download path
    if DownloadPathPreviousValue != utils.DownloadPath:
        pluginmenu.downloadreset(DownloadPathPreviousValue)

    # Toggle Favorites
    if SyncFavoritesPreviousValue != utils.SyncFavorites:
        favorites.set_Favorites(utils.SyncFavorites)

    xbmc.log("EMBY.hooks.monitor: THREAD: ---<[ reload settings ]", 0) # LOGDEBUG

def ServersConnect():
    xbmc.log("EMBY.hooks.monitor: THREAD: --->[ ServersConnect ]", 0) # LOGDEBUG

    if utils.startupDelay:
        if utils.sleep(utils.startupDelay):
            utils.SyncPause = {}
            xbmc.log("EMBY.hooks.monitor: THREAD: ---<[ ServersConnect ] shutdown", 0) # LOGDEBUG
            return

    _, files = utils.listDir(utils.FolderAddonUserdata)
    ServersSettings = []

    for Filename in files:
        if Filename.startswith('server'):
            ServersSettings.append(f"{utils.FolderAddonUserdata}{Filename}")

    if not utils.WizardCompleted:  # First run
        utils.set_settings_bool('WizardCompleted', True)
        ServerConnect(None)
    else:
        for ServerSettings in ServersSettings:
            ServerConnect(ServerSettings)

    if utils.refreshskin:
        xbmc.executebuiltin('ReloadSkin()')
        xbmc.log("EMBY.hooks.monitor: Reload skin on connection established", xbmc.LOGINFO)

    xbmc.log("EMBY.hooks.monitor: THREAD: ---<[ ServersConnect ]", 0) # LOGDEBUG

def setup():
    # copy default nodes
    utils.mkDir("special://profile/library/")
    utils.mkDir("special://profile/library/video/")
    utils.mkDir("special://profile/library/music/")
    utils.copytree("special://xbmc/system/library/video/", "special://profile/library/video/")
    utils.copytree("special://xbmc/system/library/music/", "special://profile/library/music/")

    # copy animated icons
    for PluginId in ("video", "image", "audio"):
        Destination = f"special://home/addons/plugin.{PluginId}.emby-next-gen/resources/icon-animated.gif"

        if not utils.checkFileExists(Destination):
            utils.copyFile("special://home/addons/plugin.service.emby-next-gen/resources/icon-animated.gif", Destination)

    if utils.MinimumSetup == "OPENLIBRARY":
        utils.set_settings('MinimumSetup', utils.MinimumVersion)
        return "OPENLIBRARY"

    if utils.MinimumSetup == utils.MinimumVersion:
        return True

    xbmc.executebuiltin('ReplaceWindow(10000)', True)
    utils.refreshskin = False

    # Clean installation
    if not utils.MinimumSetup:
        value = utils.Dialog.yesno(heading=utils.Translate(30511), message=utils.Translate(33035), nolabel=utils.Translate(33036), yeslabel=utils.Translate(33037))

        if value:
            utils.set_settings_bool('useDirectPaths', True)
            utils.Dialog.ok(heading=utils.addon_name, message=utils.Translate(33145))
        else:
            utils.set_settings_bool('useDirectPaths', False)

        utils.update_mode_settings()
        xbmc.log(f"EMBY.hooks.monitor: Add-on playback: {utils.useDirectPaths == '0'}", 1) # LOGINFO
        utils.set_settings('MinimumSetup', utils.MinimumVersion)
        xmls.sources() # verify sources.xml

        if xmls.advanced_settings(): # verify advancedsettings.xml
            return False

        return True

    if not utils.Dialog.yesno(heading=utils.addon_name, message=utils.Translate(33222)): # final warning
        return "stop"

    pluginmenu.factoryreset(True, favorites)
    return False

def StartUp():
    xbmc.log("EMBY.hooks.monitor: [ Start Emby-next-gen ]", 1) # LOGINFO
    Ret = setup()

    if Ret == "stop":  # db upgrade declined
        webservice.close()
        xbmc.log("EMBY.hooks.monitor: [ DB upgrade declined, Shutdown Emby-next-gen ]", 3) # LOGERROR
    elif not Ret:  # db reset required
        xbmc.log("EMBY.hooks.monitor: [ DB reset required, Kodi restart ]", 2) # LOGWARNING
        webservice.close()
        utils.restart_kodi()
    else:  # Regular start
        xbmc.log("EMBY.hooks.monitor: Monitor listening", 1) # LOGINFO
        globals()['FullShutdown'] = True
        XbmcMonitor = monitor()  # Init Monitor
        start_new_thread(favorites.monitor_Favorites, ())
        start_new_thread(favorites.emby_change_Favorite, ())

        if Ret == "OPENLIBRARY":
            ServersConnect()
            xbmc.executebuiltin('Dialog.Close(all,true)') # blocking
            utils.SendJson('{"jsonrpc": "2.0", "id": 1, "method": "GUI.ActivateWindow", "params": {"window": 10000}}')

            for EmbyServer in list(utils.EmbyServers.values()):
                while not EmbyServer.Loaded:
                    if utils.sleep(1):
                        break
                else:
                    EmbyServer.library.select_libraries("AddLibrarySelection")
        else:
            start_new_thread(ServersConnect, ())

        XbmcMonitor.waitForAbort(0) # Waiting/blocking function till Kodi stops

    ShutDown()

def ShutDown():
    if FullShutdown:
        # Shutdown
        globals()['FullShutdown'] = False
        utils.SystemShutdown = True
        utils.FavoriteQueue.put("QUIT")

        if not player.PlayBackEnded and player.PlayingItem[4]:
            player.PlayerEventsQueue.put((("stop", '{"end":"quit"}'),))

            while not player.PlayerEventsQueue.isEmpty():
                xbmc.sleep(100)

        EmbyServer_DisconnectAll()

        for RemoteCommandQueue in list(playerops.RemoteCommandQueue.values()):
            RemoteCommandQueue.put("QUIT")

        webservice.close()
        xbmc.log("EMBY.hooks.monitor: [ Shutdown Emby-next-gen ]", 2) # LOGWARNING

    player.PlayerEventsQueue.put("QUIT")
    utils.SystemShutdown = True
    xbmc.log("EMBY.hooks.monitor: Exit Emby-next-gen", 1) # LOGINFO
