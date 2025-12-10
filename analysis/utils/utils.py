import psutil
import time
import threading
import os
import numpy as np

class ResourceMonitor:
    def __init__(self, interval=0.1):
        self.interval = interval
        self.process = psutil.Process(os.getpid())
        self.running = False
        self.thread = None
        self.cpu_usages = []
        self.ram_usages = []
        self.start_time = 0
        self.end_time = 0

    def _monitor(self):
        while self.running:
            cpu = self.process.cpu_percent(interval=None)
            ram = self.process.memory_info().rss / (1024 * 1024) 
            
            self.cpu_usages.append(cpu)
            self.ram_usages.append(ram)
            time.sleep(self.interval)

    def start(self):
        self.cpu_usages = []
        self.ram_usages = []
        self.running = True
        self.start_time = time.time()
        self.process.cpu_percent(interval=None)
        self.thread = threading.Thread(target=self._monitor)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        self.end_time = time.time()
        
        exec_time = self.end_time - self.start_time
        avg_cpu = np.mean(self.cpu_usages) if self.cpu_usages else 0
        max_ram = np.max(self.ram_usages) if self.ram_usages else 0
        
        return {
            "time": exec_time,
            "cpu_avg": avg_cpu,
            "ram_peak": max_ram
        }