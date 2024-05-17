from _thread import allocate_lock
import xbmc


class Queue:
    def __init__(self):
        self.Lock = allocate_lock()
        self.QueuedItems = ()
        self.Lock.acquire()
        self.Busy = allocate_lock()

    def get(self):
        try:
            with self.Lock:
                with self.Busy:
                    ReturnData = self.QueuedItems[0]
                    self.QueuedItems = self.QueuedItems[1:]
        except Exception as Error:
            xbmc.log(f"EMBY.helper.queue: get: {Error}", 2) # LOGWARNING

        if not self.QueuedItems:
            self.LockQueue()

        return ReturnData

    def getall(self):
        try:
            with self.Lock:
                with self.Busy:
                    ReturnData = self.QueuedItems
                    self.QueuedItems = ()
        except Exception as Error:
            xbmc.log(f"EMBY.helper.queue: getall: {Error}", 2) # LOGWARNING

        self.LockQueue()
        return ReturnData

    def put(self, Data):
        with self.Busy:
            if isinstance(Data, list):
                self.QueuedItems += tuple(Data)
            elif isinstance(Data, tuple):
                self.QueuedItems += Data
            else:
                self.QueuedItems += (Data,)

        self.UnLockQueue()

    def LockQueue(self):
        if not self.Lock.locked():
            self.Lock.acquire()

    def UnLockQueue(self):
        if self.Lock.locked():
            self.Lock.release()

    def clear(self):
        with self.Busy:
            self.LockQueue()
            self.QueuedItems = ()

    def isEmpty(self):
        return not bool(self.QueuedItems)
