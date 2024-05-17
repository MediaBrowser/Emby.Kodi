import xbmc
import xbmcvfs
from helper import utils
from core import common
from database import dbio

FavoriteUpdatedByEmby = False


def monitor_Favorites():
    xbmc.log("EMBY.hooks.favorites: THREAD: --->[ Kodi favorites ]", 0) # LOGDEBUG
    globals()['FavoriteUpdatedByEmby'] = False
    FavoritesCached = get_Favorites()
    FavoriteTimestamp = 0

    while True:
        if utils.sleep(0.5):
            xbmc.log("EMBY.hooks.favorites: THREAD: ---<[ Kodi favorites ]", 0) # LOGDEBUG
            return

        Stats = xbmcvfs.Stat(utils.KodiFavFile)
        TimestampReadOut = Stats.st_mtime()

        # Skip favorite update
        if FavoriteUpdatedByEmby:
            globals()['FavoriteUpdatedByEmby'] = False
            FavoritesCached = get_Favorites()
            continue

        # Check if favorite.xml file has changed (by timestamp)
        if FavoriteTimestamp < TimestampReadOut:
            Trigger = bool(FavoriteTimestamp)
            FavoriteTimestamp = TimestampReadOut
            FavoritesCurrent = get_Favorites()

            if Trigger:
                FavoritesRemoved = []
                FavoritesAdded = []

                # detect removed favorites
                for FavoriteCached in FavoritesCached["Favorites"]:
                    if FavoriteCached not in FavoritesCurrent["Favorites"]:
                        FavoritesRemoved.append(FavoriteCached)

                # detect added favorites
                for FavoriteCurrent in FavoritesCurrent["Favorites"]:
                    if FavoriteCurrent not in FavoritesCached["Favorites"]:
                        FavoritesAdded.append(FavoriteCurrent)

                xbmc.log("EMBY.hooks.favorites: Kodi favorites changed", 1) # LOGINFO

                for Index, FavoritesChanged in enumerate((FavoritesRemoved, FavoritesAdded)):
                    isAdded = bool(Index)

                    for FavoriteChanged in FavoritesChanged:
                        EmbyType = ""
                        EmbyId = ""
                        ServerId = ""
                        ImageUrlFromDB = ""
                        KodiItemId = -1
                        KodiItemIdFromDB = ""
                        Path, isPath = get_path(FavoriteChanged)

                        if not Path:
                            xbmc.log("EMBY.hooks.favorites: Path not found: {FavoriteChanged}", 0) # LOGDEBUG
                            continue

                        # get metadata
                        if Path.startswith("videodb://tvshows/titles/"):
                            Temp = Path.split("/")

                            if Temp[5] and Temp[5] != -1:
                                videodb = dbio.DBOpenRO("video", "Favorites")
                                KodiItemId = videodb.get_seasonid_by_showid_number(Temp[4], Temp[5]) # Temp[4] = KodiTVShowId, Temp[5] = SeasonNumber
                                dbio.DBCloseRO("video", "Favorites")
                                EmbyType = "Season"
                            else:
                                KodiItemId = Temp[4]
                                EmbyType = "Series"
                        elif Path.startswith("videodb://movies/sets/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[4]
                            EmbyType = "BoxSet"
                        elif Path.startswith("videodb://movies/genres/") or Path.startswith("videodb://tvshows/genres/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[4]
                            EmbyType = "Genre"
                        elif Path.startswith("videodb://movies/tags/") or Path.startswith("videodb://tvshows/tags/") or Path.startswith("videodb://musicvideos/tags/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[4]
                            EmbyType = "Tag"
                        elif Path.startswith("videodb://movies/actors/") or Path.startswith("videodb://tvshows/actors/") or Path.startswith("videodb://musicvideos/actors/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[4]
                            EmbyType = "Person"
                        elif Path.startswith("videodb://movies/studios/") or Path.startswith("videodb://tvshows/studios/") or Path.startswith("videodb://musicvideos/studios/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[4]
                            EmbyType = "Studio"
                        elif Path.startswith("special://profile/playlists/mixed/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[5][:-4]
                            EmbyType = "Playlist"
                        elif Path.startswith("musicdb://genres/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[3]
                            EmbyType = "MusicGenre"
                        elif Path.startswith("videodb://musicvideos/genres/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[4]
                            EmbyType = "MusicGenre"
                        elif Path.startswith("musicdb://artists/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[3]
                            EmbyType = "MusicArtist"
                        elif Path.startswith("musicdb://albums/"):
                            Temp = Path.split("/")
                            KodiItemId = Temp[3]
                            EmbyType = "MusicAlbum"

                        if not isPath and KodiItemId == -1: # sub content need KodiItemId
                            xbmc.log("EMBY.hooks.favorites: KodiItemId not found: {FavoriteChanged}", 2) # LOGWARNING
                            continue

                        ValidImage = ""

                        # get ServerId by thumbnail's metadata
                        if FavoriteChanged.get("thumbnail", "").startswith("http://127.0.0.1:57342/"): # by picure url metadata
                            ValidImage = FavoriteChanged["thumbnail"]
                            FolderIds = ValidImage.split("/")

                            if len(FolderIds) >= 4:
                                ServerId = FolderIds[4]

                        # get additional metadata
                        if KodiItemId == -1:
                            if ValidImage:
                                MetaIds = ValidImage.split("-")

                                if len(MetaIds) >= 2:
                                    EmbyId = MetaIds[1] # get EmbyId by thumbnail's metadata

                                    if isAdded:
                                        embydb = dbio.DBOpenRO(ServerId, "Favorites change artwork (content)")
                                        EmbyType = embydb.get_contenttype_by_id(EmbyId)
                                        dbio.DBCloseRO(ServerId, "Favorites change artwork (content)")
                        else:
                            if ServerId in utils.EmbyServers:
                                embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata")
                                EmbyId, KodiItemIdFromDB, ImageUrlFromDB = embydb.get_EmbyId__KodiId_ImageUrl_by_KodiId_EmbyType(KodiItemId, EmbyType)
                                dbio.DBCloseRO(ServerId, "Favorites subcontent metadata")
                            else:
                                for ServerId in utils.EmbyServers:
                                    embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata")
                                    EmbyId, KodiItemIdFromDB, ImageUrlFromDB = embydb.get_EmbyId__KodiId_ImageUrl_by_KodiId_EmbyType(KodiItemId, EmbyType)
                                    dbio.DBCloseRO(ServerId, "Favorites subcontent metadata")

                                    if EmbyId:
                                        break

                        if not EmbyId:
                            xbmc.log("EMBY.hooks.favorites: EmbyId not found: {FavoriteChanged}", 0) # LOGDEBUG
                            continue

                        if isAdded:
                            delete_favorite(FavoriteChanged, FavoritesCurrent, None) # remove existing favorite record

                            # Update image overlay
                            if isPath:
                                if EmbyType == "MusicVideo":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Musicvideo", "Musicvideos", EmbyId, ServerId, FavoriteChanged["thumbnail"]), "path": FavoriteChanged["path"]})
                                elif EmbyType == "Episode":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Episode", "TV Shows", EmbyId, ServerId, FavoriteChanged["thumbnail"]), "path": FavoriteChanged["path"]})
                                elif EmbyType == "Movie":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Movie", "Movies", EmbyId, ServerId, FavoriteChanged["thumbnail"]), "path": FavoriteChanged["path"]})
                                elif EmbyType == "Video":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Video", "Movies", EmbyId, ServerId, FavoriteChanged["thumbnail"]), "path": FavoriteChanged["path"]})
                                elif EmbyType == "Audio":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Song", "Songs", EmbyId, ServerId, FavoriteChanged["thumbnail"]), "path": FavoriteChanged["path"]})
                                else:
                                    xbmc.log("EMBY.hooks.favorites: EmbyType not found: {FavoriteChanged}", 0) # LOGDEBUG
                                    continue
                            else: # add additional existing favorite records for linked sub-content
                                if ImageUrlFromDB:
                                    ImageUrlUpdated = ImageUrlFromDB
                                else:
                                    ImageUrlUpdated = FavoriteChanged["thumbnail"]

                                if EmbyType == "MusicGenre":
                                    MusicGenreByMusicVideo = Path.startswith("videodb://musicvideos/genres/")
                                    MusicGenreByAudio = Path.startswith("musicdb://genres/")

                                    # Update artwork for existing item
                                    if MusicGenreByMusicVideo:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Genre", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})
                                    elif MusicGenreByAudio:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Genre", "Songs", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                    # Add additional favorites for linked subcontent
                                    if KodiItemIdFromDB:
                                        KodiItemIdFromDB = KodiItemIdFromDB.split(";")

                                        if MusicGenreByMusicVideo:
                                            musicdb = dbio.DBOpenRO("music", "Favorites change musicgenre (subcontent)")
                                            _, hasSongs = musicdb.get_Genre_Name_hasSongs(KodiItemIdFromDB[1])
                                            dbio.DBCloseRO("music", "Favorites change musicgenre (subcontent)")

                                            if hasSongs:
                                                utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Genre", "Songs", EmbyId, ServerId, ImageUrlUpdated), True, f"musicdb://genres/{KodiItemIdFromDB[1]}/", FavoriteChanged["title"], "window", 10502),))
                                        else:
                                            videodb = dbio.DBOpenRO("video", "Favorites change musicgenre (subcontent)")
                                            _, hasMusicVideos, _, _ = videodb.get_Genre_Name_hasMusicVideos_hasMovies_hasTVShows(KodiItemIdFromDB[0])
                                            dbio.DBCloseRO("video", "Favorites change musicgenre (subcontent)")

                                            if hasMusicVideos:
                                                utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Genre", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://musicvideos/genres/{KodiItemIdFromDB[0]}/", FavoriteChanged["title"], "window", 10025),))
                                elif EmbyType == "Tag":
                                    videodb = dbio.DBOpenRO("video", "Favorites change tag (subcontent)")
                                    _, hasMusicVideos, hasMovies, hasTVShows = videodb.get_Tag_Name(KodiItemId)
                                    dbio.DBCloseRO("video", "Favorites change tag (subcontent)")
                                    TagByMovie = Path.startswith("videodb://movies/tags/")
                                    TagBySeries = Path.startswith("videodb://tvshows/tags/")

                                    if TagByMovie:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Tag", "Movie", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasTVShows:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Tag", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://tvshows/tags/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                        if hasMusicVideos:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Tag", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://musicvideos/tags/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                    elif TagBySeries:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Tag", "TV Show", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasMovies:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Tag", "Movies", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://movies/tags/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                        if hasMusicVideos:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Tag", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://musicvideos/tags/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                    else:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Tag", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasMovies:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Tag", "Movies", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://movies/tags/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                        if hasTVShows:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Tag", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://tvshows/tags/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                    # collections assigned to tags -> utils.BoxSetsToTags
                                    if str(EmbyId).startswith("999999993"):
                                        EmbySetId = str(EmbyId).replace("999999993", "")
                                        embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata tag")
                                        KodiItemId = embydb.get_KodiId_by_EmbyId_EmbyType(EmbySetId, "BoxSet")
                                        dbio.DBCloseRO(ServerId, "Favorites subcontent metadata tag")
                                        delete_favorite(None, FavoritesCurrent, f"videodb://movies/sets/{KodiItemId}/")
                                        utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Boxset", "Set", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://movies/sets/{KodiItemId}/", FavoriteChanged["title"].replace(" (Collection)", ""), "window", 10025),))
                                elif EmbyType == "BoxSet":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Boxset", "Set", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})
                                    embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata boxset")
                                    KodiItemId = embydb.get_KodiId_by_EmbyId_EmbyType(f"999999993{EmbyId}", "Tag")
                                    dbio.DBCloseRO(ServerId, "Favorites subcontent metadata boxset")
                                    videodb = dbio.DBOpenRO("video", "Favorites change boxset (subcontent)")
                                    _, hasMusicVideos, hasMovies, hasTVShows = videodb.get_Tag_Name(KodiItemId)
                                    dbio.DBCloseRO("video", "Favorites change boxset (subcontent)")

                                    if hasMovies:
                                        utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Tag", "Movies", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://movies/tags/{KodiItemId}/", f'{FavoriteChanged["title"]} (Collection)', "window", 10025),))

                                    if hasTVShows:
                                        utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Tag", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://tvshows/tags/{KodiItemId}/", f'{FavoriteChanged["title"]} (Collection)', "window", 10025),))

                                    if hasMusicVideos:
                                        utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Tag", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://musicvideos/tags/{KodiItemId}/", f'{FavoriteChanged["title"]} (Collection)', "window", 10025),))
                                elif EmbyType == "Studio":
                                    StudioByMovie = Path.startswith("videodb://movies/studios/")
                                    StudioByTVShow = Path.startswith("videodb://tvshows/studios/")
                                    videodb = dbio.DBOpenRO("video", "Favorites change studio (subcontent)")
                                    _, hasMusicVideos, hasMovies, hasTVShows = videodb.get_Studio_Name(KodiItemId)
                                    dbio.DBCloseRO("video", "Favorites change studio (subcontent)")

                                    if StudioByMovie:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Studio", "Movies", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasTVShows:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Studio", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://tvshows/studios/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                        if hasMusicVideos:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Studio", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://musicvideos/studios/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                    elif StudioByTVShow:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Studio", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasMovies:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Studio", "Movies", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://movies/studios/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                        if hasMusicVideos:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Studio", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://musicvideos/studios/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                    else:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Studio", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasMovies:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Studio", "Movies", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://movies/studios/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                        if hasTVShows:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Studio", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://tvshows/studios/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                elif EmbyType == "Person":
                                    PersonByMovie = Path.startswith("videodb://movies/actors/")
                                    PersonByTVShow = Path.startswith("videodb://tvshows/actors/")
                                    videodb = dbio.DBOpenRO("video", "Favorites change person (subcontent)")
                                    _, _, hasMusicVideos, hasMovies, hasTVShows = videodb.get_People(KodiItemId)
                                    dbio.DBCloseRO("video", "Favorites change person (subcontent)")

                                    if PersonByMovie:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Actor", "Movies", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasTVShows:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Actor", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://tvshows/actors/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                        if hasMusicVideos:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Artist", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://musicvideos/actors/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                    elif PersonByTVShow:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Actor", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasMovies:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Actor", "Movies", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://movies/actors/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                        if hasMusicVideos:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Artist", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://musicvideos/actors/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                    else:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Artist", "Musicvideos", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasMovies:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Actor", "Movies", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://movies/actors/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))

                                        if hasTVShows:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Actor", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://tvshows/actors/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                elif EmbyType == "Genre":
                                    GenreByMovie = Path.startswith("videodb://movies/genres/")
                                    videodb = dbio.DBOpenRO("video", "Favorites change genre (subcontent)")
                                    _, _, hasMovies, hasTVShows = videodb.get_Genre_Name_hasMusicVideos_hasMovies_hasTVShows(KodiItemId)
                                    dbio.DBCloseRO("video", "Favorites change genre (subcontent)")

                                    if GenreByMovie:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Genre", "Movies", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasTVShows:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Genre", "TV Shows", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://tvshows/genres/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                    else:
                                        send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Genre", "TV Show", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})

                                        if hasMovies:
                                            utils.FavoriteQueue.put(((common.set_Favorites_Artwork_Overlay("Genre", "Movies", EmbyId, ServerId, ImageUrlUpdated), True, f"videodb://movies/genres/{KodiItemId}/", FavoriteChanged["title"], "window", 10025),))
                                elif EmbyType == "Series":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Series", "TV Show", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})
                                elif EmbyType == "Season":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Season", "TV Show", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})
                                elif EmbyType == "MusicArtist":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Artist", "Songs", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})
                                elif EmbyType == "MusicAlbum":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Album", "Songs", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})
                                elif EmbyType == "Playlist":
                                    send_favorite({"type": FavoriteChanged["type"], "title": FavoriteChanged["title"] , "thumbnail": common.set_Favorites_Artwork_Overlay("Playlist", "Playlists", EmbyId, ServerId, ImageUrlUpdated), "windowparameter": FavoriteChanged["windowparameter"], "window": "videos"})
                        else: # favorite removed
                            if not isPath:
                                # remove additional existing favorite records for linked sub-content
                                if EmbyType == "MusicGenre":
                                    embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata MusicGenre")
                                    KodiIds = embydb.get_KodiId_by_EmbyId_EmbyType(EmbyId, "MusicGenre")
                                    dbio.DBCloseRO(ServerId, "Favorites subcontent metadata MusicGenre")

                                    if KodiIds:
                                        KodiIds = KodiIds.split(";")

                                        if KodiIds[1]:
                                            delete_favorite(None, FavoritesCurrent, f"musicdb://genres/{KodiIds[1]}/")

                                        if KodiIds[0]:
                                            delete_favorite(None, FavoritesCurrent, f"videodb://musicvideos/genres/{KodiIds[0]}/")
                                elif EmbyType == "Tag":
                                    delete_favorite(None, FavoritesCurrent, f"videodb://movies/tags/{KodiItemId}/")
                                    delete_favorite(None, FavoritesCurrent, f"videodb://musicvideos/tags/{KodiItemId}/")
                                    delete_favorite(None, FavoritesCurrent, f"videodb://tvshows/tags/{KodiItemId}/")

                                    # collections assigned to tags -> utils.BoxSetsToTags
                                    if str(EmbyId).startswith("999999993"):
                                        EmbySetId = str(EmbyId).replace("999999993", "")
                                        embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata set")
                                        KodiItemId = embydb.get_KodiId_by_EmbyId_EmbyType(EmbySetId, "BoxSet")
                                        dbio.DBCloseRO(ServerId, "Favorites subcontent metadata set")
                                        delete_favorite(None, FavoritesCurrent, f"videodb://movies/sets/{KodiItemId}/")
                                elif EmbyType == "BoxSet":
                                    # collections assigned to tags -> utils.BoxSetsToTags
                                    embydb = dbio.DBOpenRO(ServerId, "Favorites subcontent metadata set")
                                    KodiItemId = embydb.get_KodiId_by_EmbyId_EmbyType(f"999999993{EmbyId}", "Tag")
                                    dbio.DBCloseRO(ServerId, "Favorites subcontent metadata set")

                                    if KodiItemId:
                                        delete_favorite(None, FavoritesCurrent, f"videodb://movies/tags/{KodiItemId}/")
                                        delete_favorite(None, FavoritesCurrent, f"videodb://musicvideos/tags/{KodiItemId}/")
                                        delete_favorite(None, FavoritesCurrent, f"videodb://tvshows/tags/{KodiItemId}/")
                                elif EmbyType == "Studio":
                                    delete_favorite(None, FavoritesCurrent, f"videodb://movies/studios/{KodiItemId}/")
                                    delete_favorite(None, FavoritesCurrent, f"videodb://tvshows/studios/{KodiItemId}/")
                                    delete_favorite(None, FavoritesCurrent, f"videodb://musicvideos/studios/{KodiItemId}/")
                                elif EmbyType == "Person":
                                    delete_favorite(None, FavoritesCurrent, f"videodb://movies/actors/{KodiItemId}/")
                                    delete_favorite(None, FavoritesCurrent, f"videodb://tvshows/actors/{KodiItemId}/")
                                    delete_favorite(None, FavoritesCurrent, f"videodb://musicvideos/actors/{KodiItemId}/")
                                elif EmbyType == "Genre":
                                    delete_favorite(None, FavoritesCurrent, f"videodb://movies/genres/{KodiItemId}/")
                                    delete_favorite(None, FavoritesCurrent, f"videodb://tvshows/genres/{KodiItemId}/")

                        # Update Emby favorites
                        if EmbyId:
                            if str(EmbyId).startswith("999999993"): # skip collections assigned to tags -> utils.BoxSetsToTags
                                EmbyId = str(EmbyId).replace("999999993", "")

                            utils.ItemSkipUpdate.append(str(EmbyId))
                            xbmc.log(f"EMBY.hooks.favorites: ItemSkipUpdate favorite update: {utils.ItemSkipUpdate}", 0) # LOGDEBUG
                            utils.EmbyServers[ServerId].API.favorite(EmbyId, isAdded)

            FavoritesCached = get_Favorites()

