import xbmc
from helper import pluginmenu, utils
from . import common

class Playlist:
    def __init__(self, EmbyServer, SQLs):
        self.EmbyServer = EmbyServer
        self.SQLs = SQLs

    def change(self, Item):
        common.load_ExistingItem(Item, self.EmbyServer, self.SQLs["emby"], "Playlist")
        IsFavorite = common.set_Favorite(Item)
        xbmc.log(f"EMBY.core.playlist: Process item: {Item['Name']}", 0) # DEBUG
        PlaylistItems = self.EmbyServer.API.get_Items(Item['Id'], ["Episode", "Movie", "Trailer", "MusicVideo", "Audio", "Video", "Photo"], True, True, {},"")
        KodiItemId = utils.valid_Filename(Item['Name'])
        PlaylistFilename = f"{utils.PlaylistPath}{KodiItemId}.m3u"
        isFavorite = common.set_Favorite(Item)
        utils.delFile(PlaylistFilename)
        M3UPlaylist = "#EXTM3U\n"

        for PlaylistItem in PlaylistItems:
            M3UPlaylist += f"#EXTINF:-1,{PlaylistItem['Name']}\n"
            M3UPlaylist += f"plugin://plugin.video.emby-next-gen/?mode=play&server={self.EmbyServer.ServerData['ServerId']}&item={PlaylistItem['Id']}\n"

        utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Playlist", "Playlists", Item['Id'], self.EmbyServer.ServerData['ServerId'], ""), IsFavorite, f"special://profile/playlists/mixed/{Item['KodiItemId']}.m3u", Item['Name'], "window", 10025),))
        utils.writeFileBinary(PlaylistFilename, M3UPlaylist.encode("utf-8"))
        self.SQLs["emby"].add_reference_metadata(Item['Id'], Item['LibraryId'], "Playlist", KodiItemId, isFavorite)
        return False

    def remove(self, Item):
        if self.SQLs["emby"].remove_item(Item['Id'], "PlayList", Item['LibraryId']):
            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Playlist", "Playlists", Item['Id'], self.EmbyServer.ServerData['ServerId'], ""), False, f"special://profile/playlists/mixed/{utils.valid_Filename(Item['KodiItemId'])}/", Item['KodiItemId'], "window", 10025),))
            utils.delFile(f"{utils.PlaylistPath}{Item['KodiItemId']}.m3u")
            xbmc.log(f"EMBY.core.playlist: DELETE [{Item['KodiItemId']}] {Item['Id']}", 1) # LOGINFO

    def userdata(self, Item):
        utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Playlist", "Playlists", Item['Id'], self.EmbyServer.ServerData['ServerId'], ""), Item['IsFavorite'], f"special://profile/playlists/mixed/{utils.valid_Filename(Item['KodiItemId'])}.m3u", Item['KodiItemId'], "window", 10025),))
        self.SQLs["emby"].update_favourite(Item['IsFavorite'], Item['Id'], "Playlist")
        pluginmenu.reset_querycache("PlayList")
        xbmc.log(f"EMBY.core.playlist: USERDATA [{Item['KodiItemId']}] {Item['Id']}", 1) # LOGINFO
