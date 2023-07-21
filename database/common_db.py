from helper import utils

class CommonDatabase:
    def __init__(self, cursor):
        self.cursor = cursor

    # reset
    def delete_tables(self, DatabaseName):
        utils.progress_open(f"{utils.Translate(33415)}-{DatabaseName} {utils.Translate(33416)}")

        # Temporay remove triggers
        self.cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
        Triggers = self.cursor.fetchall()

        for Trigger in Triggers:
            self.cursor.execute(f"DROP TRIGGER {Trigger[0]}")

        # Delete tables
        self.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")
        tables = self.cursor.fetchall()
        Counter = 0
        Increment = 100.0 / (len(tables) - 1)

        for table in tables:
            name = table[0]

            if name not in ('version', 'versiontagscan'):
                Counter += 1
                utils.progress_update(int(Counter * Increment), utils.Translate(33199), f"{utils.Translate(33415)}-{DatabaseName} {utils.Translate(33416)}: {name}")
                self.cursor.execute(f"DELETE FROM {name}")

        # readding triggers
        for Trigger in Triggers:
            self.cursor.execute(Trigger[1])

        utils.progress_close()

    # artwork
    def delete_artwork(self, KodiId, KodiMediaType):
        self.cursor.execute("DELETE FROM art WHERE media_id = ? AND media_type = ?", (KodiId, KodiMediaType))

    def delete_artwork_force(self, KodiId):
        self.cursor.execute("DELETE FROM art WHERE media_id = ?", (KodiId,))

    def get_artwork_urls(self, media_type):
        self.cursor.execute("SELECT url FROM art WHERE media_type = ?", (media_type,))
        return self.cursor.fetchall()

    def get_artwork_urls_all(self):
        self.cursor.execute("SELECT url FROM art")
        return self.cursor.fetchall()

    def add_artwork(self, KodiArtworks, KodiId, KodiMediaType):
        for ArtworkId, ImagePath in list(KodiArtworks.items()):
            if ArtworkId != "fanart":
                if ImagePath:
                    self.cursor.execute("INSERT INTO art(media_id, media_type, type, url) VALUES (?, ?, ?, ?)", (KodiId, KodiMediaType, ArtworkId, ImagePath))
            else:
                for ArtworkFanArtId, ImageFanArtPath in list(KodiArtworks['fanart'].items()):
                    self.cursor.execute("INSERT INTO art(media_id, media_type, type, url) VALUES (?, ?, ?, ?)", (KodiId, KodiMediaType, ArtworkFanArtId, ImageFanArtPath))