def get_Favorites():
    Result = utils.SendJson('{"jsonrpc":"2.0", "method":"Favourites.GetFavourites", "params":{"properties":["windowparameter", "path", "thumbnail", "window"]}, "id": 1}').get("result", {})

    if Result:
        Favorites = Result.get("favourites", [])

        if Favorites: # Favorites can be "None"
            FavoriteData = {"Favorites": Favorites, "Path": len(Favorites) * [""], "Filtered": len(Favorites) * [""], "Title": len(Favorites) * [""], "ImageUrl": len(Favorites) * [""]}

            for Index, Favorite in enumerate(Favorites):
                if 'path' in Favorite:
                    FavoriteData["Path"][Index] = Favorite['path']
                    FavoriteData["Filtered"][Index] = filter_path(Favorite['path'])
                elif 'windowparameter' in Favorite:
                    FavoriteData["Path"][Index] = Favorite['windowparameter']
                    FavoriteData["Filtered"][Index] = filter_path(Favorite['windowparameter'])

                FavoriteData["Title"][Index] = Favorite.get('title', "")
                FavoriteData["ImageUrl"][Index] = Favorite.get('thumbnail', "")

            return FavoriteData

    return {"Favorites": [], "Path": [], "Filtered": [], "Title": [], "ImageUrl": []}

