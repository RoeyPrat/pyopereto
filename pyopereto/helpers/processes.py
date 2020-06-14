from pyopereto.client import OperetoClient
from threading import Timer

class ProcessLogScheduler():
    """
        from time import sleep
        p = ProcessLogScheduler(1)
        try:
            p.write('eAsEFPGfJun', [{'text': 'my log entry 1', 'level': 'INFO'}])
            p.write('eAsEFPGfJun', [{'text': 'my log entry 2', 'level': 'INFO'}])
            p.write('53cqHRdu4Cr', [{'text': 'some log text..', 'level': 'ERROR'}])

            sleep(5)  # your long-running job goes here...
        finally:
            p.stop()

    """
    def __init__(self, interval=2):
        self.buffer = {
            0: {},
            1: {}
        }
        self.active_buffer = 0
        self._timer = None
        self.client = OperetoClient()
        self.is_running = False
        self.interval = interval
        self.start()

    def _switch_buffer(self):
        active_buffer_sn = self.active_buffer
        self.active_buffer = abs(int(self.active_buffer) - 1)
        logs = self.buffer[active_buffer_sn]
        self.buffer[active_buffer_sn]={}
        return logs

    def __del__(self):
        self.stop()

    def flush_logs(self, *args):
        self.is_running = False
        self.start()
        for pid, entries in self._switch_buffer().items():
            self.client.send_process_log(pid, entries)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self.flush_logs)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False

    def write(self, pid, log_entries=[]):
        if not pid in self.buffer[self.active_buffer]:
            self.buffer[self.active_buffer][pid]=[]
        self.buffer[self.active_buffer][pid]+=log_entries
