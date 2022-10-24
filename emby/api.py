from helper import utils, loghandler
from database import dbio

EmbyPagingFactors = {"MusicArtist": 100, "MusicAlbum": 100, "Audio": 200, "Movie": 50, "BoxSet": 50, "Series": 50, "Season": 50, "Episode": 50, "MusicVideo": 50, "Video": 50, "Everything": 50, "Photo": 50, "PhotoAlbum": 50, "Playlist": 50, "Channels": 50, "Folder": 1000}
EmbyFields = {
    "MusicArtist": ("Genres", "SortName", "ProductionYear", "DateCreated", "ProviderIds", "Overview", "Path", "PresentationUniqueKey"),
    "MusicAlbum": ("Genres", "SortName", "ProductionYear", "DateCreated", "ProviderIds", "Overview", "Path", "PresentationUniqueKey", "Studios", "PremiereDate"),
    "Audio": ("Genres", "SortName", "ProductionYear", "DateCreated", "MediaStreams", "ProviderIds", "Overview", "Path", "ParentId", "PresentationUniqueKey", "PremiereDate"),
    "Movie": ("Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "LocalTrailerCount", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "CriticRating", "ShortOverview", "ProductionLocations", "ProviderIds", "ParentId", "RemoteTrailers", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "PartCount", "SpecialFeatureCount", "Chapters", "Tags"),
    "BoxSet": ("Overview", "PresentationUniqueKey", "DateCreated"),
    "Series": ("Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "CriticRating", "ShortOverview", "ProviderIds", "ParentId", "Status", "PresentationUniqueKey", "OriginalTitle", "Tags", "LocalTrailerCount", "RemoteTrailers"),
    "Season": ("PresentationUniqueKey", "Tags", "DateCreated"),
    "Episode": ("SpecialEpisodeNumbers", "Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "LocalTrailerCount", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "CriticRating", "ShortOverview", "Tags", "ProviderIds", "ParentId", "RemoteTrailers", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "PartCount", "SpecialFeatureCount", "Chapters"),
    "MusicVideo": ("Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "CriticRating", "ShortOverview", "Tags", "ProviderIds", "ParentId", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "PartCount", "Chapters"),
    "Video": ("Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "LocalTrailerCount", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "CriticRating", "ShortOverview", "ProductionLocations", "ProviderIds", "ParentId", "RemoteTrailers", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "PartCount", "SpecialFeatureCount", "Chapters", "Tags"),
    "Everything": ("SpecialEpisodeNumbers", "Path", "Genres", "SortName", "Studios", "Writer", "Taglines", "LocalTrailerCount", "Video3DFormat", "OfficialRating", "PremiereDate", "ProductionYear", "DateCreated", "People", "Overview", "CommunityRating", "CriticRating", "ShortOverview", "ProductionLocations", "Tags", "ProviderIds", "ParentId", "RemoteTrailers", "MediaSources", "PresentationUniqueKey", "OriginalTitle", "AlternateMediaSources", "PartCount", "SpecialFeatureCount", "Chapters", "MediaStreams"),
    "Photo": ("Path", "SortName", "ProductionYear", "ParentId", "PremiereDate", "Width", "Height", "Tags", "DateCreated"),
    "PhotoAlbum": ("Path", "SortName", "Taglines", "DateCreated", "ShortOverview", "ProductionLocations", "Tags", "ParentId", "OriginalTitle"),
    "TvChannel": ("Genres", "SortName", "Taglines", "DateCreated", "Overview", "MediaSources", "Tags", "MediaStreams"),
    "Folder": ("Path", )
}
LOG = loghandler.LOG('EMBY.emby.api')


class API:
    def __init__(self, EmbyServer):
        self.DynamicListsRemoveFields = ()
        self.EmbyServer = EmbyServer
        self.update_settings()

    def update_settings(self):
        self.DynamicListsRemoveFields = ()

        if not utils.getDateCreated:
            self.DynamicListsRemoveFields += ("DateCreated",)

        if not utils.getGenres:
            self.DynamicListsRemoveFields += ("Genres",)

        if not utils.getStudios:
            self.DynamicListsRemoveFields += ("Studios",)

        if not utils.getTaglines:
            self.DynamicListsRemoveFields += ("Taglines",)

        if not utils.getOverview:
            self.DynamicListsRemoveFields += ("Overview",)

        if not utils.getProductionLocations:
            self.DynamicListsRemoveFields += ("ProductionLocations",)

        if not utils.getCast:
            self.DynamicListsRemoveFields += ("People",)

    def get_Items_dynamic(self, parent_id, MediaTypes, Basic, Recursive, Extra, Resume, Latest=False, MusicVideo=False):
        SingleRun = False
        Limit = get_Limit(MediaTypes)
        IncludeItemTypes, _ = self.get_MediaData(MediaTypes, Basic, True)
        params = {
            'ParentId': parent_id,
            'IncludeItemTypes': IncludeItemTypes,
            'CollapseBoxSetItems': False,
            'IsVirtualUnaired': False,
            'EnableTotalRecordCount': False,
            'LocationTypes': "FileSystem,Remote,Offline",
            'IsMissing': False,
            'Recursive': Recursive,
            'Limit': Limit
        }

        if Extra:
            params.update(Extra)

            if "Limit" in Extra:
                Limit = Extra["Limit"]
                SingleRun = True

        index = 0

        if Resume:
            url = "Users/%s/Items/Resume"
        elif Latest:
            url = "Users/%s/Items/Latest"
        else:
            url = "Users/%s/Items"

        embydb = dbio.DBOpenRO(self.EmbyServer.server_id, "get_Items_dynamic")
        videodb = dbio.DBOpenRO("video", "get_Items_dynamic")
        musicdb = dbio.DBOpenRO("music", "get_Items_dynamic")

        while True:
            params['StartIndex'] = index
            IncomingData = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': url % self.EmbyServer.user_id}, False, False)

            if Latest:
                if not IncomingData:
                    break

                IncomingData = {'Items': IncomingData}
            else:
                if 'Items' not in IncomingData:
                    break

                if not IncomingData['Items']:
                    break

            ItemsReturn = []
            ItemsFullQuery = []

            for Item in IncomingData['Items']:
                if not MusicVideo:
                    Data = embydb.get_KodiId_KodiType_by_EmbyId_EmbyLibraryId(Item['Id'], parent_id) # Requested video is synced to KodiDB.

                    if Data:
                        listitem, path, isFolder = utils.load_ContentMetadataFromKodiDB(Data[0], Data[1], videodb, musicdb)

                        if listitem:
                            ItemsReturn.append({"ListItem": listitem, "Path": path, "isFolder": isFolder})
                            LOG.info("Fetching data from internal database: %s / %s" % (Data[1], Data[0]))
                    else:
                        ItemsFullQuery.append(Item['Id'])
                else:
                    ItemsFullQuery.append(Item['Id'])

            IncomingData['Items'].clear()  # free memory

            # Load All Data
            while ItemsFullQuery:
                TempItemsFullQuery = ItemsFullQuery[:100]  # Chunks of 100
                ItemsFullQuery = ItemsFullQuery[100:]
                ItemsFull = self.get_Item(",".join(TempItemsFullQuery), ["Everything"], True, Basic, False)
                ItemsReturn += ItemsFull

            for ItemReturn in ItemsReturn:
                yield ItemReturn

            ItemsReturn = []

            if not Recursive or SingleRun: # Emby server bug workaround
                break

            index += Limit

        dbio.DBCloseRO("video", "get_Items_dynamic")
        dbio.DBCloseRO("music", "get_Items_dynamic")
        dbio.DBCloseRO(self.EmbyServer.server_id, "get_Items_dynamic")

    def get_Items(self, parent_id, MediaTypes, Basic, Recursive, Extra):
        SingleRun = False
        Limit = get_Limit(MediaTypes)
        IncludeItemTypes, Fields = self.get_MediaData(MediaTypes, Basic, False)
        params = {
            'ParentId': parent_id,
            'IncludeItemTypes': IncludeItemTypes,
            'CollapseBoxSetItems': False,
            'IsVirtualUnaired': False,
            'EnableTotalRecordCount': False,
            'LocationTypes': "FileSystem,Remote,Offline",
            'IsMissing': False,
            'Recursive': Recursive,
            'Limit': Limit,
            'Fields': Fields
        }

        if Extra:
            params.update(Extra)

            if "Limit" in Extra:
                Limit = Extra["Limit"]
                SingleRun = True

        index = 0

        while True:
            params['StartIndex'] = index
            IncomingData = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Users/%s/Items" % self.EmbyServer.user_id}, False, False)

            if 'Items' not in IncomingData:
                break

            if not IncomingData['Items']:
                break

            for Item in IncomingData['Items']:
                yield Item

            IncomingData['Items'].clear()  # free memory

            if not Recursive or SingleRun: # Emby server bug workaround
                break

            index += Limit

    def get_TotalRecordsRegular(self, parent_id, item_type, Extra=None):
        params = {
            'ParentId': parent_id,
            'IncludeItemTypes': item_type,
            'CollapseBoxSetItems': False,
            'IsVirtualUnaired': False,
            'IsMissing': False,
            'EnableTotalRecordCount': True,
            'LocationTypes': "FileSystem,Remote,Offline",
            'Recursive': True,
            'Limit': 1
        }

        if Extra:
            params.update(Extra)

        Data = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Users/%s/Items" % self.EmbyServer.user_id}, False, False)

        if 'TotalRecordCount' in Data:
            return int(Data['TotalRecordCount'])

        return 0

    def browse_MusicByArtistId(self, Artist_id, Parent_id, MediaTypes, Dynamic):
        IncludeItemTypes, Fields = self.get_MediaData(MediaTypes, False, Dynamic)
        params = {
            'ParentId': Parent_id,
            'ArtistIds': Artist_id,
            'IncludeItemTypes': IncludeItemTypes,
            'IsMissing': False,
            'Recursive': True,
            'Fields': Fields
        }
        Data = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Users/%s/Items" % self.EmbyServer.user_id}, False, False)

        if 'Items' in Data:
            return Data['Items']

        return []

    def get_genres(self, ParentId, MediaTypes):
        IncludeItemTypes, Fields = self.get_MediaData(MediaTypes, False, False)
        params = {
            'ParentId': ParentId,
            'IncludeItemTypes': IncludeItemTypes,
            'Recursive': True,
            'Fields': Fields
        }
        Data = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Genres"}, False, False)

        if 'Items' in Data:
            return Data['Items']

        return []

    def get_tags(self, ParentId, MediaTypes):
        IncludeItemTypes, Fields = self.get_MediaData(MediaTypes, False, False)
        params = {
            'ParentId': ParentId,
            'IncludeItemTypes': IncludeItemTypes,
            'Recursive': True,
            'Fields': Fields
        }
        Data = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Tags"}, False, False)

        if 'Items' in Data:
            return Data['Items']

        return []

    def get_users(self, disabled, hidden):
        params = {
            'IsDisabled': disabled,
            'IsHidden': hidden
        }
        return self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Users"}, False, False)

    def get_public_users(self):
        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Users/Public"}, False, False)

    def get_user(self, user_id):
        if not user_id:
            return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Users/%s" % self.EmbyServer.user_id}, False, False)

        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Users/%s" % user_id}, False, False)

    def get_libraries(self):
        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Library/VirtualFolders/Query"}, False, False)

    def get_views(self):
        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Users/%s/Views" % self.EmbyServer.user_id}, False, False)

    def get_Item_Basic(self, Id, ParentId, Type):
        Data = self.EmbyServer.http.request({'params': {'ParentId': ParentId, 'Ids': Id, 'Recursive': True, 'IncludeItemTypes': Type, 'Limit': 1}, 'type': "GET", 'handler': "Users/%s/Items" % self.EmbyServer.user_id}, False, False)

        if 'Items' in Data:
            return Data['Items']

        return []

    def get_Image_Binary(self, Id, ImageType, ImageIndex, ImageTag):
        Params = {}

        if utils.enableCoverArt:
            Params["EnableImageEnhancers"]: True
        else:
            Params["EnableImageEnhancers"]: False

        if utils.compressArt:
            Params["Quality"]: 70

        BinaryData, Headers = self.EmbyServer.http.request({'params': Params, 'type': "GET", 'handler': "Items/%s/Images/%s/%s?%s" % (Id, ImageType, ImageIndex, ImageTag)}, False, True, True)

        if 'Content-Type' in Headers:
            ContentType = Headers['Content-Type']

            if ContentType == "image/jpeg":
                FileExtension = "jpg"
            elif ContentType == "image/png":
                FileExtension = "png"
            elif ContentType == "image/gif":
                FileExtension = "gif"
            elif ContentType == "image/webp":
                FileExtension = "webp"
            elif ContentType == "image/apng":
                FileExtension = "apng"
            elif ContentType == "image/avif":
                FileExtension = "avif"
            elif ContentType == "image/svg+xml":
                FileExtension = "svg"
            else:
                FileExtension = "ukn"
        else:
            FileExtension = "ukn"
            ContentType = "ukn"

        return BinaryData, ContentType, FileExtension

    def get_Item(self, Ids, MediaTypes, Dynamic, Basic, SingleItemQuery=True):
        _, Fields = self.get_MediaData(MediaTypes, Basic, Dynamic)
        params = {
            'Ids': Ids,
            'Fields': Fields,
            'LocationTypes': "FileSystem,Remote,Offline"
        }
        Data = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Users/%s/Items" % self.EmbyServer.user_id}, False, False)

        if SingleItemQuery:
            if 'Items' in Data:
                if Data['Items']:
                    return Data['Items'][0]

            return {}

        if 'Items' in Data:
            return Data['Items']

        return []

    def get_device(self):
        return self.EmbyServer.http.request({'params': {'DeviceId': utils.device_id}, 'type': "GET", 'handler': "Sessions"}, False, False)

    def get_channels(self):
        params = {
            'UserId': self.EmbyServer.user_id,
            'EnableImages': True,
            'EnableUserData': True,
            'Fields': EmbyFields['TvChannel']
        }
        Data = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "LiveTv/Channels"}, False, False)

        if 'Items' in Data:
            return Data['Items']

        return []

    def get_channelprogram(self):
        params = {
            'UserId': self.EmbyServer.user_id,
            'EnableImages': True,
            'EnableUserData': True,
            'Fields': "Overview"
        }
        return self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "LiveTv/Programs"}, False, False)

    def get_specialfeatures(self, item_id):
        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Users/%s/Items/%s/SpecialFeatures" % (self.EmbyServer.user_id, item_id)}, False, False)

    def get_intros(self, item_id):
        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Users/%s/Items/%s/Intros" % (self.EmbyServer.user_id, item_id)}, False, False)

    def get_additional_parts(self, item_id):
        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Videos/%s/AdditionalParts" % item_id}, False, False)

    def get_local_trailers(self, item_id):
        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Users/%s/Items/%s/LocalTrailers" % (self.EmbyServer.user_id, item_id)}, False, False)

    def get_themes(self, item_id):
        params = {
            'UserId': self.EmbyServer.user_id,
            'InheritFromParent': True,
            'EnableThemeSongs': True,
            'EnableThemeVideos': True
        }
        return self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Items/%s/ThemeMedia" % item_id}, False, False)

    def get_plugins(self):
        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "Plugins"}, False, False)

    def get_sync_queue(self, date):
        return self.EmbyServer.http.request({'params': {'LastUpdateDT': date}, 'type': "GET", 'handler': "Emby.Kodi.SyncQueue/%s/GetItems" % self.EmbyServer.user_id}, False, False)

    def get_system_info(self):
        return self.EmbyServer.http.request({'params': {}, 'type': "GET", 'handler': "System/Configuration"}, False, False)

    def set_progress(self, item_id, Progress, PlayCount):
        params = {"PlaybackPositionTicks": Progress}

        if PlayCount != -1:
            params["PlayCount"] = PlayCount
            params["Played"] = bool(PlayCount)

        self.EmbyServer.http.request({'params': params, 'type': "POST", 'handler': "Users/%s/Items/%s/UserData" % (self.EmbyServer.user_id, item_id)}, False, False)

    def set_played(self, item_id, PlayCount):
        if PlayCount:
            self.EmbyServer.http.request({'params': {}, 'type': "POST", 'handler': "Users/%s/PlayedItems/%s" % (self.EmbyServer.user_id, item_id)}, False, False)
        else:
            self.EmbyServer.http.request({'params': {}, 'type': "DELETE", 'handler': "Users/%s/PlayedItems/%s" % (self.EmbyServer.user_id, item_id)}, False, False)

    def refresh_item(self, item_id):
        params = {
            'Recursive': True,
            'ImageRefreshMode': "FullRefresh",
            'MetadataRefreshMode': "FullRefresh",
            'ReplaceAllImages': False,
            'ReplaceAllMetadata': True
        }
        self.EmbyServer.http.request({'params': params, 'type': "POST", 'handler': "Items/%s/Refresh" % item_id}, False, False)

    def favorite(self, item_id, Add):
        if Add:
            self.EmbyServer.http.request({'params': {}, 'type': "POST", 'handler': "Users/%s/FavoriteItems/%s" % (self.EmbyServer.user_id, item_id)}, False, False)
        else:
            self.EmbyServer.http.request({'params': {}, 'type': "DELETE", 'handler': "Users/%s/FavoriteItems/%s" % (self.EmbyServer.user_id, item_id)}, False, False)

    def post_capabilities(self, params):
        self.EmbyServer.http.request({'params': params, 'type': "POST", 'handler': "Sessions/Capabilities/Full"}, False, False)

    def session_add_user(self, session_id, user_id, option):
        if option:
            self.EmbyServer.http.request({'params': {}, 'type': "POST", 'handler': "Sessions/%s/Users/%s" % (session_id, user_id)}, False, False)
        else:
            self.EmbyServer.http.request({'params': {}, 'type': "DELETE", 'handler': "Sessions/%s/Users/%s" % (session_id, user_id)}, False, False)

    def session_playing(self, params):
        self.EmbyServer.http.request({'params': params, 'type': "POST", 'handler': "Sessions/Playing"}, False, False)

    def session_progress(self, params):
        self.EmbyServer.http.request({'params': params, 'type': "POST", 'handler': "Sessions/Playing/Progress"}, False, False)

    def session_stop(self, params):
        self.EmbyServer.http.request({'params': params, 'type': "POST", 'handler': "Sessions/Playing/Stopped"}, False, False)

    def close_transcode(self):
        self.EmbyServer.http.request({'params': {'DeviceId': utils.device_id}, 'type': "DELETE", 'handler': "Videos/ActiveEncodings"}, False, False)

    def delete_item(self, item_id):
        self.EmbyServer.http.request({'params': {}, 'type': "DELETE", 'handler': "Items/%s" % item_id}, False, False)

    def get_MediaData(self, MediaTypes, Basic, Dynamic):
        IncludeItemTypes = ",".join(MediaTypes)
        Fields = []

        if not Basic:
            if MediaTypes[0] == "Everything":
                IncludeItemTypes = None


            for MediaType in MediaTypes:
                Fields += EmbyFields[MediaType]

            #Dynamic list query, remove fields to improve performance
            if Dynamic:
                if "Series" in MediaTypes or "Season" in MediaTypes:
                    Fields += ("RecursiveItemCount", "ChildCount")

                for DynamicListsRemoveField in self.DynamicListsRemoveFields:
                    if DynamicListsRemoveField in Fields:
                        Fields.remove(DynamicListsRemoveField)

            Fields = ",".join(list(dict.fromkeys(Fields))) # remove duplicates and join into string
        else:
            Fields = None

        return IncludeItemTypes, Fields

    def get_upcoming(self, ParentId, MediaTypes):
        _, Fields = self.get_MediaData(MediaTypes, False, False)
        params = {
            'UserId': self.EmbyServer.user_id,
            'ParentId': ParentId,
            'Fields': Fields,
            'EnableImages': True,
            'EnableUserData': True
        }
        Data = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Shows/Upcoming"}, False, False)

        if 'Items' in Data:
            return Data['Items']

        return []

    def get_NextUp(self, ParentId, MediaTypes):
        _, Fields = self.get_MediaData(MediaTypes, False, False)
        params = {
            'UserId': self.EmbyServer.user_id,
            'ParentId': ParentId,
            'Fields': Fields,
            'EnableImages': True,
            'EnableUserData': True,
            'LegacyNextUp': True
        }
        Data = self.EmbyServer.http.request({'params': params, 'type': "GET", 'handler': "Shows/NextUp"}, False, False)

        if 'Items' in Data:
            return Data['Items']

        return []

def get_Limit(MediaTypes):
    Factor = 1000000

    for MediaType in MediaTypes:
        if EmbyPagingFactors[MediaType] < Factor:
            Factor = EmbyPagingFactors[MediaType]

    return int(utils.limitIndex) * Factor
