class ImageFrame(object):

    def __init__(self, timestamp, image):
        self.timestamp = timestamp
        self.image = image


class ThreadStatisticsData(object):

    def __init__(self):
        self.average_fps = 0
        self.frames_processed_count = 0