def filter_path(Path):
    PathPos = Path.find("?")

    if PathPos != -1:
        Path = Path[:PathPos]

    return Path

def get_path(Favorite):
    if Favorite:
        if "windowparameter" in Favorite:
            return Favorite["windowparameter"], False

        if "path" in Favorite:
            return Favorite["path"], True

    return "", False

def delete_favorite(Favorite, Favorites, PathCheck):
    _, _, FoundIndex, isValid = get_existing_favorite(Favorite, Favorites, PathCheck)

    if isValid and FoundIndex != -1:
        send_favorite(Favorites["Favorites"][FoundIndex])
        del Favorites["Favorites"][FoundIndex]
        del Favorites["Path"][FoundIndex]
        del Favorites["Filtered"][FoundIndex]
        del Favorites["Title"][FoundIndex]
        del Favorites["ImageUrl"][FoundIndex]

def get_existing_favorite(Favorite, Favorites, PathCheck):
    Path = ""
    FoundInPath = False
    FoundInPathFiltered = False
    PathIndex = -1

    if PathCheck:
        Path = PathCheck
    else:
        Path, _ = get_path(Favorite)

    if Path:
        PathFiltered = filter_path(Path)

        if Path in Favorites["Path"]:
            FoundInPath = True
            PathIndex = Favorites["Path"].index(Path)
        elif PathFiltered in Favorites["Filtered"]:
            FoundInPathFiltered = True
            PathIndex = Favorites["Filtered"].index(PathFiltered)

    return FoundInPath, FoundInPathFiltered, PathIndex, bool(Path)

