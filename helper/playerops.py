import xbmc
from helper import utils, loghandler
from database import dbio
from emby import listitem

LOG = loghandler.LOG('EMBY.helper.playerops')
Pictures = []


def AddPlaylistItem(Position, EmbyID, Offset, EmbyServer, embydb):
    KodiId, KodiType = embydb.get_KodiId_KodiType_by_EmbyId_EmbyLibraryId(EmbyID)

    if KodiId:  # Requested video is synced to KodiDB. No additional info required
        if KodiType in ("song", "album", "artist"):
            playlistID = 0
            playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
        else:
            playlistID = 1
            playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)

        xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id": 1, "method": "Playlist.Insert", "params": {"playlistid": %s, "position": %s, "item": {"%sid": %d}}}' % (playlistID, GetPlaylistPos(Position, playlist, Offset), KodiType, int(KodiId)))
    else:
        item = EmbyServer.API.get_Item(EmbyID, ['Everything'], True, False)
        li = listitem.set_ListItem(item, EmbyServer.ServerData['ServerId'])
        path, Type = utils.get_path_type_from_item(EmbyServer.ServerData['ServerId'], item)

        if not path:
            return False, False, None

        if Type == "p":
            Pictures.append((path, li))
            return True, False, None

        li.setProperty('path', path)

        if Type == "a":
            playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
        else:
            playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)

        playlist.add(path, li, index=GetPlaylistPos(Position, playlist, Offset))

    return True, True, playlist

# Websocket command from Emby server
def Play(ItemIds, PlayCommand, StartIndex, StartPositionTicks, EmbyServer):
    FirstItem = True
    Offset = 0
    isPlaylist = False
    embydb = dbio.DBOpenRO(EmbyServer.ServerData['ServerId'], "AddPlaylistItem")
    globals()["Pictures"] = []

    for ID in ItemIds:
        playlist = None
        Offset += 1
        Found = False
        isPlaylist = False

        if PlayCommand == "PlayNow":
            Found, isPlaylist, playlist = AddPlaylistItem("current", ID, Offset, EmbyServer, embydb)
        elif PlayCommand == "PlayNext":
            Found, isPlaylist, playlist = AddPlaylistItem("current", ID, Offset, EmbyServer, embydb)
        elif PlayCommand == "PlayLast":
            Found, isPlaylist, playlist = AddPlaylistItem("last", ID, 0, EmbyServer, embydb)

        if not Found:
            continue

        if isPlaylist:  # picture
            # Play Item
            if PlayCommand == "PlayNow":
                if StartIndex != -1:
                    if Offset == int(StartIndex + 1):
                        if FirstItem:
                            Pos = playlist.getposition()

                            if Pos == -1:
                                Pos = 0

                            PlaylistStartIndex = Pos + Offset
                            utils.XbmcPlayer.play(item=playlist, startpos=PlaylistStartIndex)
                            setPlayerPosition(StartPositionTicks)
                            Offset = 0
                            FirstItem = False
                else:
                    if FirstItem:
                        Pos = playlist.getposition()

                        if Pos == -1:
                            Pos = 0

                        utils.XbmcPlayer.play(item=playlist, startpos=Pos + Offset)
                        setPlayerPosition(StartPositionTicks)
                        Offset = 0
                        FirstItem = False

    dbio.DBCloseRO(EmbyServer.ServerData['ServerId'], "AddPlaylistItem")

    # picture
    if not isPlaylist:
        if StartIndex != -1:
            globals()["Pictures"][StartIndex][1].select(True)

        xbmc.executebuiltin('Action(Stop)')
        xbmc.executebuiltin('Action(Back)')
        xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id": 1, "method": "Playlist.Clear", "params": {"playlistid": 2}}')
        xbmc.executebuiltin('ReplaceWindow(10002,"plugin://%s/?mode=remotepictures&position=%s")' % (utils.PluginId, StartIndex))

def setPlayerPosition(StartPositionTicks):
    if StartPositionTicks != -1:
        Position = StartPositionTicks / 10000000

        for _ in range(20):
            if utils.XbmcPlayer.isPlaying():
                try:
                    utils.XbmcPlayer.seekTime(Position)
                    CurrentTime = utils.XbmcPlayer.getTime()
                except Exception as error:
                    LOG.error(error)
                    continue

                if CurrentTime >= Position - 10:
                    return

                if utils.sleep(0.5):
                    return
            else:
                if utils.sleep(0.5):
                    return

def GetPlaylistPos(Position, playlist, Offset):
    if Position == "current":
        Pos = playlist.getposition()

        if Pos == -1:
            Pos = 0

        Pos = Pos + Offset
    elif Position == "previous":
        Pos = playlist.getposition()

        if Pos == -1:
            Pos = 0
    elif Position == "last":
        Pos = playlist.size()
    else:
        Pos = Position

    return Pos
