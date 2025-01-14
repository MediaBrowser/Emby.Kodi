from urllib.parse import quote, unquote
import xbmc
from helper import utils
from . import common_db

class VideoDatabase:
    def __init__(self, cursor):
        self.cursor = cursor
        self.common_db = common_db.CommonDatabase(cursor)

    def add_Index(self):
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_strFilename on files (strFilename)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_dateAdded on files (dateAdded)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_lastPlayed on files (lastPlayed)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_playCount on files (playCount)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookmark_type on bookmark (type)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookmark_timeInSeconds on bookmark (timeInSeconds)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating_rating on rating (rating)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_episode_c12 on episode (c12)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_episode_idShow_idFile_c12 on episode (idShow, idFile, c12)")

    def delete_Index(self):
        self.cursor.execute("DROP INDEX IF EXISTS idx_files_strFilename")
        self.cursor.execute("DROP INDEX IF EXISTS idx_files_dateAdded")
        self.cursor.execute("DROP INDEX IF EXISTS idx_files_lastPlayed")
        self.cursor.execute("DROP INDEX IF EXISTS idx_files_playCount")
        self.cursor.execute("DROP INDEX IF EXISTS idx_bookmark_type")
        self.cursor.execute("DROP INDEX IF EXISTS idx_bookmark_timeInSeconds")
        self.cursor.execute("DROP INDEX IF EXISTS idx_rating_rating")
        self.cursor.execute("DROP INDEX IF EXISTS idx_episode_c12")
        self.cursor.execute("DROP INDEX IF EXISTS idx_episode_idShow_idFile_c12")

    # playcount
    def get_playcount(self, KodiItemId, ContentType):
        if ContentType == "movie":
            self.cursor.execute("SELECT idFile FROM movie WHERE idMovie = ?", (KodiItemId,))
        elif ContentType == "musicvideo":
            self.cursor.execute("SELECT idFile FROM musicvideo WHERE idMVideo = ?", (KodiItemId,))
        elif ContentType == "episode":
            self.cursor.execute("SELECT idFile FROM episode WHERE idEpisode = ?", (KodiItemId,))
        else:
            return 0

        KodiFileId = self.cursor.fetchone()

        if KodiFileId:
            self.cursor.execute("SELECT playCount FROM files WHERE idFile = ?", (KodiFileId[0],))
            KodiPlayCount = self.cursor.fetchone()

            if KodiPlayCount and KodiPlayCount[0]:
                return KodiPlayCount[0]

        return 0

    # Favorite for content
    def get_favoriteData(self, KodiFileId, KodiItemId, ContentType):
        Image = ""

        if ContentType == "set":
            self.cursor.execute("SELECT strSet FROM sets WHERE idSet = ?", (KodiItemId,))
            DataSet = self.cursor.fetchone()

            if DataSet:
                for ImageId in ("poster", "thumb"):
                    self.cursor.execute("SELECT url FROM art WHERE media_id = ? AND media_type = ? AND type = ?", (KodiItemId, "set", ImageId))
                    ArtworkData = self.cursor.fetchone()

                    if ArtworkData:
                        Image = ArtworkData[0]
                        break

                return "", Image, DataSet[0]

            return "", "", ""

        self.cursor.execute("SELECT idPath, strFilename FROM files WHERE idFile = ?", (KodiFileId,))
        DataFile = self.cursor.fetchone()

        if DataFile:
            self.cursor.execute("SELECT strPath FROM path WHERE idPath = ?", (DataFile[0],))
            DataPath = self.cursor.fetchone()

            if DataPath:
                if ContentType == "movie":
                    self.cursor.execute("SELECT c00 FROM movie WHERE idMovie = ?", (KodiItemId,))
                elif ContentType == "musicvideo":
                    self.cursor.execute("SELECT c00 FROM musicvideo WHERE idMVideo = ?", (KodiItemId,))
                elif ContentType == "episode":
                    self.cursor.execute("SELECT c00 FROM episode WHERE idEpisode = ?", (KodiItemId,))
                else:
                    return "", "", ""

                ItemData = self.cursor.fetchone()

                if ItemData:
                    for ImageId in ("poster", "thumb"):
                        self.cursor.execute("SELECT url FROM art WHERE media_id = ? AND media_type = ? AND type = ?", (KodiItemId, ContentType, ImageId))
                        ArtworkData = self.cursor.fetchone()

                        if ArtworkData:
                            Image = ArtworkData[0]
                            break

                    return f"{DataPath[0]}{DataFile[1]}", Image, ItemData[0]

        return "", "", ""

    # Favorite for subcontent
    def get_FavoriteSubcontent(self, KodiItemId, ContentType):
        Image = ""

        if ContentType == "tvshow":
            self.cursor.execute("SELECT c00 FROM tvshow WHERE idShow = ?", (KodiItemId,))
        else:
            self.cursor.execute("SELECT name, season, idShow FROM seasons WHERE idSeason = ?", (KodiItemId,))

        ItemData = self.cursor.fetchone()

        if ItemData:
            Name = ItemData[0]

            if ContentType == "season":
                self.cursor.execute("SELECT c00 FROM tvshow WHERE idShow = ?", (ItemData[2],))
                TVShowData = self.cursor.fetchone()

                if TVShowData:
                    Name = f"{TVShowData[0]} - {Name}"

            for ImageId in ("poster", "thumb"):
                self.cursor.execute("SELECT url FROM art WHERE media_id = ? AND media_type = ? AND type = ?", (KodiItemId, ContentType, ImageId))
                ArtworkData = self.cursor.fetchone()

                if ArtworkData:
                    Image = ArtworkData[0]
                    break

            if ContentType == "tvshow":
                return Image, Name, -1

            return Image, Name, ItemData[1]

        return "", "", -1

    # movies
    def get_movie_doubles(self):
        Data = {}
        self.cursor.execute("SELECT c00, premiered FROM movie GROUP BY c00, premiered HAVING COUNT(c00) > 1")
        Doubles = self.cursor.fetchall()

        for Double in Doubles:
            self.cursor.execute("SELECT idMovie FROM movie WHERE c00 = ? AND premiered IS ?" , (Double[0], Double[1]))
            KodiIds = self.cursor.fetchall()

            if KodiIds:
                Data[f"MOVIE_BY_NAME(m)_DATE(o)/{Double[0]}/{Double[1]}"] = [{}, {}]

                for KodiId in KodiIds:
                    Data[f"MOVIE_BY_NAME(m)_DATE(o)/{Double[0]}/{Double[1]}"][0].update({KodiId[0]: {"EmbyServerId": "", "EmbyLibraryIds": "", "EmbyId": ""}})

        return Data

    def add_movie(self, KodiItemId, KodiFileId, Name, Overview, ShortOverview, Tagline, RatingId, Writers, Poster, Unique, SortName, RunTimeTicks, OfficialRating, Genre, Directors, OriginalTitle, Studio, Trailer, KodiFanart, ProductionLocation, Path, KodiPathId, PremiereDate, Filename, DateCreated, PlayCount, LastPlayedDate, idSet, KodiStackedFilename, VersionName):
        self.cursor.execute("INSERT INTO movie (idMovie, idFile, c00, c01, c02, c03, c05, c06, c08, c09, c10, c11, c12, c14, c15, c16, c18, c19, c20, c21, c22, c23, premiered, idSet) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (KodiItemId, KodiFileId, Name, Overview, ShortOverview, Tagline, RatingId, Writers, Poster, Unique, SortName, RunTimeTicks, OfficialRating, Genre, Directors, OriginalTitle, Studio, Trailer, KodiFanart, ProductionLocation, Path, KodiPathId, PremiereDate, idSet))
        self.add_file(KodiPathId, Filename, DateCreated, KodiFileId, PlayCount, LastPlayedDate, KodiStackedFilename)
        VideoVersionTypeId = self.get_add_videoversiontype(VersionName)
        self.cursor.execute("INSERT OR REPLACE INTO videoversion(idFile, idMedia, media_type, itemType, idType) VALUES (?, ?, ?, ?, ?)", (KodiFileId, KodiItemId, "movie", 0, VideoVersionTypeId))

    def add_movie_version(self, KodiItemId, KodiFileId, KodiPathId, Filename, DateCreated, PlayCount, LastPlayedDate, KodiStackedFilename, VersionName, KodiType, itemType):
        self.add_file(KodiPathId, Filename, DateCreated, KodiFileId, PlayCount, LastPlayedDate, KodiStackedFilename)
        VideoVersionTypeId = self.get_add_videoversiontype(VersionName)
        self.cursor.execute("INSERT OR REPLACE INTO videoversion(idFile, idMedia, media_type, itemType, idType) VALUES (?, ?, ?, ?, ?)", (KodiFileId, KodiItemId, KodiType, itemType, VideoVersionTypeId))

    def update_movie(self, KodiItemId, KodiFileId, Name, Overview, ShortOverview, Tagline, RatingId, Writers, Poster, Unique, SortName, RunTimeTicks, OfficialRating, Genre, Directors, OriginalTitle, Studio, Trailer, KodiFanart, ProductionLocation, PremiereDate, PlayCount, LastPlayedDate, idSet, FileFilename, KodiStackedFilename, DateCreated, VersionName, KodiPathId, KodiPath):
        self.cursor.execute("UPDATE movie SET c00 = ?, c01 = ?, c02 = ?, c03 = ?, c05 = ?, c06 = ?, c08 = ?, c09 = ?, c10 = ?, c11 = ?, c12 = ?, c14 = ?, c15 = ?, c16 = ?, c18 = ?, c19 = ?, c20 = ?, c21 = ?, premiered = ?, idSet = ? WHERE idMovie = ?", (Name, Overview, ShortOverview, Tagline, RatingId, Writers, Poster, Unique, SortName, RunTimeTicks, OfficialRating, Genre, Directors, OriginalTitle, Studio, Trailer, KodiFanart, ProductionLocation, PremiereDate, idSet, KodiItemId))
        self.update_file(KodiFileId, PlayCount, LastPlayedDate, DateCreated, FileFilename, KodiStackedFilename)
        self.cursor.execute("DELETE FROM movielinktvshow WHERE idMovie = ?", (KodiItemId,))
        self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (KodiPath, KodiPathId))

        # update videoversions
        VideoVersionTypeId = self.get_add_videoversiontype(VersionName)
        self.cursor.execute("INSERT OR REPLACE INTO videoversion(idFile, idMedia, media_type, itemType, idType) VALUES (?, ?, ?, ?, ?)", (KodiFileId, KodiItemId, "movie", 0, VideoVersionTypeId))

    def update_default_movieversion(self, KodiItemId, KodiFileId, KodiPathId, KodiPath):
        self.cursor.execute("UPDATE movie SET idFile = ?, c23 = ?, c22 = ? WHERE idMovie = ?", (KodiFileId, KodiPathId, KodiPath, KodiItemId))

    def create_movie_entry(self):
        self.cursor.execute("SELECT coalesce(max(idMovie), 0) FROM movie")
        return self.cursor.fetchone()[0] + 1

    def delete_movie(self, KodiItemId, KodiFileId, KodiPathId):
        self.cursor.execute("DELETE FROM movie WHERE idMovie = ?", (KodiItemId,))
        self.cursor.execute("DELETE FROM files WHERE idFile = ?", (KodiFileId,))
        self.cursor.execute("DELETE FROM movielinktvshow WHERE idMovie = ?", (KodiItemId,))
        self.cursor.execute("DELETE FROM videoversion WHERE idFile = ?", (KodiFileId,))