def update_favorite(Favorite, Path, ImageUrl):
    FavoriteUpdated = Favorite.copy()

    if ImageUrl:
        FavoriteUpdated["thumbnail"] = ImageUrl

    if 'path' in Favorite:
        FavoriteUpdated["path"] = Path
    else:
        FavoriteUpdated["windowparameter"] = Path

    return FavoriteUpdated

def send_favorite(Favorite):
    globals()['FavoriteUpdatedByEmby'] = True

    if 'path' in Favorite:
        utils.SendJson(f'{{"jsonrpc":"2.0", "method":"Favourites.AddFavourite", "params":{{"type":"{Favorite["type"]}", "title":"{Favorite["title"]}", "thumbnail":"{Favorite["thumbnail"]}", "path":"{Favorite["path"]}"}}, "id": 1}}')
    else:
        utils.SendJson(f'{{"jsonrpc":"2.0", "method":"Favourites.AddFavourite", "params":{{"type":"{Favorite["type"]}", "title":"{Favorite["title"]}", "thumbnail":"{Favorite["thumbnail"]}", "windowparameter":"{Favorite["windowparameter"]}", "window":"{Favorite["window"]}"}}, "id": 1}}')

def set_Favorite_Emby_Media(Path, isFavorite):
    if Path.startswith("http://127.0.0.1:57342/") or Path.startswith("/emby_addon_mode/"):
        Path = Path.replace("http://127.0.0.1:57342/", "").replace("/emby_addon_mode/", "")
        ServerId = Path.split("/")[1]
        EmbyId = Path[Path.rfind("/"):].split("-")[1]
        utils.ItemSkipUpdate.append(str(EmbyId))
        xbmc.log(f"EMBY.hooks.favorites: ItemSkipUpdate: {utils.ItemSkipUpdate}", 0) # LOGDEBUG
        utils.EmbyServers[ServerId].API.favorite(EmbyId, isFavorite)

