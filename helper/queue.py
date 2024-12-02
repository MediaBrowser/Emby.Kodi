from _thread import allocate_lock
import xbmc


class Queue:
    def __init__(self):
        self.Lock = allocate_lock()
        self.QueuedItems = ()
        self.Lock.acquire()
        self.Busy = allocate_lock()

    def get(self):
        ReturnData = ()

        try:
            self.Lock.acquire()

            with self.Busy:
                ReturnData = self.QueuedItems[0]
                self.QueuedItems = self.QueuedItems[1:]

                if self.Lock.locked():
                    if self.QueuedItems:
                        self.Lock.release()
                else:
                    if not self.QueuedItems:
                        self.Lock.acquire()
        except Exception as Error:
            xbmc.log(f"EMBY.helper.queue: get: {Error}, queuelen: {len(ReturnData)}", 2) # LOGWARNING

        return ReturnData

    def getall(self):
        ReturnData = ()

        try:
            self.Lock.acquire()

            with self.Busy:
                ReturnData = self.QueuedItems
                self.QueuedItems = ()

                if not self.Lock.locked():
                    self.Lock.acquire()

        except Exception as Error:
            xbmc.log(f"EMBY.helper.queue: getall: {Error}, queuelen: {len(ReturnData)}", 2) # LOGWARNING

        return ReturnData

    def put(self, Data):
        with self.Busy:
            if isinstance(Data, list):
                self.QueuedItems += tuple(Data)
            elif isinstance(Data, tuple):
                self.QueuedItems += Data
            else:
                self.QueuedItems += (Data,)

            if self.Lock.locked():
                self.Lock.release()

    def clear(self):
        with self.Busy:
            if not self.Lock.locked():
                self.Lock.acquire()

            self.QueuedItems = ()

    def isEmpty(self):
        return not bool(self.QueuedItems)