#        if KodiPathId:
#            self.cursor.execute("DELETE FROM path WHERE idPath = ?", (KodiPathId,))

    def get_movie_metadata_for_listitem(self, KodiItemId, PathAndFilename):
        self.cursor.execute("SELECT * FROM movie_view WHERE idMovie = ?", (KodiItemId,))
        ItemData = self.cursor.fetchone()

        if not ItemData:
            return {}

        Path = ItemData[32].replace("|redirect-limit=1000", "")

        if not PathAndFilename:
            PathAndFilename = f"{Path}{ItemData[31]}"

        Artwork = self.get_artwork(KodiItemId, "movie", "")
        People = self.get_people_artwork(KodiItemId, "movie")
        return {'mediatype': "movie", "dbid": KodiItemId, 'title': ItemData[2], 'Overview': ItemData[3], 'ShortOverview': ItemData[4], 'Tagline': ItemData[5], 'Writer': ItemData[8], 'SortName': ItemData[12], 'duration': ItemData[13], 'OfficialRating': ItemData[14], 'genre': ItemData[16], 'Director': ItemData[17], 'OriginalTitle': ItemData[18], 'StudioName': ItemData[20], 'ProductionLocation': ItemData[23], 'CriticRating': ItemData[27], 'KodiPremiereDate': ItemData[28], 'playcount': ItemData[33], 'lastplayed': ItemData[34], 'KodiDateCreated': ItemData[35], 'CommunityRating': ItemData[39], 'trailer': ItemData[20], 'path': Path, 'pathandfilename': PathAndFilename, 'properties': {'IsFolder': 'false', 'IsPlayable': 'true'}, 'people': People, 'artwork': Artwork, 'KodiRunTimeTicks': ItemData[37], 'KodiPlaybackPositionTicks': ItemData[36]}

    # musicvideo
    def get_musicvideos_doubles(self):
        Data = {}
        self.cursor.execute("SELECT c00, premiered, c10, c09, c12 FROM musicvideo GROUP BY c00, premiered, c10, c09, c12 HAVING COUNT(c00) > 1")
        Doubles = self.cursor.fetchall()

        for Double in Doubles:
            self.cursor.execute("SELECT idMVideo FROM musicvideo WHERE c00 = ? AND premiered IS ? AND c10 = ? AND c09 IS ? AND c12 IS ?" , (Double[0], Double[1], Double[2], Double[3], Double[4]))
            KodiIds = self.cursor.fetchall()

            if KodiIds:
                Data[f"MUSICVIDEO_BY_NAME(m)_DATE(o)_ARTIST(m)_ALBUM(o)_TRACK(o)/{Double[0]}/{Double[1]}/{Double[2]}/{Double[3]}/{Double[4]}"] = [{}, {}]

                for KodiId in KodiIds:
                    Data[f"MUSICVIDEO_BY_NAME(m)_DATE(o)_ARTIST(m)_ALBUM(o)_TRACK(o)/{Double[0]}/{Double[1]}/{Double[2]}/{Double[3]}/{Double[4]}"][0].update({KodiId[0]: {"EmbyServerId": "", "EmbyLibraryIds": "", "EmbyId": ""}})

        return Data

    def add_musicvideos(self, KodiItemId, KodiFileId, Name, Poster, RunTimeTicks, Directors, Studio, Overview, Album, Artist, Genre, IndexNumber, FilePath, KodiPathId, PremiereDate, DateCreated, PlayCount, LastPlayedDate, Filename, KodiStackedFilename):
        self.cursor.execute("INSERT INTO musicvideo (idMVideo, idFile, c00, c01, c04, c05, c06, c08, c09, c10, c11, c12, c13, c14, premiered) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (KodiItemId, KodiFileId, Name, Poster, RunTimeTicks, Directors, Studio, Overview, Album, Artist, Genre, IndexNumber, FilePath, KodiPathId, PremiereDate))
        self.add_file(KodiPathId, Filename, DateCreated, KodiFileId, PlayCount, LastPlayedDate, KodiStackedFilename)

    def update_musicvideos(self, KodiItemId, KodiFileId, Name, Poster, RunTimeTicks, Directors, Studio, Overview, Album, Artist, Genre, IndexNumber, PremiereDate, PlayCount, LastPlayedDate, FileFilename, KodiStackedFilename, DateCreated, KodiPathId, KodiPath):
        self.cursor.execute("UPDATE musicvideo SET c00 = ?, c01 = ?, c04 = ?, c05 = ?, c06 = ?, c08 = ?, c09 = ?, c10 = ?, c11 = ?, c12 = ?, premiered = ? WHERE idMVideo = ?", (Name, Poster, RunTimeTicks, Directors, Studio, Overview, Album, Artist, Genre, IndexNumber, PremiereDate, KodiItemId))
        self.update_file(KodiFileId, PlayCount, LastPlayedDate, DateCreated, FileFilename, KodiStackedFilename)
        self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (KodiPath, KodiPathId))

    def create_entry_musicvideos(self):
        self.cursor.execute("SELECT coalesce(max(idMVideo), 0) FROM musicvideo")
        return self.cursor.fetchone()[0] + 1

    def delete_musicvideos(self, KodiItemId, KodiFileId, KodiPathId):
        self.cursor.execute("DELETE FROM musicvideo WHERE idMVideo = ?", (KodiItemId,))
        self.cursor.execute("DELETE FROM files WHERE idFile = ?", (KodiFileId,))

