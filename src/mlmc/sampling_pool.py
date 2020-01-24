from abc import ABC, abstractmethod
from multiprocessing import Pool as ProcPool
from multiprocessing.pool import ThreadPool as Threads
from level_simulation import LevelSimulation
import numpy as np
import queue


class SamplingPool(ABC):

    def __init__(self):
        self.need_workspace = False

    @abstractmethod
    def schedule_sample(self, sample_id, level_sim: LevelSimulation):
        """
        Method for calculating simulation samples
        :param sample_id: str
        :param level_sim: level_simulation.LevelSimulation instance
        :return: Tuple[str, List]
        """

    @abstractmethod
    def have_permanent_sample(self, sample_id):
        """
        Is sample serialized?
        """

    @abstractmethod
    def get_finished(self):
        """
        Return finished samples
        :return: list of results, number of running samples
        """

    # @ TODO: remove
    def change_to_sample_directory(self, sample_id, level_id):
        pass


class OneProcessPool(SamplingPool):

    def __init__(self):
        """
        Everything is running in one process
        """
        self._queues = {}
        self._n_running = 0

    def schedule_sample(self, sample_id, level_sim):
        self._n_running += 1
        level_sim.config_dict["sample_id"] = sample_id
        result = level_sim.calculate(level_sim.config_dict)

        self._queues.setdefault(level_sim.level_id, queue.Queue()).put((sample_id, result[0], result[1]))
        return result

    def have_permanent_sample(self, sample_id):
        return False

    def get_finished(self):
        """
        return results from queue - list of (sample_id, pair_of_result_vectors, error_message)
        """
        results = list(np.empty(len(self._queues)))
        for level_id, queue in self._queues.items():
            results[level_id] = list(queue.queue)
            self._n_running -= len(results[level_id])

        return results, self._n_running


class ProcessPool(OneProcessPool):

    def __init__(self, n_processes):
        self._pool = ProcPool(n_processes)
        self._queues = {}
        self._n_running = 0

        self._queue = queue.Queue()

    def schedule_sample(self, sample_id, level_sim):
        level_sim.config_dict["sample_id"] = sample_id
        result = self._pool.apply_async(ProcessPool.calculate_sample, args=(sample_id, level_sim, ),
                                        callback=self.result_callback, error_callback=self.error_callback)
        result.get()
        return result

    def result_callback(self, res):
        print("res ", res)
        self._queue.put((res[0], res[1], "message"))

    def error_callback(self, res):
        print("res ", res)
        self._queue.put((res[0], res[1], "There was an error"))

    @staticmethod
    def calculate_sample(sample_id, level_sim):
        """
        Method for calculating results
        :param sample_id:
        :param level_sim:
        :return:
        """
        res = level_sim.calculate(level_sim.config_dict)
        return sample_id, res


class ThreadPool(ProcessPool):

    def __init__(self, n_thread):
        self._pool = Threads(n_thread)
        self._queue = queue.Queue()
