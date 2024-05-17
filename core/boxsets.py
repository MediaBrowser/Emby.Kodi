import xbmc
from helper import pluginmenu, utils
from . import common, tag

KodiTypeMapping = {"Movie": "movie", "Series": "tvshow", "MusicVideo": "musicvideo", "Video": "movie"}


class BoxSets:
    def __init__(self, EmbyServer, SQLs):
        self.EmbyServer = EmbyServer
        self.SQLs = SQLs
        self.TagObject = tag.Tag(EmbyServer, self.SQLs)

    def change(self, Item):
        common.load_ExistingItem(Item, self.EmbyServer, self.SQLs["emby"], "BoxSet")
        BoxSetKodiParentIds = ()
        TagItems = []

        # Query assigned content for collections
        ContentsAssignedToBoxset = []

        for ContentAssignedToBoxset in self.EmbyServer.API.get_Items(Item['Id'], ["All"], True, True, {'GroupItemsIntoCollections': True}):
            ContentsAssignedToBoxset.append(ContentAssignedToBoxset)

        # Add new collection tag
        if utils.BoxSetsToTags:
            TagItems = [{"LibraryId": Item["LibraryId"], "Type": "Tag", "Id": f"999999993{Item['Id']}", "Name": f"{Item['Name']} (Collection)", "Memo": "collection", 'ImageTags': Item.get('ImageTags', {})}]
            self.TagObject.change(TagItems[0])

        # Boxsets
        common.set_overview(Item)

        if Item['UpdateItem']:
            self.SQLs["video"].common_db.delete_artwork(Item['KodiItemId'], "set")
            self.SQLs["video"].update_boxset(Item['Name'], Item['Overview'], Item['KodiItemId'])
        else:
            xbmc.log(f"EMBY.core.boxsets: SetId {Item['Id']} not found", 0) # LOGDEBUG
            Item['KodiItemId'] = self.SQLs["video"].add_boxset(Item['Name'], Item['Overview'])

        if Item['KodiParentId']:
            CurrentBoxSetContent = Item['KodiParentId'].split(",")
        else:
            CurrentBoxSetContent = []

        for ContentAssignedToBoxset in ContentsAssignedToBoxset:
            if ContentAssignedToBoxset['Type'] not in ("Movie", "Series", "MusicVideo", "Video"): # Episode and season tags not supported by Kodi
                continue

            ContentAssignedToBoxset.update({'KodiItemId': Item['KodiItemId']})
            ContentItemKodiId = self.SQLs["emby"].get_KodiId_by_EmbyId_EmbyType(ContentAssignedToBoxset['Id'], ContentAssignedToBoxset['Type'])

            if ContentAssignedToBoxset['Type'] in ("Movie", "Video") and ContentItemKodiId:
                if str(ContentItemKodiId) in CurrentBoxSetContent:
                    CurrentBoxSetContent.remove(str(ContentItemKodiId))

                xbmc.log(f"EMBY.core.boxsets: ADD to Kodi set [{Item['KodiItemId']}] {ContentAssignedToBoxset['Name']}: {ContentAssignedToBoxset['Id']}", 1) # LOGINFO
                self.SQLs["video"].set_boxset(Item['KodiItemId'], ContentItemKodiId) # assign boxset to movie
                BoxSetKodiParentIds += (str(ContentItemKodiId),)

            # Assign content to collection tag
            if utils.BoxSetsToTags and ContentItemKodiId:
                common.set_Tag_links(ContentItemKodiId, self.SQLs, KodiTypeMapping[ContentAssignedToBoxset['Type']], TagItems)
                xbmc.log(f"EMBY.core.boxsets: ADD to tag [{Item['KodiItemId']}] {ContentAssignedToBoxset['Name']}: {ContentAssignedToBoxset['Id']}", 1) # LOGINFO

        # Delete remove content from boxsets
        for KodiContentId in CurrentBoxSetContent:
            self.SQLs["video"].remove_from_boxset(KodiContentId)
            xbmc.log(f"EMBY.core.boxsets: DELETE from boxset [{Item['Id']}] {Item['KodiItemId']} {Item['Name']}: {KodiContentId}", 1) # LOGINFO

        common.set_KodiArtwork(Item, self.EmbyServer.ServerData['ServerId'], False)
        self.SQLs["video"].common_db.add_artwork(Item['KodiArtwork'], Item['KodiItemId'], "set")
        Item['KodiParentId'] = ",".join(BoxSetKodiParentIds)
        self.SQLs["emby"].add_reference_boxset(Item['Id'], Item['LibraryId'], Item['KodiItemId'], Item['UserData']['IsFavorite'], Item['KodiParentId'])
        self.set_favorite(Item['UserData']['IsFavorite'], Item['KodiItemId'], Item['Id'])
        xbmc.log(f"EMBY.core.boxsets: UPDATE [{Item['Id']}] {Item['KodiItemId']} {Item['Name']}", 1) # LOGINFO
        return True

    # This updates: Favorite, LastPlayedDate, PlaybackPositionTicks
    def userdata(self, Item):
        self.SQLs["emby"].update_favourite(Item['IsFavorite'], Item['Id'], "BoxSet")

        if utils.BoxSetsToTags:
            EmbyTagId = f"999999993{Item['Id']}"
            self.SQLs["emby"].update_favourite(Item['IsFavorite'], EmbyTagId, "Tag")

        self.set_favorite(Item['IsFavorite'], Item['KodiItemId'], Item['Id'])
        pluginmenu.reset_querycache("BoxSet")
        xbmc.log(f"EMBY.core.boxsets: USERDATA {Item['Id']}", 1) # LOGINFO

    def remove(self, Item):
        KodiParentIds = self.SQLs["emby"].get_KodiParentIds(Item['Id'], "BoxSet")

        if self.SQLs["emby"].remove_item(Item['Id'], "BoxSet", Item['LibraryId']):
            self.SQLs["emby"].add_RemoveItem(f"999999993{Item['Id']}", Item['LibraryId'])

            for KodiParentId in KodiParentIds:
                self.SQLs["video"].remove_from_boxset(KodiParentId)

            self.SQLs["video"].common_db.delete_artwork(Item['KodiItemId'], "set")
            self.set_favorite(False, Item['KodiItemId'], Item['Id'])
            self.SQLs["video"].delete_boxset(Item['KodiItemId'])

        xbmc.log(f"EMBY.core.boxsets: DELETE [{Item['KodiItemId']} / {Item['KodiFileId']}] {Item['Id']}", 1) # LOGINFO

    def set_favorite(self, IsFavorite, KodiItemId, EmbyItemId):
        _, ImageUrl, Itemname = self.SQLs["video"].get_favoriteData(None, KodiItemId, "set")
        utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Boxset", "Set", EmbyItemId, self.EmbyServer.ServerData['ServerId'], ImageUrl), IsFavorite, f"videodb://movies/sets/{KodiItemId}/", Itemname, "window", 10025),))

        if utils.BoxSetsToTags:
            EmbyTagId = f"999999993{EmbyItemId}"
            KodiTagId = self.SQLs["emby"].get_KodiId_by_EmbyId_EmbyType(EmbyTagId, "Tag")

            if KodiTagId:
                self.TagObject.set_favorite(IsFavorite, KodiTagId, ImageUrl, EmbyTagId)