#        if KodiPathId:
#            self.cursor.execute("DELETE FROM path WHERE idPath = ?", (KodiPathId,))

    def get_musicvideos_metadata_for_listitem(self, KodiItemId, PathAndFilename):
        self.cursor.execute("SELECT * FROM musicvideo_view WHERE idMVideo = ?", (KodiItemId,))
        ItemData = self.cursor.fetchone()

        if not ItemData:
            return {}

        Path = ItemData[29].replace("|redirect-limit=1000", "")

        if not PathAndFilename:
            PathAndFilename = f"{Path}{ItemData[28]}"

        Artwork = self.get_artwork(KodiItemId, "musicvideo", "")
        People = self.get_people_artwork(KodiItemId, "musicvideo")
        return {'mediatype': "musicvideo", "dbid": KodiItemId, 'title': ItemData[2], 'duration': ItemData[6], 'Director': ItemData[7], 'StudioName': ItemData[8], 'Overview': ItemData[10], 'Album': ItemData[11], 'genre': ItemData[13], 'track': ItemData[14], 'KodiPremiereDate': ItemData[27], 'playcount': ItemData[30], 'lastplayed': ItemData[31], 'path': Path, 'pathandfilename': PathAndFilename, 'properties': {'IsFolder': 'false', 'IsPlayable': 'true'}, 'people': People, 'artwork': Artwork, 'KodiRunTimeTicks': ItemData[34], 'KodiPlaybackPositionTicks': ItemData[33]}

    # tvshow
    def get_tvshow_doubles(self):
        Data = {}
        self.cursor.execute("SELECT c00, c05 FROM tvshow GROUP BY c00, c05 HAVING COUNT(c00) > 1")
        Doubles = self.cursor.fetchall()

        for Double in Doubles:
            self.cursor.execute("SELECT idShow FROM tvshow WHERE c00 = ? AND c05 IS ?", (Double[0], Double[1]))
            KodiIds = self.cursor.fetchall()

            if KodiIds:
                Data[f"SERIES_BY_NAME(m)_DATE(o)/{Double[0]}/{Double[1]}"] = [{}, {}]

                for KodiId in KodiIds:
                    Data[f"SERIES_BY_NAME(m)_DATE(o)/{Double[0]}/{Double[1]}"][0].update({KodiId[0]: {"EmbyServerId": "", "EmbyLibraryIds": "", "EmbyId": ""}})

        return Data

    def update_tvshow(self, TVShowName, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, TVShowSortName, duration, KodiShowId, Trailer, KodiPathId, KodiPath):
        self.cursor.execute("SELECT c00 FROM tvshow WHERE idShow = ?", (KodiShowId,))
        Data = self.cursor.fetchone()

        if Data and Data[0].endswith(" (download)"):
            TVShowNameMod = f"{TVShowName} (download)"
            TVShowSortNameMod = f"{TVShowSortName} (download)"
        else:
            TVShowNameMod = TVShowName
            TVShowSortNameMod = TVShowSortName

        self.cursor.execute("UPDATE tvshow SET c00 = ?, c01 = ?, c02 = ?, c04 = ?, c05 = ?, c06 = ?, c08 = ?, c09 = ?, c11 = ?, c12 = ?, c13 = ?, c14 = ?, c15 = ?, duration = ?, c16 = ? WHERE idShow = ?", (TVShowNameMod, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, TVShowSortNameMod, duration, Trailer, KodiShowId))
        self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (KodiPath, KodiPathId))

    def add_tvshow(self, KodiShowId, c00, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, c15, duration, Trailer):
        self.cursor.execute("INSERT INTO tvshow(idShow, c00, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, c15, duration, c16) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (KodiShowId, c00, c01, c02, c04, c05, c06, c08, c09, c11, c12, c13, c14, c15, duration, Trailer))

    def create_entry_tvshow(self):
        self.cursor.execute("SELECT coalesce(max(idShow), 0) FROM tvshow")
        return self.cursor.fetchone()[0] + 1

    def delete_tvshow(self, KodiShowId, KodiPathId):
        SubcontentKodiIds = ()
        self.common_db.delete_artwork(KodiShowId, "tvshow")
        self.delete_links_tags(KodiShowId, "tvshow", None)
        self.cursor.execute("SELECT idSeason FROM seasons WHERE idShow = ?", (KodiShowId,))
        SeasonsData = self.cursor.fetchall()

        for SeasonData in SeasonsData:
            SubcontentKodiIds += ((SeasonData[0], "Season"),)
            SubcontentKodiIds += self.delete_season(SeasonData[0])

        self.cursor.execute("DELETE FROM tvshow WHERE idShow = ?", (KodiShowId,))
        self.cursor.execute("DELETE FROM movielinktvshow WHERE idShow = ?", (KodiShowId,))
        self.cursor.execute("DELETE FROM path WHERE idPath = ?", (KodiPathId,))
        return SubcontentKodiIds

    def add_link_tvshow(self, KodiShowId, idPath):
        self.cursor.execute("INSERT OR REPLACE INTO tvshowlinkpath(idShow, idPath) VALUES (?, ?)", (KodiShowId, idPath))

    def delete_link_tvshow(self, KodiShowId):
        self.cursor.execute("DELETE FROM tvshowlinkpath WHERE idShow = ?", (KodiShowId,))

    def get_inprogress_mixedIds(self):
        self.cursor.execute("SELECT idFile FROM bookmark WHERE type = ?", (1,))
        KodiFileIds = self.cursor.fetchall()
        InProgressInfos = ()

        for KodiFileId in KodiFileIds:
            self.cursor.execute("SELECT lastPlayed, idMovie FROM movie_view WHERE idFile = ?", (KodiFileId[0],))
            MovieData = self.cursor.fetchone()

            if MovieData:
                if not MovieData[0]:
                    InProgressInfos += (f"0000;{MovieData[1]};Movie",)
                else:
                    InProgressInfos += (f"{MovieData[0]};{MovieData[1]};Movie",)
            else:
                self.cursor.execute("SELECT lastPlayed, idEpisode FROM episode_view WHERE idFile = ?", (KodiFileId[0],))
                EpisodeData = self.cursor.fetchone()

                if EpisodeData:
                    if not EpisodeData[0]:
                        InProgressInfos += (f"0000;{EpisodeData[1]};Episode",)
                    else:
                        InProgressInfos += (f"{EpisodeData[0]};{EpisodeData[1]};Episode",)
                else:
                    self.cursor.execute("SELECT lastPlayed, idMVideo FROM musicvideo_view WHERE idFile = ?", (KodiFileId[0],))
                    MusicVideoData = self.cursor.fetchone()

                    if MusicVideoData:
                        if not MusicVideoData[0]:
                            InProgressInfos += (f"0000;{MusicVideoData[1]};MusicVideo",)
                        else:
                            InProgressInfos += (f"{MusicVideoData[0]};{MusicVideoData[1]};MusicVideo",)

        InProgressInfos = sorted(InProgressInfos, reverse=True)
        return InProgressInfos

    def get_next_episodesIds(self, TagName):
        if TagName != "unknown":
            self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (TagName,))
            TagId = self.cursor.fetchone()

            if TagId:
                TagId = TagId[0]
            else:
                return ()

            self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE tag_id = ? AND media_type = ?", (TagId, "tvshow"))
        else:
            self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE media_type = ?", ("tvshow",))

        KodiShowIds = self.cursor.fetchall()
        NextEpisodeInfos = ()

        for KodiShowId in KodiShowIds:
            self.cursor.execute("SELECT idEpisode, idFile, c12, playCount, lastPlayed FROM episode_view WHERE idShow = ? ORDER BY CAST(c12 AS INT) ASC, CAST(c13 AS INT) ASC", (KodiShowId[0],))
            Episodes = self.cursor.fetchall()
            LastPlayedDate = "0000"
            PlayedFound = False
            NextEpisodeId = "-1"

            for Episode in Episodes:
                if Episode[4] and Episode[4] > LastPlayedDate: # find highest PlayedDate
                    LastPlayedDate = str(Episode[4])

                if Episode[2] == "0": # Skip special seasons
                    continue

                if Episode[3]: # Playcount
                    PlayedFound = True
                else:
                    if PlayedFound: # get episode Id from the next (not played) episode
                        NextEpisodeId = Episode[0]
                        PlayedFound = False

            if NextEpisodeId != "-1":
                NextEpisodeInfos += (f"{LastPlayedDate};{NextEpisodeId};Episode",)

        NextEpisodeInfos = sorted(NextEpisodeInfos, reverse=True) # reverse sort by date
        return NextEpisodeInfos

    def get_last_played_next_episodesIds(self, TagName):
        if TagName != "unknown":
            self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (TagName,))
            TagId = self.cursor.fetchone()

            if TagId:
                TagId = TagId[0]
            else:
                return ()

            self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE tag_id = ? AND media_type = ?", (TagId, "tvshow"))
        else:
            self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE media_type = ?", ("tvshow",))

        KodiShowIds = self.cursor.fetchall()
        NextEpisodeInfos = ()

        for KodiShowId in KodiShowIds:
            self.cursor.execute("SELECT idEpisode, c12, c13, lastPlayed, resumeTimeInSeconds, c15, c16 FROM episode_view WHERE idShow = ? AND lastPlayed IS NOT NULL and COALESCE(c15,c12) is not '0' AND (playCount > 0 or resumeTimeInSeconds IS NOT NULL) ORDER BY lastPlayed DESC, CAST(COALESCE(c15,c12) AS INT) DESC, CAST(COALESCE(c16,c13) AS INT) DESC, CAST(c12 as INT) ASC, idEpisode ASC LIMIT 1", (KodiShowId[0],))
            Episode = self.cursor.fetchone()

            if Episode:
                LastPlayedDate = str(Episode[3])

                if Episode[4]:
                    NextEpisodeId = Episode[0]
                    NextEpisodeInfos += (f"{LastPlayedDate};{NextEpisodeId};Episode",)
                else:
                    if Episode[5]: # It was a special inserted into the season
                        # Search for more specials at the same point
                        self.cursor.execute("SELECT idEpisode FROM episode_view WHERE idShow = ? AND CAST(c15 AS INT) = ? AND CAST(c16 AS INT) = ? and idEpisode > ? ORDER BY idEpisode ASC LIMIT 1", (KodiShowId[0], Episode[5], Episode[6], Episode[0]))
                        nextEpisode = self.cursor.fetchone()

                        if not nextEpisode:
                            # No more specials, get the regular episode
                            self.cursor.execute("SELECT idEpisode FROM episode_view WHERE idShow = ? AND ((CAST(c12 AS INT) = ? AND CAST(c13 AS INT) >= ?) OR (CAST(c12 AS INT) > ?)) ORDER BY CAST(c12 AS INT) ASC, CAST(c13 AS INT) ASC LIMIT 1", (KodiShowId[0], Episode[5], Episode[6], Episode[5]))
                            nextEpisode = self.cursor.fetchone()
                    else: # It was a regular episode, get the next special or regular episode after it
                        self.cursor.execute("SELECT idEpisode FROM episode_view WHERE idShow = ? AND ((CAST(COALESCE(c15,c12) AS INT) = ? AND CAST(COALESCE(c16,c13) AS INT) > ?) OR (CAST(COALESCE(c15,c12) AS INT) > ?)) ORDER BY CAST(COALESCE(c15,c12) AS INT) ASC, CAST(COALESCE(c16,c13) AS INT) ASC, CAST(c12 as INT) ASC, idEpisode ASC LIMIT 1", (KodiShowId[0], Episode[1], Episode[2], Episode[1]))
                        nextEpisode = self.cursor.fetchone()

                    if nextEpisode:
                        NextEpisodeId = nextEpisode[0]
                        NextEpisodeInfos += (f"{LastPlayedDate};{NextEpisodeId};Episode",)

        NextEpisodeInfos = sorted(NextEpisodeInfos, reverse=True) # reverse sort by date
        return NextEpisodeInfos

    def get_tvshows_metadata_for_listitem(self, KodiShowId):
        self.cursor.execute("SELECT * FROM tvshow_view WHERE idShow = ?", (KodiShowId,))
        ItemData = self.cursor.fetchone()

        if not ItemData:
            return {}

        if ItemData[31] and ItemData[32]:
            UnWatchedEpisodes = int(ItemData[31]) - int(ItemData[32])
        else:
            UnWatchedEpisodes = 0

        Artwork = self.get_artwork(KodiShowId, "tvshow", "")
        People = self.get_people_artwork(KodiShowId, "tvshow")
        return {'mediatype': "tvshow", "dbid": KodiShowId, 'title': ItemData[1], 'SeriesName': ItemData[1], 'Overview': ItemData[2], 'Status': ItemData[3], 'KodiPremiereDate': ItemData[6], 'genre': ItemData[8], 'OriginalTitle': ItemData[9], 'Unique': ItemData[13], 'OfficialRating': ItemData[14], 'StudioName': ItemData[15], 'SortName': ItemData[16], 'CriticRating': ItemData[25], 'duration': ItemData[26], 'lastplayed': ItemData[30], 'CommunityRating': ItemData[34], 'path': f"videodb://tvshows/titles/{KodiShowId}/", 'properties': {'TotalEpisodes': ItemData[31], 'TotalSeasons': ItemData[33], 'WatchedEpisodes': ItemData[32], 'UnWatchedEpisodes': UnWatchedEpisodes, 'IsFolder': 'true', 'IsPlayable': 'true'}, 'people': People, 'artwork': Artwork}

    def add_link_movie_tvshow(self, KodiMovieId, KodiShowId):
        self.cursor.execute("INSERT OR REPLACE INTO movielinktvshow(idMovie, idShow) VALUES (?, ?)", (KodiMovieId, KodiShowId))

    # seasons
    def update_season_tvshowid(self, KodiShowId, KodiShowIdNew):
        self.cursor.execute("UPDATE seasons SET idShow = ? WHERE idShow = ?", (KodiShowIdNew, KodiShowId))

    def get_season_doubles(self, DoublesSeries):
        Data = {}

        for DoubleSerieDatas in list(DoublesSeries.values()):
            DoublesSeriesIds = ()

            for DoubleSerieData in DoubleSerieDatas[0]:
                DoublesSeriesIds += (DoubleSerieData,)

            Param = ",".join(len(DoublesSeriesIds) * ["?"]  )
            self.cursor.execute(f"SELECT season FROM seasons WHERE idShow IN ({Param}) GROUP BY season HAVING COUNT(season) > 1", DoublesSeriesIds)
            Doubles = self.cursor.fetchall()

            for Double in Doubles:
                ParamValues = DoublesSeriesIds + Double
                self.cursor.execute(f"SELECT idSeason FROM seasons WHERE idShow IN ({Param}) AND season = ?", ParamValues)
                KodiIds = self.cursor.fetchall()

                if KodiIds:
                    Data[f"SEASON_BY_SEASON(m)_SERIESID(m)/{Double[0]}/{str(DoublesSeriesIds)}"] = [{}, {}]

                    for KodiId in KodiIds:
                        Data[f"SEASON_BY_SEASON(m)_SERIESID(m)/{Double[0]}/{str(DoublesSeriesIds)}"][0].update({KodiId[0]: {"EmbyServerId": "", "EmbyLibraryIds": "", "EmbyId": ""}})

        return Data

    def add_season(self, KodiSeasonId, KodiShowId, SeasonNumber, SeasonName):
        self.cursor.execute("INSERT OR REPLACE INTO seasons(idSeason, idShow, season, name) VALUES (?, ?, ?, ?)", (KodiSeasonId, KodiShowId, SeasonNumber, SeasonName)) # IGNORE required for stacked content

    def update_season(self, KodiShowId, SeasonNumber, SeasonName, KodiSeasonId):
        self.cursor.execute("SELECT name FROM seasons WHERE idSeason = ?", (KodiSeasonId,))
        Data = self.cursor.fetchone()

        if Data and Data[0].endswith(" (download)"):
            SeasonNameMod = f"{SeasonName} (download)"
        else:
            SeasonNameMod = SeasonName

        self.cursor.execute("UPDATE seasons SET idShow = ?, season = ?, name = ? WHERE idSeason = ?", (KodiShowId, SeasonNumber, SeasonNameMod, KodiSeasonId))

    def create_entry_season(self):
        self.cursor.execute("SELECT coalesce(max(idSeason), 0) FROM seasons")
        return self.cursor.fetchone()[0] + 1

    def delete_season(self, KodiSeasonId):
        # Delete Season and subcontent
        SubcontentKodiIds = ()
        self.common_db.delete_artwork(KodiSeasonId, "season")
        self.cursor.execute("SELECT idEpisode, idFile FROM episode WHERE idSeason = ?", (KodiSeasonId,))
        EpisodesData = self.cursor.fetchall()

        for EpisodeData in EpisodesData:
            SubcontentKodiIds += ((EpisodeData[0], "Episode"),)
            self.delete_episode(EpisodeData[0], EpisodeData[1], None)

        self.cursor.execute("DELETE FROM seasons WHERE idSeason = ?", (KodiSeasonId,))
        return SubcontentKodiIds

    def get_season_metadata_for_listitem(self, KodiSeasonId):
        self.cursor.execute("SELECT * FROM season_view WHERE idSeason = ?", (KodiSeasonId,))
        ItemData = self.cursor.fetchone()

        if not ItemData:
            return {}

        if ItemData[12] and ItemData[13]:
            UnWatchedEpisodes = int(ItemData[12]) - int(ItemData[13])
        else:
            UnWatchedEpisodes = 0

        Artwork = self.get_artwork(KodiSeasonId, "season", "")
        People = self.get_people_artwork(KodiSeasonId, "season")
        return {'mediatype': "season", "dbid": KodiSeasonId, 'ParentIndexNumber': ItemData[2], 'title': ItemData[3], 'CriticRating': ItemData[4], 'SeriesName': ItemData[6], 'Overview': ItemData[7], 'KodiPremiereDate': ItemData[8], 'genre': ItemData[9], 'StudioName': ItemData[10], 'OfficialRating': ItemData[11], 'firstaired': ItemData[14], 'path': f"videodb://tvshows/titles/{ItemData[1]}/{ItemData[2]}/", 'properties': {'NumEpisodes': ItemData[12], 'WatchedEpisodes': ItemData[13], 'UnWatchedEpisodes': UnWatchedEpisodes, 'IsFolder': 'true', 'IsPlayable': 'true'}, 'people': People, 'artwork': Artwork}

    def get_showid_by_episodeid(self, KodiEpisodeId):
        self.cursor.execute("SELECT idShow FROM episode WHERE idEpisode = ?", (KodiEpisodeId,))
        KodiShowId = self.cursor.fetchone()

        if KodiShowId:
            return KodiShowId[0]

        return None

    def get_seasonid_by_showid_number(self, KodiTVShowId, KodiSeasonNumber):
        self.cursor.execute("SELECT idSeason FROM seasons WHERE idShow = ? AND season = ?", (KodiTVShowId, KodiSeasonNumber))
        KodiSeasonId = self.cursor.fetchone()

        if KodiSeasonId:
            return KodiSeasonId[0]

        return -1

    def get_season_number(self, KodiSeasonId):
        self.cursor.execute("SELECT season FROM seasons WHERE idSeason = ?", (KodiSeasonId,))
        SeasonNumber = self.cursor.fetchone()

        if SeasonNumber:
            return SeasonNumber[0]

        return None

    # episode
    def update_episode_tvshowid(self, KodiShowId, KodiShowIdNew):
        self.cursor.execute("UPDATE episode SET idShow = ? WHERE idShow = ?", (KodiShowIdNew, KodiShowId))

    def update_episode_seasonid(self, KodiSeasonId, KodiSeasonIdNew):
        self.cursor.execute("UPDATE episode SET idSeason = ? WHERE idSeason = ?", (KodiSeasonIdNew, KodiSeasonId))

    def get_episode_doubles(self):
        Data = {}

        # Detect doubles by multiple identical tvshows but skip if seasonnumber or episodenumber is None -> SQL "IS" respects queries by None, "=" skips None's
        self.cursor.execute("SELECT strTitle, premiered, c12, c13 FROM episode_view GROUP BY strTitle, premiered, c12, c13 HAVING COUNT(strTitle) > 1")
        Doubles = self.cursor.fetchall()

        for Double in Doubles:
            self.cursor.execute("SELECT idEpisode FROM episode_view WHERE strTitle = ? AND premiered IS ? AND c12 = ? AND c13 = ?" , (Double[0], Double[1], Double[2], Double[3]))
            KodiIds = self.cursor.fetchall()

            if KodiIds:
                Data[f"EPISODE_BY_TVSHOWNAME(m)_TVSHOWDATE(o)_SEASONNUMBER(m)_NUMBER(m)/{Double[0]}/{Double[1]}/{Double[2]}/{Double[3]}"] = [{}, {}]

                for KodiId in KodiIds:
                    Data[f"EPISODE_BY_TVSHOWNAME(m)_TVSHOWDATE(o)_SEASONNUMBER(m)_NUMBER(m)/{Double[0]}/{Double[1]}/{Double[2]}/{Double[3]}"][0].update({KodiId[0]: {"EmbyServerId": "", "EmbyLibraryIds": "", "EmbyId": ""}})

        # Detect doubles by multiple identical tvshows and episode name must match
        self.cursor.execute("SELECT strTitle, premiered, c12, c13, c00 FROM episode_view GROUP BY strTitle, premiered, c12, c13, c00 HAVING COUNT(c00) > 1")
        Doubles = self.cursor.fetchall()

        for Double in Doubles:
            self.cursor.execute("SELECT idEpisode FROM episode_view WHERE strTitle = ? AND premiered IS ? AND c12 IS ? AND c13 IS ? AND c00 = ?" , (Double[0], Double[1], Double[2], Double[3], Double[4]))
            KodiIds = self.cursor.fetchall()

            if KodiIds:
                Data[f"EPISODE_BY_TVSHOWNAME(m)_TVSHOWDATE(o)_SEASONNUMBER(o)_NUMBER(o)_NAME(m)/{Double[0]}/{Double[1]}/{Double[2]}/{Double[3]}/{Double[4]}"] = [{}, {}]

                for KodiId in KodiIds:
                    Data[f"EPISODE_BY_TVSHOWNAME(m)_TVSHOWDATE(o)_SEASONNUMBER(o)_NUMBER(o)_NAME(m)/{Double[0]}/{Double[1]}/{Double[2]}/{Double[3]}/{Double[4]}"][0].update({KodiId[0]: {"EmbyServerId": "", "EmbyLibraryIds": "", "EmbyId": ""}})

        # Detect doubles by single tvshow containing double episodes
        self.cursor.execute("SELECT c00, idShow, c12, c13 FROM episode GROUP BY c00, idShow, c12, c13 HAVING COUNT(c00) > 1")
        Doubles = self.cursor.fetchall()

        for Double in Doubles:
            self.cursor.execute("SELECT idEpisode FROM episode WHERE c00 = ? AND idShow = ? AND c12 IS ? AND c13 IS ?" , (Double[0], Double[1], Double[2], Double[3]))
            KodiIds = self.cursor.fetchall()

            if KodiIds:
                Data[f"EPISODE_BY_NAME(m)_TVSHOWID(m)_SEASONNUMBER(o)_NUMBER(o)/{Double[0]}/{Double[1]}/{Double[2]}/{Double[3]}"] = [{}, {}]

                for KodiId in KodiIds:
                    Data[f"EPISODE_BY_NAME(m)_TVSHOWID(m)_SEASONNUMBER(o)_NUMBER(o)/{Double[0]}/{Double[1]}/{Double[2]}/{Double[3]}"][0].update({KodiId[0]: {"EmbyServerId": "", "EmbyLibraryIds": "", "EmbyId": ""}})

        return Data

    def add_episode(self, KodiItemId, KodiFileId, Name, Overview, RatingId, Writers, PremiereDate, Poster, RunTimeTicks, Directors, ParentIndexNumber, IndexNumber, OriginalTitle, SortParentIndexNumber, SortIndexNumber, FilePath, FileFilename, KodiPathId, Unique, KodiShowId, KodiSeasonId, Filename, DateCreated, PlayCount, LastPlayedDate, KodiStackedFilename):
        FilePath = f"{FilePath}{FileFilename}"
        self.cursor.execute("INSERT INTO episode(idEpisode, idFile, c00, c01, c03, c04, c05, c06, c09, c10, c12, c13, c14, c15, c16, c18, c19, c20, idShow, idSeason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (KodiItemId, KodiFileId, Name, Overview, RatingId, Writers, PremiereDate, Poster, RunTimeTicks, Directors, ParentIndexNumber, IndexNumber, OriginalTitle, SortParentIndexNumber, SortIndexNumber, FilePath, KodiPathId, Unique, KodiShowId, KodiSeasonId))
        self.add_file(KodiPathId, Filename, DateCreated, KodiFileId, PlayCount, LastPlayedDate, KodiStackedFilename)

    def update_episode(self, KodiItemId, KodiFileId, Name, Overview, RatingId, Writers, PremiereDate, Poster, RunTimeTicks, Directors, ParentIndexNumber, IndexNumber, OriginalTitle, SortParentIndexNumber, SortIndexNumber, KodiPath, FileFilename, KodiPathId, Unique, KodiShowId, KodiSeasonId, PlayCount, LastPlayedDate, KodiStackedFilename, DateCreated):
        FilePath = f"{KodiPath}{FileFilename}"
        self.cursor.execute("UPDATE episode SET idFile = ?, c00 = ?, c01 = ?, c03 = ?, c04 = ?, c05 = ?, c06 = ?, c09 = ?, c10 = ?, c12 = ?, c13 = ?, c14 = ?, c15 = ?, c16 = ?, c18 = ?, c19 = ?, c20 = ?, idShow = ?, idSeason = ? WHERE idEpisode = ?", (KodiFileId, Name, Overview, RatingId, Writers, PremiereDate, Poster, RunTimeTicks, Directors, ParentIndexNumber, IndexNumber, OriginalTitle, SortParentIndexNumber, SortIndexNumber, FilePath, KodiPathId, Unique, KodiShowId, KodiSeasonId, KodiItemId))
        self.update_file(KodiFileId, PlayCount, LastPlayedDate, DateCreated, FileFilename, KodiStackedFilename)
        self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (KodiPath, KodiPathId))

    def create_entry_episode(self):
        self.cursor.execute("SELECT coalesce(max(idEpisode), 0) FROM episode")
        return self.cursor.fetchone()[0] + 1

    def delete_episode(self, KodiItemId, KodiFileId, KodiPathId):
        self.cursor.execute("DELETE FROM episode WHERE idEpisode = ?", (KodiItemId,))
        self.cursor.execute("DELETE FROM files WHERE idFile = ?", (KodiFileId,))