def emby_change_Favorite(): # Threaded / queued
    xbmc.log("EMBY.hooks.favorites: THREAD: --->[ Kodi favorites mods ]", 0) # LOGDEBUG

    FavoritesCurrent = get_Favorites()
    FavoriteTimestamp = 0

    while True:
        Favorites = utils.FavoriteQueue.getall()

        if Favorites == ("QUIT",):
            xbmc.log("EMBY.hooks.favorites: THREAD: ---<[ Kodi favorites mods ]", 0) # LOGDEBUG
            return

        if not utils.SyncFavorites:
            continue

        Stats = xbmcvfs.Stat(utils.KodiFavFile)
        TimestampReadOut = Stats.st_mtime()

        # Check if favorite.xml file has changed (by timestamp)
        if FavoriteTimestamp < TimestampReadOut:
            FavoriteTimestamp = TimestampReadOut
            FavoritesCurrent = get_Favorites()

        for Favorite in Favorites: # Favorite = (ImageUrl, IsFavorite, FullPath, Title, "media", WindowId)
            FoundInPath, FoundInPathFiltered, FoundIndex, isValid = get_existing_favorite(None, FavoritesCurrent, Favorite[2])

            if not isValid:
                xbmc.log(f"EMBY.hooks.favorites: Invalid item: {Favorite}", 0) # LOGDEBUG
                continue

            if Favorite[1]:
                if not FoundInPath and not FoundInPathFiltered: # is favorite and doesn't exist
                    if Favorite[4] == "media":
                        FavoriteNew = {"type": Favorite[4], "title": Favorite[3] , "thumbnail": Favorite[0], "path": Favorite[2]}
                    else:
                        FavoriteNew = {"type": Favorite[4], "title": Favorite[3] , "thumbnail": Favorite[0], "windowparameter": Favorite[2], "window": Favorite[5]}

                    send_favorite(FavoriteNew)
                else: # if favorite exists but title or artwork has changed
                    if FavoritesCurrent["Favorites"][FoundIndex]["title"] != Favorite[3] or FavoritesCurrent["Favorites"][FoundIndex]["thumbnail"] != Favorite[1]:
                        send_favorite(FavoritesCurrent["Favorites"][FoundIndex]) # remove existing favorite record

                        if Favorite[4] == "media":
                            FavoriteNew = {"type": FavoritesCurrent["Favorites"][FoundIndex]['type'], "title": Favorite[3] , "thumbnail": Favorite[0], "path": FavoritesCurrent["Favorites"][FoundIndex]['path']}
                        else:
                            FavoriteNew = {"type": FavoritesCurrent["Favorites"][FoundIndex]['type'], "title": Favorite[3] , "thumbnail": Favorite[0], "windowparameter": FavoritesCurrent["Favorites"][FoundIndex]['windowparameter'], "window": FavoritesCurrent["Favorites"][FoundIndex]['window']}

                        send_favorite(FavoriteNew)
            else:
                if FoundInPath or FoundInPathFiltered: # is not favorite and exist
                    send_favorite(FavoritesCurrent["Favorites"][FoundIndex]) # remove existing favorite record