#        if KodiPathId:
#            self.cursor.execute("DELETE FROM path WHERE idPath = ?", (KodiPathId,))

    def get_episode_metadata_for_listitem(self, KodiItemId, PathAndFilename):
        self.cursor.execute("SELECT * FROM episode_view WHERE idEpisode = ?", (KodiItemId,))
        ItemData = self.cursor.fetchone()

        if not ItemData:
            return {}

        Path = ItemData[30].replace("|redirect-limit=1000", "")

        if not PathAndFilename:
            PathAndFilename = f"{Path}{ItemData[29]}"

        People = self.get_people_artwork(KodiItemId, "episode")
        People += self.get_people_artwork(ItemData[26], "tvshow")
        Artwork = self.get_artwork(KodiItemId, "episode", "")
        Artwork.update(self.get_artwork(ItemData[26], "tvshow", "tvshow."))
        Artwork.update(self.get_artwork(ItemData[28], "season", "season."))
        return {'mediatype': "episode", "dbid": KodiItemId, 'title': ItemData[2], 'Overview': ItemData[3], 'Writer': ItemData[6], 'KodiPremiereDate': ItemData[7], 'duration': ItemData[11], 'Director': ItemData[12], 'ParentIndexNumber': ItemData[14], 'IndexNumber': ItemData[15], 'OriginalTitle': ItemData[16], 'SortParentIndexNumber': ItemData[17], 'SortIndexNumber': ItemData[18], 'Unique': ItemData[22], 'CriticRating': ItemData[27], 'playCount': ItemData[31], 'lastplayed': ItemData[32], 'SeriesName': ItemData[34], 'genre': ItemData[35], 'StudioName': ItemData[36], 'path': Path, 'pathandfilename': PathAndFilename, 'properties': {'IsFolder': 'false', 'IsPlayable': 'true'}, 'people': People, 'artwork': Artwork, 'KodiRunTimeTicks': ItemData[40], 'KodiPlaybackPositionTicks': ItemData[39]}

    # boxsets
    def add_boxset(self, strSet, strOverview):
        self.cursor.execute("SELECT coalesce(max(idSet), 0) FROM sets")
        set_id =  self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT INTO sets(idSet, strSet, strOverview) VALUES (?, ?, ?)", (set_id, strSet, strOverview))
        return set_id

    def update_boxset(self, strSet, strOverview, idSet):
        self.cursor.execute("UPDATE sets SET strSet = ?, strOverview = ? WHERE idSet = ?", (strSet, strOverview, idSet))

    def set_boxset(self, idSet, idMovie):
        self.cursor.execute("UPDATE movie SET idSet = ? WHERE idMovie = ?", (idSet, idMovie))

    def remove_from_boxset(self, idMovie):
        self.cursor.execute("UPDATE movie SET idSet = null WHERE idMovie = ?", (idMovie,))

    def delete_boxset(self, idSet):
        self.cursor.execute("DELETE FROM sets WHERE idSet = ?", (idSet,))

    # file
    def add_file(self, idPath, Filename, dateAdded, KodiFileId, PlayCount, LastPlayedDate, KodiStackedFilename):
        if not PlayCount:
            PlayCount = None

        if KodiStackedFilename:
            Filename = KodiStackedFilename

        self.cursor.execute("INSERT INTO files(idPath, strFilename, dateAdded, idFile, playCount, lastPlayed) VALUES (?, ?, ?, ?, ?, ?)", (idPath, Filename, dateAdded, KodiFileId, PlayCount, LastPlayedDate))

    def update_file(self, KodiFileId, PlayCount, LastPlayedDate, dateAdded, Filename, KodiStackedFilename):
        if not PlayCount:
            PlayCount = None

        if KodiStackedFilename:
            Filename = KodiStackedFilename

        if Filename:
            self.cursor.execute("UPDATE files SET playCount = ?, lastPlayed = ?, strFilename = ?, dateAdded = ? WHERE idFile = ?", (PlayCount, LastPlayedDate, Filename, dateAdded, KodiFileId))
        else:
            self.cursor.execute("UPDATE files SET playCount = ?, lastPlayed = ?, dateAdded = ? WHERE idFile = ?", (PlayCount, LastPlayedDate, dateAdded, KodiFileId))

    def create_entry_file(self):
        self.cursor.execute("SELECT coalesce(max(idFile), 0) FROM files")
        return self.cursor.fetchone()[0] + 1

    # video versions
    def get_add_videoversiontype(self, VersionName):
        self.cursor.execute("SELECT id FROM videoversiontype WHERE name = ?", (VersionName,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(id), 0) FROM videoversiontype")
        VideoVersionTypeId = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT OR REPLACE INTO videoversiontype(id, name, owner, itemType) VALUES (?, ?, ?, ?)", (VideoVersionTypeId, VersionName, 0, 0))
        return VideoVersionTypeId

    def delete_videoversion_by_KodiId_notKodiFileId_KodiType(self, KodiItemId, KodiFileId, KodiType):
        self.cursor.execute("SELECT idFile FROM videoversion WHERE idMedia = ? AND idFile != ? AND media_type = ?", (KodiItemId, KodiFileId, KodiType))
        KodiFileIdsRef = self.cursor.fetchall()
        self.cursor.execute("DELETE FROM videoversion WHERE idMedia = ? AND idFile != ? AND media_type = ?", (KodiItemId, KodiFileId, KodiType))

        for KodiFileIdRef in KodiFileIdsRef:
            self.cursor.execute("DELETE FROM files WHERE idFile = ?", (KodiFileIdRef[0],))

    def get_KodiFileId_by_videoversion(self, KodiItemId, KodiType):
        self.cursor.execute("SELECT idFile FROM videoversion WHERE idMedia = ? AND media_type = ?", (KodiItemId, KodiType))
        return self.cursor.fetchall()

    def delete_videoversion(self, KodiItemId, KodiType):
        self.cursor.execute("SELECT idFile FROM videoversion WHERE idMedia = ? AND media_type = ?", (KodiItemId, KodiType))
        KodiFileIdsRef = self.cursor.fetchall()
        self.cursor.execute("DELETE FROM videoversion WHERE idMedia = ? AND media_type = ?", (KodiItemId, KodiType))

        for KodiFileIdRef in KodiFileIdsRef:
            self.cursor.execute("DELETE FROM files WHERE idFile = ?", (KodiFileIdRef[0],))

    # people
    def add_person(self, PersonName, ArtUrl):
        self.cursor.execute("SELECT coalesce(max(actor_id), 0) FROM actor")
        PersonId = self.cursor.fetchone()[0] + 1
        PersonNameMod = PersonName

        while True:
            try:
                self.cursor.execute("INSERT INTO actor(actor_id, name, art_urls) VALUES (?, ?, ?)", (PersonId, PersonNameMod, ArtUrl))
                break
            except Exception as Error:
                xbmc.log(f"EMBY.database.video_db: Add person, Duplicate ActorName detected: {PersonNameMod} / {Error}", 0) # LOGDEBUG
                PersonNameMod += " "

            if len(PersonNameMod) >= 255: # max 256 char
                xbmc.log(f"EMBY.database.video_db: Add person, too many charecters ActorName detected: {PersonNameMod}", 2) # LOGWARNING
                return -1

        return PersonId

    def update_person(self, PersonId, PersonName, ArtUrl):
        PersonNameMod = PersonName

        while True:
            try:
                self.cursor.execute("UPDATE OR IGNORE actor SET name = ?, art_urls = ? WHERE actor_id = ?", (PersonNameMod, ArtUrl, PersonId))
                break
            except Exception as Error:
                xbmc.log(f"EMBY.database.video_db: Update person, Duplicate ActorName detected: {PersonNameMod} / {Error}", 0) # LOGDEBUG
                PersonNameMod += " "

            if len(PersonNameMod) >= 255:
                xbmc.log(f"EMBY.database.video_db: Update person, too many charecters ActorName detected: {PersonNameMod}", 2) # LOGWARNING

    def delete_links_actors(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM actor_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def delete_links_director(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM director_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def delete_links_writer(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM writer_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def get_People(self, ActorId):
        MusicVideos = False
        Movies = False
        TVShows = False
        self.cursor.execute("SELECT name, art_urls FROM actor WHERE actor_id = ?", (ActorId,))
        Data = self.cursor.fetchone()

        if Data:
            self.cursor.execute("SELECT * FROM actor_link WHERE actor_id = ? AND media_type = ?", (ActorId, "musicvideo"))

            if self.cursor.fetchone():
                MusicVideos = True
            else:
                self.cursor.execute("SELECT * FROM director_link WHERE actor_id = ? AND media_type = ?", (ActorId, "musicvideo"))

                if self.cursor.fetchone():
                    MusicVideos = True
                else:
                    self.cursor.execute("SELECT * FROM writer_link WHERE actor_id = ? AND media_type = ?", (ActorId, "musicvideo"))

                    if self.cursor.fetchone():
                        MusicVideos = True

            self.cursor.execute("SELECT * FROM actor_link WHERE actor_id = ? AND media_type = ?", (ActorId, "movie"))

            if self.cursor.fetchone():
                Movies = True
            else:
                self.cursor.execute("SELECT * FROM director_link WHERE actor_id = ? AND media_type = ?", (ActorId, "movie"))

                if self.cursor.fetchone():
                    Movies = True
                else:
                    self.cursor.execute("SELECT * FROM writer_link WHERE actor_id = ? AND media_type = ?", (ActorId, "movie"))

                    if self.cursor.fetchone():
                        Movies = True

            self.cursor.execute("SELECT * FROM actor_link WHERE actor_id = ? AND media_type = ?", (ActorId, "tvshow"))

            if self.cursor.fetchone():
                TVShows = True
            else:
                self.cursor.execute("SELECT * FROM director_link WHERE actor_id = ? AND media_type = ?", (ActorId, "tvshow"))

                if self.cursor.fetchone():
                    TVShows = True
                else:
                    self.cursor.execute("SELECT * FROM writer_link WHERE actor_id = ? AND media_type = ?", (ActorId, "tvshow"))

                    if self.cursor.fetchone():
                        TVShows = True

            return Data[0], Data[1], MusicVideos, Movies, TVShows

        return "", "", False, False, False

    def get_actor_metadata_for_listitem(self, KodiItemId):
        self.cursor.execute("SELECT * FROM actor WHERE actor_id = ?", (KodiItemId,))
        ItemData = self.cursor.fetchone()

        if not ItemData:
            return {}

        Artwork = {"poster": ItemData[2]}
        return {'mediatype': "actor", "dbid": KodiItemId, 'title': ItemData[1], 'artist': ItemData[1], 'path': f"videodb://musicvideos/actors/{KodiItemId}/", 'properties': {'IsFolder': 'true', 'IsPlayable': 'true'}, 'artwork': Artwork}

    def del_musicartist(self, ArtistId):
        self.delete_people_by_Id(ArtistId)

    def delete_people_by_Id(self, ActorId):
        self.cursor.execute("DELETE FROM actor_link WHERE actor_id = ?", (ActorId,))
        self.cursor.execute("DELETE FROM director_link WHERE actor_id = ?", (ActorId,))
        self.cursor.execute("DELETE FROM writer_link WHERE actor_id = ?", (ActorId,))
        self.cursor.execute("DELETE FROM actor WHERE actor_id = ?", (ActorId,))

    def add_director_link(self, ActorId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO director_link(actor_id, media_id, media_type) VALUES (?, ?, ?)", (ActorId, MediaId, MediaType))

    def add_writer_link(self, ActorId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO writer_link(actor_id, media_id, media_type) VALUES (?, ?, ?)", (ActorId, MediaId, MediaType))

    def add_actor_link(self, ActorId, MediaId, MediaType, Role, Order):
        self.cursor.execute("INSERT OR REPLACE INTO actor_link(actor_id, media_id, media_type, role, cast_order) VALUES (?, ?, ?, ?, ?)", (ActorId, MediaId, MediaType, Role, Order))

    def get_people_artwork(self, KodiItemId, ContentType):
        People = ()
        PeopleCounter = 0
        self.cursor.execute("SELECT * FROM actor_link WHERE media_id = ? and media_type = ?", (KodiItemId, ContentType))
        ActorLinks = self.cursor.fetchall()

        for ActorLink in ActorLinks:
            self.cursor.execute("SELECT * FROM actor WHERE actor_id = ?", (ActorLink[0],))
            Actor = self.cursor.fetchone()
            People += ((Actor[1], ActorLink[3], PeopleCounter, Actor[2]),)
            PeopleCounter += 1

        self.cursor.execute("SELECT * FROM director_link WHERE media_id = ? and media_type = ?", (KodiItemId, ContentType))
        DirectorLinks = self.cursor.fetchall()

        for DirectorLink in DirectorLinks:
            self.cursor.execute("SELECT * FROM actor WHERE actor_id = ?", (DirectorLink[0],))
            Actor = self.cursor.fetchone()
            People += ((Actor[1], "Director", PeopleCounter, Actor[2]),)
            PeopleCounter += 1

        return People

    # streams
    def delete_streams(self, KodiFileId):
        self.cursor.execute("DELETE FROM streamdetails WHERE idFile = ?", (KodiFileId,))

    def add_streams(self, KodiFileId, videostream, audiostream, subtitlestream, runtime):
        for track in videostream:
            self.cursor.execute("INSERT OR REPLACE INTO streamdetails(idFile, iStreamType, strVideoCodec, fVideoAspect, iVideoWidth, iVideoHeight, iVideoDuration, strStereoMode, strVideoLanguage, strHdrType) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (KodiFileId, 0, track['codec'], track['aspect'], track['width'], track['height'], runtime, track['3d'], track['language'], track['hdrtype']))

        for track in audiostream:
            self.cursor.execute("INSERT OR REPLACE INTO streamdetails(idFile, iStreamType, strAudioCodec, iAudioChannels, strAudioLanguage) VALUES (?, ?, ?, ?, ?)", (KodiFileId, 1, track['codec'], track['channels'], track['language']))

        for track in subtitlestream:
            if not track['external']:
                self.cursor.execute("INSERT OR REPLACE INTO streamdetails(idFile, iStreamType, strSubtitleLanguage) VALUES (?, ?, ?)", (KodiFileId, 2, track['language']))

    # stacked times
    def delete_stacktimes(self, KodiFileId):
        self.cursor.execute("DELETE FROM stacktimes WHERE idFile = ?", (KodiFileId,))

    def add_stacktimes(self, idFile, times):
        self.cursor.execute("INSERT OR REPLACE INTO stacktimes(idFile, times) VALUES (?, ?)", (idFile, times))

    # tags
    def get_add_tag(self, TagName):
        self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (TagName,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(tag_id), 0) FROM tag")
        TagId = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT OR REPLACE INTO tag(tag_id, name) VALUES (?, ?)", (TagId, TagName))
        return TagId

    def update_tag(self, TagName, TagId):
        self.cursor.execute("UPDATE tag SET name = ? WHERE tag_id = ?", (TagName, TagId))

    def add_tag_link(self, TagId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO tag_link(tag_id, media_id, media_type) VALUES (?, ?, ?)", (TagId, MediaId, MediaType))

    def delete_library_links_tags(self, MediaId, MediaType, LibraryName):
        self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (f"{LibraryName} (Library)",))
        TagId = self.cursor.fetchone()

        if TagId:
            self.cursor.execute("DELETE FROM tag_link WHERE tag_id = ? AND media_id = ? AND media_type = ?", (TagId[0], MediaId, MediaType))

    def delete_links_tags(self, MediaId, MediaType, KodiLibraryTagIds):
        if KodiLibraryTagIds:
            KodiLibraryTagIdsArray = ()

            for KodiLibraryTagId in KodiLibraryTagIds:
                KodiLibraryTagIdsArray += (KodiLibraryTagId[0], )

            Param = ",".join(len(KodiLibraryTagIdsArray) * ["?"]  )
            self.cursor.execute(f"DELETE FROM tag_link WHERE media_id = ? AND media_type = ? AND tag_id NOT IN ({Param})", (MediaId, MediaType) + KodiLibraryTagIdsArray)
        else:
            self.cursor.execute("DELETE FROM tag_link WHERE media_id = ? AND media_type = ?", (MediaId, MediaType))

    def get_collection_tags(self, LibraryTag, KodiMediaType):
        self.cursor.execute("SELECT tag_id, name FROM tag WHERE name LIKE ?", ("% (Collection)",))
        CollectionItems = self.cursor.fetchall()
        CollectionIds = ()
        CollectionNames = {}

        for CollectionItem in CollectionItems:
            CollectionIds += (CollectionItem[0],)
            CollectionNames[CollectionItem[0]] = CollectionItem[1]

        CollectionValidIds = ()
        CollectionValidNames = ()

        if LibraryTag and LibraryTag != "unknown":
            self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (LibraryTag,))
            LibraryTagId = self.cursor.fetchone()

            if LibraryTagId:
                self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE tag_id = ?", (LibraryTagId[0],))
                ValidMediaIds = self.cursor.fetchall()
            else:
                return (), ()
        else:
            self.cursor.execute("SELECT DISTINCT media_id FROM tag_link WHERE media_type = ?", (KodiMediaType,))
            ValidMediaIds = self.cursor.fetchall()

        for ValidMediaId in  ValidMediaIds:
            self.cursor.execute("SELECT DISTINCT tag_id FROM tag_link WHERE media_id = ? AND media_type = ?", (ValidMediaId[0], KodiMediaType))
            TagIds = self.cursor.fetchall()

            for TagId in TagIds:
                if TagId[0] in CollectionIds and TagId[0] not in CollectionValidIds:
                    CollectionValidIds += TagId
                    CollectionValidNames += (CollectionNames[TagId[0]],)

        return CollectionValidIds, CollectionValidNames

    def get_Tag_Name(self, TagId):
        MusicVideos = False
        Movies = False
        TVShows = False
        self.cursor.execute("SELECT name FROM tag WHERE tag_id = ?", (TagId,))
        Data = self.cursor.fetchone()

        if Data:
            self.cursor.execute("SELECT * FROM tag_link WHERE tag_id = ? AND media_type = ?", (TagId, "musicvideo"))

            if self.cursor.fetchone():
                MusicVideos = True

            self.cursor.execute("SELECT * FROM tag_link WHERE tag_id = ? AND media_type = ?", (TagId, "movie"))

            if self.cursor.fetchone():
                Movies = True

            self.cursor.execute("SELECT * FROM tag_link WHERE tag_id = ? AND media_type = ?", (TagId, "tvshow"))

            if self.cursor.fetchone():
                TVShows = True

            return Data[0], MusicVideos, Movies, TVShows

        return "", False, False, False

    def delete_tag(self, Name):
        self.cursor.execute("DELETE FROM tag WHERE name = ?", (Name,))

    def delete_tag_by_Id(self, TagId):
        self.cursor.execute("DELETE FROM tag WHERE tag_id = ?", (TagId,))
        self.cursor.execute("DELETE FROM tag_link WHERE tag_id = ?", (TagId,))

    def add_link_tag(self, TagId, KodiItemId, KodiType):
        self.cursor.execute("INSERT OR REPLACE INTO tag_link(tag_id, media_id, media_type) VALUES (?, ?, ?)", (TagId, KodiItemId, KodiType)) # IGNORE required for stacked content

    def set_Favorite_Tag(self, IsFavorite, KodiItemId, KodiType):
        if KodiType == "tvshow":
            TagName = "TVShows (Favorites)"
        else:
            TagName = f"{KodiType[:1].upper() + KodiType[1:]}s (Favorites)"

        self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (TagName,))
        Data = self.cursor.fetchone()

        if Data:
            TagId = Data[0]
        else:
            self.cursor.execute("SELECT coalesce(max(tag_id), 0) FROM tag")
            TagId = self.cursor.fetchone()[0] + 1
            self.cursor.execute("INSERT INTO tag(tag_id, name) VALUES (?, ?)", (TagId, TagName))

        if IsFavorite:
            self.add_link_tag(TagId, KodiItemId, KodiType)
        else:
            self.cursor.execute("DELETE FROM tag_link WHERE tag_id = ? AND media_type = ? AND media_id = ?", (TagId, KodiType, KodiItemId))

    # genres
    def get_add_genre(self, GenreName):
        self.cursor.execute("SELECT genre_id FROM genre WHERE name = ?", (GenreName,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(genre_id), 0) FROM genre")
        GenreId = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT INTO genre(genre_id, name) VALUES (?, ?)", (GenreId, GenreName))
        return GenreId

    def update_genre(self, GenreName, GenreId):
        self.cursor.execute("UPDATE OR IGNORE genre SET name = ? WHERE genre_id = ?", (GenreName, GenreId))

    def add_genre_link(self, GenreId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO genre_link(genre_id, media_id, media_type) VALUES (?, ?, ?)", (GenreId, MediaId, MediaType))

    def delete_links_genres(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM genre_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def get_Genre_Name_hasMusicVideos_hasMovies_hasTVShows(self, GenreId):
        MusicVideos = False
        Movies = False
        TVShows = False
        self.cursor.execute("SELECT name FROM genre WHERE genre_id = ?", (GenreId,))
        Data = self.cursor.fetchone()

        if Data:
            self.cursor.execute("SELECT * FROM genre_link WHERE genre_id = ? AND media_type = ?", (GenreId, "musicvideo"))

            if self.cursor.fetchone():
                MusicVideos = True

            self.cursor.execute("SELECT * FROM genre_link WHERE genre_id = ? AND media_type = ?", (GenreId, "movie"))

            if self.cursor.fetchone():
                Movies = True

            self.cursor.execute("SELECT * FROM genre_link WHERE genre_id = ? AND media_type = ?", (GenreId, "tvshow"))

            if self.cursor.fetchone():
                TVShows = True

            return Data[0], MusicVideos, Movies, TVShows

        return "", False, False, False

    def delete_genre_by_Id(self, GenreId):
        self.cursor.execute("DELETE FROM genre_link WHERE genre_id = ?", (GenreId,))
        self.cursor.execute("DELETE FROM genre WHERE genre_id = ?", (GenreId,))

    def delete_musicgenre_by_Id(self, GenreId):
        self.cursor.execute("DELETE FROM genre_link WHERE genre_id = ?", (GenreId,))
        self.cursor.execute("DELETE FROM genre WHERE genre_id = ?", (GenreId,))

    # studios
    def get_add_studio(self, StudioName):
        self.cursor.execute("SELECT studio_id FROM studio WHERE name = ?", (StudioName,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(studio_id), 0) FROM studio")
        StudioId = self.cursor.fetchone()[0] + 1
        self.cursor.execute("INSERT OR REPLACE INTO studio(studio_id, name) VALUES (?, ?)", (StudioId, StudioName))
        return StudioId

    def update_studio(self, StudioName, StudioId):
        self.cursor.execute("UPDATE OR IGNORE studio SET name = ? WHERE studio_id = ?", (StudioName, StudioId))

    def add_studio_link(self, GenreId, MediaId, MediaType):
        self.cursor.execute("INSERT OR REPLACE INTO studio_link(studio_id, media_id, media_type) VALUES (?, ?, ?)", (GenreId, MediaId, MediaType))

    def delete_links_studios(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM studio_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def delete_studio_by_Id(self, StudioId):
        self.cursor.execute("DELETE FROM studio_link WHERE studio_id = ?", (StudioId,))
        self.cursor.execute("DELETE FROM studio WHERE studio_id = ?", (StudioId,))

    def get_Studio_Name(self, StudioId):
        MusicVideos = False
        Movies = False
        TVShows = False
        self.cursor.execute("SELECT name FROM studio WHERE studio_id = ?", (StudioId,))
        Data = self.cursor.fetchone()

        if Data:
            self.cursor.execute("SELECT * FROM studio_link WHERE studio_id = ? AND media_type = ?", (StudioId, "musicvideo"))

            if self.cursor.fetchone():
                MusicVideos = True

            self.cursor.execute("SELECT * FROM studio_link WHERE studio_id = ? AND media_type = ?", (StudioId, "movie"))

            if self.cursor.fetchone():
                Movies = True

            self.cursor.execute("SELECT * FROM studio_link WHERE studio_id = ? AND media_type = ?", (StudioId, "tvshow"))

            if self.cursor.fetchone():
                TVShows = True

            return Data[0], MusicVideos, Movies, TVShows

        return "", False, False, False

    # ratings
    def delete_ratings(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM rating WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def add_ratings(self, KodiItemId, media_type, rating_type, Rating):
        if Rating:
            if rating_type == "default" and utils.imdbrating:
                rating_type = "imdb"

            self.cursor.execute("SELECT coalesce(max(rating_id), 0) FROM rating")
            rating_id = self.cursor.fetchone()[0] + 1
            self.cursor.execute("INSERT INTO rating(rating_id, media_id, media_type, rating_type, rating) VALUES (?, ?, ?, ?, ?)", (rating_id, KodiItemId, media_type, rating_type, Rating))
            return rating_id

        return None

    # uniqueid
    def delete_uniqueids(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM uniqueid WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def add_uniqueids(self, KodiItemId, ProviderIds, MediaId, DefaulId):
        UniqueId = None

        for Provider, Value in list(ProviderIds.items()):
            if not Value:
                continue

            Provider = Provider.lower()
            self.cursor.execute("SELECT coalesce(max(uniqueid_id), 0) FROM uniqueid")
            Unique = self.cursor.fetchone()[0] + 1
            self.cursor.execute("INSERT INTO uniqueid(uniqueid_id, media_id, media_type, value, type) VALUES (?, ?, ?, ?, ?)", (Unique, KodiItemId, MediaId, Value, Provider))

            if Provider == DefaulId:
                UniqueId = Unique

        return UniqueId

    # bookmarks
    def get_bookmark_urls_all(self):
        self.cursor.execute("SELECT thumbNailImage FROM bookmark")
        return self.cursor.fetchall()

    def delete_bookmark(self, KodiFileId):
        self.cursor.execute("DELETE FROM bookmark WHERE idFile = ?", (KodiFileId,))

    def add_bookmarks(self, KodiFileId, RunTimeTicks, KodiChapters, PlaybackPositionTicks):
        for StartPositionTicks, Image in list(KodiChapters.items()):
            self.cursor.execute("INSERT INTO bookmark(idFile, timeInSeconds, totalTimeInSeconds, thumbNailImage, player, type) VALUES (?, ?, ?, ?, ?, ?)", (KodiFileId, StartPositionTicks, RunTimeTicks, Image, "VideoPlayer", 0))

        if PlaybackPositionTicks:
            self.cursor.execute("INSERT INTO bookmark(idFile, timeInSeconds, totalTimeInSeconds, player, type) VALUES (?, ?, ?, ?, ?)", (KodiFileId, PlaybackPositionTicks, RunTimeTicks, "VideoPlayer", 1))

    def update_bookmark_playstate(self, KodiFileId, playcount, date_played, Progress, Runtime):
        Update = False

        self.cursor.execute("SELECT timeInSeconds FROM bookmark WHERE idFile = ? AND type = ?", (KodiFileId, "1"))
        Data = self.cursor.fetchone()

        if Data:
            CurrentProgress = Data[0]

            if Progress:
                if CurrentProgress != Progress:
                    self.cursor.execute("UPDATE bookmark SET timeInSeconds = ?, totalTimeInSeconds = ? WHERE idFile = ?", (Progress, Runtime, KodiFileId))
                    Update = True
            else:
                self.cursor.execute("DELETE FROM bookmark WHERE idFile = ? AND type = ?", (KodiFileId, "1"))
                Update = True
        elif Progress:
            Update = True
            self.cursor.execute("INSERT INTO bookmark(idFile, timeInSeconds, totalTimeInSeconds, player, type) VALUES (?, ?, ?, ?, ?)", (KodiFileId, Progress, Runtime, "VideoPlayer", 1))

        # Update playcounter and last played date
        self.cursor.execute("SELECT playCount FROM files WHERE idFile = ?", (KodiFileId,))
        Data = self.cursor.fetchone()
        CurrentPlayCount = Data[0]

        if CurrentPlayCount != playcount:
            self.cursor.execute("UPDATE files SET playCount = ?, lastPlayed = ? WHERE idFile = ?", (playcount, date_played, KodiFileId))

            if (CurrentPlayCount and playcount and playcount -1 != CurrentPlayCount) or (not playcount and CurrentPlayCount) or (not CurrentPlayCount and playcount):
                Update = True

        return Update

    # countries
    def delete_links_countries(self, Media_id, media_type):
        self.cursor.execute("DELETE FROM country_link WHERE media_id = ? AND media_type = ?", (Media_id, media_type))

    def add_countries_and_links(self, ProductionLocations, media_id, media_type):
        for CountryName in ProductionLocations:
            self.cursor.execute("SELECT country_id FROM country WHERE name = ?", (CountryName,))
            Data = self.cursor.fetchone()

            if Data:
                country_id = Data[0]
            else:
                self.cursor.execute("SELECT coalesce(max(country_id), 0) FROM country")
                country_id = self.cursor.fetchone()[0] + 1
                self.cursor.execute("INSERT INTO country(country_id, name) VALUES (?, ?)", (country_id, CountryName))

            self.cursor.execute("INSERT OR REPLACE INTO country_link(country_id, media_id, media_type) VALUES (?, ?, ?)", (country_id, media_id, media_type))

    # artwork
    def get_artwork(self, KodiItemId, ContentType, PrefixKey):
        Artwork = {}
        self.cursor.execute("SELECT * FROM art WHERE media_id = ? AND media_type = ?", (KodiItemId, ContentType))
        ArtworksData = self.cursor.fetchall()

        for ArtworkData in ArtworksData:
            Artwork[f"{PrefixKey}{ArtworkData[3]}"] = ArtworkData[4]

        return Artwork

    def get_artworks(self, KodiItemId, ContentType):
        self.cursor.execute("SELECT * FROM art WHERE media_id = ? and media_type = ?", (KodiItemId, ContentType))
        return self.cursor.fetchall()

    def update_artwork(self, ArtId, url):
        self.cursor.execute("UPDATE art SET url = ? WHERE art_id = ?", (url, ArtId))

    # settings
    def get_FileSettings(self, KodiFileId):
        self.cursor.execute("SELECT idFile, Deinterlace, ViewMode, ZoomAmount, PixelRatio, VerticalShift, AudioStream, SubtitleStream, SubtitleDelay, SubtitlesOn, Brightness, Contrast, Gamma, VolumeAmplification, AudioDelay, ResumeTime, Sharpness, NoiseReduction, NonLinStretch, PostProcess, ScalingMethod, StereoMode, StereoInvert, VideoStream, TonemapMethod, TonemapParam, Orientation, CenterMixLevel FROM settings WHERE idFile = ?", (KodiFileId,))
        return self.cursor.fetchone()

    # Download item
    def get_Fileinfo_by_SubcontentId(self, KodiId, KodiType):
        if KodiType == "season":
            self.cursor.execute("SELECT idEpisode, idFile, c00 FROM episode WHERE idSeason = ?", (KodiId,))
        else:
            self.cursor.execute("SELECT idEpisode, idFile, c00 FROM episode WHERE idShow = ?", (KodiId,))

        FileInfos = ()
        EpisodesInfo = self.cursor.fetchall()

        for EpisodeInfo in EpisodesInfo:
            if EpisodeInfo[2].endswith(" (download)"):
                continue

            self.cursor.execute("SELECT strFilename, idPath FROM files WHERE idFile = ?", (EpisodeInfo[1],))
            FileInfo = self.cursor.fetchone()

            if FileInfo:
                self.cursor.execute("SELECT idParentPath FROM path WHERE idPath = ?", (FileInfo[1],))
                PathInfo = self.cursor.fetchone()

                if PathInfo:
                    FileInfos += ((EpisodeInfo[0], PathInfo[0], FileInfo[1], EpisodeInfo[1], FileInfo[0], EpisodeInfo[2]),)

        return FileInfos

    def get_KodiId_FileName_by_SubcontentId(self, KodiId, KodiType):
        if KodiType == "season":
            self.cursor.execute("SELECT idEpisode, c18 FROM episode WHERE idSeason = ?", (KodiId,))
        else:
            self.cursor.execute("SELECT idEpisode, c18 FROM episode WHERE idShow = ?", (KodiId,))

        EpisodesData = self.cursor.fetchall()
        Data = ()

        for EpisodeData in EpisodesData:
            Data += ((EpisodeData[0], "".join("".join(EpisodeData[1].split("/")[-1:]).split("\\")[-1:]), "episode"),)

        return Data

    def set_Subcontent_download_tags(self, KodiEpisodeId, AddContent):
        Artworks = ()
        self.cursor.execute("SELECT idShow, idSeason FROM episode WHERE idEpisode = ?", (KodiEpisodeId,))
        EpisodeAdded = self.cursor.fetchone()

        if EpisodeAdded:
            SeasonComplete = True
            self.cursor.execute("SELECT c00 FROM episode WHERE idSeason = ?", (EpisodeAdded[1],)) # get all episodes from season
            SeasonEpisodes = self.cursor.fetchall()

            for SeasonEpisode in SeasonEpisodes:
                if not SeasonEpisode[0].endswith(" (download)"):
                    SeasonComplete = False
                    break

            if SeasonComplete and AddContent:
                self.update_Name(EpisodeAdded[1], "season", True)
                Artworks += self.mod_artwork(EpisodeAdded[1], "season", True)
            elif not SeasonComplete and not AddContent:
                self.update_Name(EpisodeAdded[1], "season", False)
                Artworks += self.mod_artwork(EpisodeAdded[1], "season", False)

            TVShowComplete = True
            self.cursor.execute("SELECT c00 FROM episode WHERE idShow = ?", (EpisodeAdded[0],)) # get all episodes from season
            TVShowEpisodes = self.cursor.fetchall()

            for TVShowEpisode in TVShowEpisodes:
                if not TVShowEpisode[0].endswith(" (download)"):
                    TVShowComplete = False
                    break

            if TVShowComplete and AddContent:
                self.update_Name(EpisodeAdded[0], "tvshow", True)
                Artworks += self.mod_artwork(EpisodeAdded[0], "tvshow", True)
            elif not TVShowComplete and not AddContent:
                self.update_Name(EpisodeAdded[0], "tvshow", False)
                Artworks += self.mod_artwork(EpisodeAdded[0], "tvshow", False)

        return Artworks

    def mod_artwork(self, KodiId, KodiType, AddLabel):
        Artworks = ()
        ArtworksData = self.get_artworks(KodiId, KodiType)

        for ArtworkData in ArtworksData:
            if ArtworkData[3] in ("poster", "thumb", "landscape"):
                UrlMod = ArtworkData[4].split("|")

                if AddLabel:
                    UrlMod = f"{UrlMod[0].replace('-download', '')}-download|redirect-limit=1000"
                else:
                    UrlMod = f"{UrlMod[0].replace('-download', '')}|redirect-limit=1000"

                self.update_artwork(ArtworkData[0], UrlMod)
                Artworks += ((UrlMod,),)

        return Artworks

    def replace_Path_ContentItem(self, KodiId, KodiType, NewPath, OldPath=""):
        if KodiType == "episode":
            self.cursor.execute("SELECT c18 FROM episode WHERE idEpisode = ?", (KodiId,))
        elif KodiType == "movie":
            self.cursor.execute("SELECT c22 FROM movie WHERE idMovie = ?", (KodiId,))
        elif KodiType == "musicvideo":
            self.cursor.execute("SELECT c13 FROM musicvideo WHERE idMVideo = ?", (KodiId,))

        CurrentData = self.cursor.fetchone()

        if CurrentData:
            if OldPath:
                NewData = CurrentData[0].replace(OldPath, NewPath)
            else:
                NewData = CurrentData[0].replace("http://127.0.0.1:57342/", NewPath).replace("/emby_addon_mode/", NewPath)

            if KodiType == "episode":
                self.cursor.execute("UPDATE episode SET c18 = ? WHERE idEpisode = ?", (NewData, KodiId))
            elif KodiType == "movie":
                self.cursor.execute("UPDATE movie SET c22 = ? WHERE idMovie = ?", (NewData, KodiId))
            elif KodiType == "musicvideo":
                self.cursor.execute("UPDATE musicvideo SET c13 = ? WHERE idMVideo = ?", (NewData, KodiId))

    def update_Name(self, KodiId, KodiType, isDownloaded):
        if KodiType == "season":
            self.cursor.execute("SELECT name FROM seasons WHERE idSeason = ?", (KodiId,))
        elif KodiType == "tvshow":
            self.cursor.execute("SELECT c00, c15 FROM tvshow WHERE idShow = ?", (KodiId,))
        elif KodiType == "episode":
            self.cursor.execute("SELECT c00 FROM episode WHERE idEpisode = ?", (KodiId,))
        elif KodiType == "movie":
            self.cursor.execute("SELECT c00, c10 FROM movie WHERE idMovie = ?", (KodiId,))
        elif KodiType == "musicvideo":
            self.cursor.execute("SELECT c00 FROM musicvideo WHERE idMVideo = ?", (KodiId,))

        NameChanged = False
        CurrentName = self.cursor.fetchone()

        if CurrentName:
            if isDownloaded:
                NewName = f"{CurrentName[0]} (download)"
            else:
                NewName = CurrentName[0].replace(" (download)", "")

            NameChanged = bool(CurrentName != NewName)

            if NameChanged:
                if KodiType == "season":
                    self.cursor.execute("UPDATE seasons SET name = ? WHERE idSeason = ?", (NewName, KodiId))
                elif KodiType == "tvshow":
                    if isDownloaded:
                        NewSortName = f"{CurrentName[1]} (download)"
                    else:
                        NewSortName = CurrentName[1].replace(" (download)", "")

                    self.cursor.execute("UPDATE tvshow SET c00 = ?, c15 = ? WHERE idShow = ?", (NewName, NewSortName, KodiId))
                elif KodiType == "episode":
                    self.cursor.execute("UPDATE episode SET c00 = ? WHERE idEpisode = ?", (NewName, KodiId))
                elif KodiType == "movie":
                    if isDownloaded:
                        NewSortName = f"{CurrentName[1]} (download)"
                    else:
                        NewSortName = CurrentName[1].replace(" (download)", "")

                    self.cursor.execute("UPDATE movie SET c00 = ?, c10 = ? WHERE idMovie = ?", (NewName, NewSortName, KodiId))
                elif KodiType == "musicvideo":
                    self.cursor.execute("UPDATE musicvideo SET c00 = ? WHERE idMVideo = ?", (NewName, KodiId))

        return NameChanged

    def delete_Subcontent_download_tags(self, KodiEpisodeId):
        self.cursor.execute("SELECT idShow, idSeason FROM episode WHERE idEpisode = ?", (KodiEpisodeId,))
        EpisodesData = self.cursor.fetchone()
        KodiTVShowId = 0
        KodiSeasonId = 0

        if EpisodesData:
            if self.update_Name(EpisodesData[0], "tvshow", False):
                KodiTVShowId = EpisodesData[0]

            if self.update_Name(EpisodesData[1], "season", False):
                KodiSeasonId = EpisodesData[1]

        return KodiTVShowId, KodiSeasonId

    def replace_PathId(self, KodiFileId, KodiPathId):
        self.cursor.execute("UPDATE files SET idPath = ? WHERE idFile = ?", (KodiPathId, KodiFileId))

    def replace_Path(self, OldPath, NewPath):
        self.cursor.execute("UPDATE path SET strPath = ? WHERE strPath = ?", (NewPath, OldPath))

    def get_Fileinfo(self, KodiId, KodiType):
        if KodiType == "episode":
            self.cursor.execute("SELECT idFile, c00 FROM episode WHERE idEpisode = ?", (KodiId,))
        elif KodiType == "movie":
            self.cursor.execute("SELECT idFile, c00 FROM movie WHERE idMovie = ?", (KodiId,))
        elif KodiType == "musicvideo":
            self.cursor.execute("SELECT idFile, c00 FROM musicvideo WHERE idMVideo = ?", (KodiId,))

        ContentInfo = self.cursor.fetchone()

        if ContentInfo:
            self.cursor.execute("SELECT strFilename, idPath FROM files WHERE idFile = ?", (ContentInfo[0],))
            FileInfo = self.cursor.fetchone()

            if FileInfo:
                self.cursor.execute("SELECT idParentPath FROM path WHERE idPath = ?", (FileInfo[1],))
                PathInfo = self.cursor.fetchone()

                if PathInfo:
                    return ((KodiId, PathInfo[0], FileInfo[1], ContentInfo[0], FileInfo[0], ContentInfo[1]),)

        return ()

    def get_Progress_by_KodiType_KodiId(self, KodiType, KodiId):
        if KodiType == "movie":
            self.cursor.execute("SELECT idFile FROM movie WHERE idMovie = ?", (KodiId,))
        elif KodiType == "episode":
            self.cursor.execute("SELECT idFile FROM episode WHERE idEpisode = ?", (KodiId,))
        elif KodiType == "musicvideo":
            self.cursor.execute("SELECT idFile FROM musicvideo WHERE idMVideo = ?", (KodiId,))
        else:
            return 0

        KodiFileId = self.cursor.fetchone()

        if KodiFileId:
            self.cursor.execute("SELECT timeInSeconds FROM bookmark WHERE idFile = ? AND type = ?", (KodiFileId[0], 1))
            Progress = self.cursor.fetchone()

            if Progress:
                return Progress[0]

        return 0

    def get_Progress(self, KodiFileId):
        self.cursor.execute("SELECT playCount, lastPlayed FROM files WHERE idFile = ?", (KodiFileId,))
        FileInfo = self.cursor.fetchone()

        if FileInfo:
            self.cursor.execute("SELECT timeInSeconds FROM bookmark WHERE idFile = ? AND type = ?", (KodiFileId, 1))
            Progress = self.cursor.fetchone()

            if Progress:
                return True, Progress[0], FileInfo[0], FileInfo[1]

            return True, 0, FileInfo[0], FileInfo[1]

        return False, None, None, None

    # Path
    def delete_path(self, KodiPath):
        self.cursor.execute("DELETE FROM path WHERE strPath = ?", (KodiPath,))

    def toggle_path(self, OldPath, NewPath):
        PathSubstitution = NewPath.startswith("/emby_addon_mode/")
        self.cursor.execute("SELECT idFile, strFilename FROM files")
        FileNames = self.cursor.fetchall()

        for FileName in FileNames:
            if not PathSubstitution:
                FileNameNew = quote(FileName[1])
            else:
                FileNameNew = unquote(FileName[1])

            self.cursor.execute("UPDATE files SET strFilename = ? WHERE idFile = ?", (FileNameNew, FileName[0]))

        self.cursor.execute("SELECT idPath, strPath FROM path")
        Pathes = self.cursor.fetchall()

        for Path in Pathes:
            if Path[1].startswith(OldPath):
                PathMod = toggle_path(Path[1], NewPath)
                self.cursor.execute("UPDATE path SET strPath = ? WHERE idPath = ?", (PathMod, Path[0]))

        self.cursor.execute("SELECT idMovie, c19, c22 FROM movie")
        Pathes = self.cursor.fetchall()

        for Path in Pathes:
            if Path[1] and Path[1].startswith(OldPath):
                PathMod = toggle_path(Path[1], NewPath)
                self.cursor.execute("UPDATE movie SET c19 = ? WHERE idMovie = ?", (PathMod, Path[1]))

            if Path[2].startswith(OldPath):
                PathMod = toggle_path(Path[2], NewPath)
                self.cursor.execute("UPDATE movie SET c22 = ? WHERE idMovie = ?", (PathMod, Path[0]))

        self.cursor.execute("SELECT idEpisode, c18 FROM episode")
        Pathes = self.cursor.fetchall()

        for Path in Pathes:
            if Path[1].startswith(OldPath):
                PathMod = toggle_path(Path[1], NewPath)
                self.cursor.execute("UPDATE episode SET c18 = ? WHERE idEpisode = ?", (PathMod, Path[0]))

        self.cursor.execute("SELECT idMVideo, c13 FROM musicvideo")
        Pathes = self.cursor.fetchall()

        for Path in Pathes:
            if Path[1].startswith(OldPath):
                PathMod = toggle_path(Path[1], NewPath)
                self.cursor.execute("UPDATE musicvideo SET c13 = ? WHERE idMVideo = ?", (PathMod, Path[0]))

    def get_add_path(self, Path, MediaType, LinkId=None):
        if Path.startswith("http://127.0.0.1:57342/"):
            PathMod = f"{Path}|redirect-limit=1000"
        else:
            PathMod = Path

        self.cursor.execute("SELECT idPath FROM path WHERE strPath = ?", (PathMod,))
        Data = self.cursor.fetchone()

        if Data:
            return Data[0]

        self.cursor.execute("SELECT coalesce(max(idPath), 0) FROM path")
        KodiPathId = self.cursor.fetchone()[0] + 1

        if MediaType:
            self.cursor.execute("INSERT INTO path(idPath, strPath, strContent, strScraper, noUpdate, idParentPath) VALUES (?, ?, ?, ?, ?, ?)", (KodiPathId, PathMod, MediaType, 'metadata.local', 1, LinkId))
        else:
            self.cursor.execute("INSERT INTO path(idPath, strPath, strContent, strScraper, noUpdate, idParentPath) VALUES (?, ?, ?, ?, ?, ?)", (KodiPathId, PathMod, MediaType, None, 1, LinkId))

        return KodiPathId

def toggle_path(CurrentPath, NewPath):
    if NewPath == "http://127.0.0.1:57342/":
        if CurrentPath.find("/emby_addon_mode/") != -1:
            return f'{CurrentPath.replace("/emby_addon_mode/", "http://127.0.0.1:57342/")}|redirect-limit=1000'

        return CurrentPath

    return CurrentPath.replace("http://127.0.0.1:57342/", "/emby_addon_mode/").replace("|redirect-limit=1000", "")
